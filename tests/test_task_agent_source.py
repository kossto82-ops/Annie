"""Tests for the delegation capability seam (D1-revised).

Covers the `TaskResult` value object, the `TaskAgent` Protocol surface, the
`AgentCapability` provider, and Jarvis's integration: `can_do` reflects a wired
agent, `delegate` hands a material task to the agent edge, and an unwired Jarvis
stays offline with clear errors.
"""

from __future__ import annotations

import pytest

from jarvis.domain.retrieval.task_agent_source import TaskAgent
from jarvis.domain.value_objects.capability import Capability
from jarvis.domain.value_objects.task_result import TaskResult
from jarvis.infrastructure.capability_registry import (
    AgentCapability,
    build_default_registry,
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
