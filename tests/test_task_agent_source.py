"""Tests for the delegation capability seam (D1-revised).

Covers the `TaskResult` value object, the `TaskAgent` Protocol surface, the
`AgentCapability` provider, and Jarvis's integration: `can_do` reflects a wired
agent, `delegate` hands a material task to the agent edge, and an unwired Jarvis
stays offline with clear errors.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.domain.enums.permission_level import PermissionLevel
from jarvis.domain.retrieval.task_agent_source import TaskAgent
from jarvis.domain.tools.tool_registry import ToolRegistry
from jarvis.domain.value_objects.capability import Capability
from jarvis.domain.value_objects.task_result import TaskResult
from jarvis.domain.value_objects.tool_call_result import ToolCallResult
from jarvis.domain.value_objects.tool_spec import ToolSpec
from jarvis.infrastructure.capability_registry import (
    AgentCapability,
    build_default_registry,
)
from jarvis.infrastructure.echo_tool import EchoTool
from jarvis.infrastructure.provider_settings import ProviderSettings
from jarvis.infrastructure.task_agent_source import (
    ToolRegistryTaskAgent,
    build_instruction_agent,
)
from jarvis.jarvis import Jarvis


class _FakeTaskAgent:
    """An agent that returns a canned outcome and records the tasks it ran."""

    def __init__(self) -> None:
        self.runs: list[str] = []

    def run_task(self, task: str) -> TaskResult:
        self.runs.append(task)
        if "fail" in task:
            return TaskResult(task=task, summary="the agent could not finish", success=False)
        return TaskResult(task=task, summary="moved files to the archive", success=True)


class TestTaskResult:
    def test_result_requires_task_or_summary(self) -> None:
        with pytest.raises(ValueError):
            TaskResult(task="", summary="", success=True)

    def test_result_records_provenance(self) -> None:
        result = TaskResult(task="back up the folder", summary="done", success=True)
        assert result.provenance == "delegated task completed: back up the folder"

    def test_failed_result_records_failure(self) -> None:
        result = TaskResult(task="sync", summary="nope", success=False)
        assert "failed" in result.provenance


class TestTaskAgentProtocol:
    def test_fake_agent_satisfies_the_protocol(self) -> None:
        assert isinstance(_FakeTaskAgent(), TaskAgent)


class TestAgentCapability:
    def test_agent_capability_backs_the_delegation_name(self) -> None:
        provider = AgentCapability(_FakeTaskAgent())  # type: ignore[arg-type]
        assert provider.capability == "delegate to an agent"
        assert provider.is_available()

    def test_default_registry_backs_delegation_when_an_agent_is_wired(self) -> None:
        agent = _FakeTaskAgent()
        registry = build_default_registry(None, task_agent=agent)  # type: ignore[arg-type]
        assert registry.provider_for("delegate to an agent") is not None

    def test_default_registry_without_an_agent_has_no_delegation(self) -> None:
        registry = build_default_registry(None)
        assert registry.provider_for("delegate to an agent") is None


class TestJarvisDelegation:
    @staticmethod
    def _acquire(jarvis: Jarvis) -> None:
        capability = Capability(
            name="delegate to an agent",
            description="hand a decided material task to an edge agent",
            requirement="a wired task agent at the edge (TaskAgent)",
            provenance="test",
        )
        jarvis.remember_capability(capability)
        jarvis.acquire_capability("delegate to an agent")

    def test_can_do_reflects_a_wired_agent(self) -> None:
        jarvis = Jarvis(task_agent=_FakeTaskAgent())  # type: ignore[arg-type]
        self._acquire(jarvis)
        assert jarvis.can_do("delegate to an agent")

    def test_unwired_jarvis_is_offline_to_delegation(self) -> None:
        jarvis = Jarvis()
        self._acquire(jarvis)
        assert not jarvis.can_do("delegate to an agent")

    def test_delegate_hands_the_task_to_the_agent(self) -> None:
        agent = _FakeTaskAgent()
        jarvis = Jarvis(task_agent=agent)  # type: ignore[arg-type]
        result = jarvis.delegate("move files to the archive")
        assert result.success
        assert agent.runs == ["move files to the archive"]

    def test_delegate_reports_failed_outcomes_honestly(self) -> None:
        jarvis = Jarvis(task_agent=_FakeTaskAgent())  # type: ignore[arg-type]
        result = jarvis.delegate("fail this task")
        assert not result.success

    def test_wiring_an_agent_at_runtime_updates_can_do(self) -> None:
        jarvis = Jarvis()
        self._acquire(jarvis)
        assert not jarvis.can_do("delegate to an agent")
        jarvis.set_task_agent(_FakeTaskAgent())  # type: ignore[arg-type]
        assert jarvis.can_do("delegate to an agent")
        jarvis.set_task_agent(None)
        assert not jarvis.can_do("delegate to an agent")

    def test_delegate_raises_clearly_when_offline(self) -> None:
        jarvis = Jarvis()
        with pytest.raises(RuntimeError, match="agent capability"):
            jarvis.delegate("do a thing")


class _ExternalTool:
    """A tool whose permission level always needs explicit approval."""

    spec = ToolSpec(
        name="external",
        description="an external action",
        args={},
        permission=PermissionLevel.EXTERNAL_ACTION,
    )

    def run(self, arguments: dict[str, str]) -> ToolCallResult:
        return ToolCallResult(value="external done", ok=True)


class TestJarvisInstructionExecution:
    def test_execute_hands_the_instruction_to_the_executor(self) -> None:
        agent = _FakeTaskAgent()
        jarvis = Jarvis(instruction_agent=agent)  # type: ignore[arg-type]
        result = jarvis.execute("write a file with the plan")
        assert result.success
        assert agent.runs == ["write a file with the plan"]

    def test_execute_reports_failed_outcomes_honestly(self) -> None:
        jarvis = Jarvis(instruction_agent=_FakeTaskAgent())  # type: ignore[arg-type]
        result = jarvis.execute("fail this task")
        assert not result.success

    def test_execute_reflects_a_runtime_wired_executor(self) -> None:
        agent = _FakeTaskAgent()
        jarvis = Jarvis()
        assert jarvis.instruction_agent is None
        jarvis.set_instruction_agent(agent)  # type: ignore[arg-type]
        assert jarvis.instruction_agent is not None
        result = jarvis.execute("write a note")
        assert result.success
        jarvis.set_instruction_agent(None)
        assert jarvis.instruction_agent is None

    def test_execute_raises_clearly_when_offline(self) -> None:
        jarvis = Jarvis()
        assert jarvis.instruction_agent is None
        with pytest.raises(RuntimeError, match="instruction executor"):
            jarvis.execute("create a note")


class TestBuildInstructionAgent:
    def test_offline_without_a_sandbox_builds_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("JARVIS_AGENT_ROOT", raising=False)
        monkeypatch.delenv("JARVIS_MCP_CONFIG", raising=False)
        assert (
            build_instruction_agent(ProviderSettings(provider="scripted", model=""))
            is None
        )

    def test_with_a_sandbox_it_builds_an_earned_agency_executor(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("JARVIS_AGENT_ROOT", str(tmp_path))
        monkeypatch.delenv("JARVIS_MCP_CONFIG", raising=False)
        agent = build_instruction_agent(ProviderSettings(provider="scripted", model=""))
        assert agent is not None
        assert isinstance(agent, ToolRegistryTaskAgent)

    def test_protocol_level_acts_run_but_external_ones_refuse(self) -> None:
        registry = ToolRegistry()
        registry.register(EchoTool())
        registry.register(_ExternalTool())
        agent = ToolRegistryTaskAgent(registry, approved=False)
        result = agent.run_task('echo text=hello\nexternal x=1')
        assert not result.success
        assert "echo ok" in result.summary
        assert "requires explicit approval" in result.summary

    def test_approval_lets_an_external_act_run(self) -> None:
        registry = ToolRegistry()
        registry.register(_ExternalTool())
        agent = ToolRegistryTaskAgent(registry, approved=True)
        result = agent.run_task("external x=1")
        assert result.success
        assert "external ok" in result.summary
