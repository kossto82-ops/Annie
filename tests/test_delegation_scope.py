"""Tests for delegation scopes (Increment 186, roadmap F6 deepening).

A ``DelegationScope`` bounds *which* tools one delegated task may use behind the
`TaskAgent` seam. Covers the value object + permission-ceiling factories, the
``run_scoped`` seam helper, both registry-backed executors (decided-script and
model-driven), and Jarvis's ``delegate``/``execute`` wiring: an out-of-scope call
is refused truthfully, never folded into a fabricated success.
"""

from __future__ import annotations

import importlib.util

import pytest

from jarvis.domain.enums.permission_level import PermissionLevel
from jarvis.domain.retrieval.task_agent_source import run_scoped
from jarvis.domain.tools.tool_registry import ToolRegistry
from jarvis.domain.value_objects.delegation_scope import (
    DelegationScope,
    scope_at_most,
)
from jarvis.domain.value_objects.task_result import TaskResult
from jarvis.domain.value_objects.tool_call_result import ToolCallResult
from jarvis.domain.value_objects.tool_spec import ToolSpec
from jarvis.infrastructure.echo_tool import EchoTool
from jarvis.infrastructure.task_agent_source import (
    ToolRegistryTaskAgent,
    registered_scope_at_most,
)
from jarvis.jarvis import Jarvis

_PDAI_AVAILABLE = importlib.util.find_spec("pydantic_ai") is not None


class _ExternalTool:
    """A tool whose permission always needs explicit approval."""

    spec = ToolSpec(
        name="external",
        description="an external action",
        args={},
        permission=PermissionLevel.EXTERNAL_ACTION,
    )

    def run(self, arguments: dict[str, str]) -> ToolCallResult:
        del arguments
        return ToolCallResult(value="external done", ok=True)


class TestDelegationScope:
    def test_none_allows_nothing(self) -> None:
        scope = DelegationScope.none()
        assert not scope.allows("echo")
        assert scope.allowed_tools == frozenset()

    def test_all_allows_exactly_the_given_names(self) -> None:
        scope = DelegationScope.all("echo", "filesystem")
        assert scope.allows("echo")
        assert scope.allows("filesystem")
        assert not scope.allows("external")

    def test_duplicate_names_collapse(self) -> None:
        scope = DelegationScope.all("echo", "echo")
        assert scope.allowed_tools == frozenset({"echo"})

    def test_scopes_compare_by_content(self) -> None:
        assert DelegationScope.all("echo") == DelegationScope.all("echo")
        assert DelegationScope.all("echo") != DelegationScope.all("filesystem")

    def test_blank_tool_name_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            DelegationScope.all("  ")
        with pytest.raises(ValueError, match="must not be empty"):
            DelegationScope(allowed_tools=frozenset({"echo", ""}))

    def test_scope_at_most_keeps_lower_permission_tools_only(self) -> None:
        tools = {
            "read": PermissionLevel.READ,
            "write": PermissionLevel.WRITE,
            "external": PermissionLevel.EXTERNAL_ACTION,
        }
        scope = scope_at_most(tools, PermissionLevel.WRITE)
        assert scope.allows("read")
        assert scope.allows("write")
        assert not scope.allows("external")

    def test_scope_at_most_is_inclusive_of_the_level_itself(self) -> None:
        tools = {
            "read": PermissionLevel.READ,
            "external": PermissionLevel.EXTERNAL_ACTION,
        }
        assert scope_at_most(tools, PermissionLevel.READ).allows("read")
        assert not scope_at_most(tools, PermissionLevel.READ).allows("external")
        assert scope_at_most(
            tools, PermissionLevel.EXTERNAL_ACTION
        ).allows("external")


class TestRegisteredScopeAtMost:
    def test_under_execute_it_keeps_local_tools_and_drops_external(self) -> None:
        registry = ToolRegistry()
        registry.register(EchoTool())
        registry.register(_ExternalTool())
        scope = registered_scope_at_most(registry, PermissionLevel.EXECUTE)
        assert scope.allows("echo")
        assert not scope.allows("external")

    def test_at_external_level_it_keeps_every_registered_tool(self) -> None:
        registry = ToolRegistry()
        registry.register(EchoTool())
        registry.register(_ExternalTool())
        scope = registered_scope_at_most(registry, PermissionLevel.EXTERNAL_ACTION)
        assert scope.allows("echo")
        assert scope.allows("external")


class _ScopedAgent:
    def __init__(self) -> None:
        self.tasks: list[tuple[str, DelegationScope | None]] = []

    def run_task(self, task: str) -> TaskResult:
        return TaskResult(task=task, summary="ran", success=True)

    def run_scoped(
        self, task: str, scope: DelegationScope | None = None
    ) -> TaskResult:
        self.tasks.append((task, scope))
        return TaskResult(task=task, summary="scoped", success=True)


class TestRunScopedHelper:
    def test_uses_the_agent_scope_aware_path(self) -> None:
        agent = _ScopedAgent()
        scope = DelegationScope.all("echo")
        result = run_scoped(agent, "work", scope)
        assert result.success
        assert result.summary == "scoped"
        assert agent.tasks == [("work", scope)]

    def test_plain_agent_falls_back_to_run_task(self) -> None:
        class _Plain:
            def run_task(self, task: str) -> TaskResult:
                del task
                return TaskResult(task="", summary="plain", success=True)

        assert run_scoped(_Plain(), "work", DelegationScope.none()).summary == "plain"

    def test_scope_agent_is_a_task_agent_protocol_member_free(self) -> None:
        # The seam helper, not the protocol, carries the scope: a plain agent stays
        # a TaskAgent without declaring run_scoped.
        from jarvis.domain.retrieval.task_agent_source import TaskAgent

        class _Plain:
            def run_task(self, task: str) -> TaskResult:
                del task
                return TaskResult(task="", summary="plain", success=True)

        assert isinstance(_Plain(), TaskAgent)


class TestToolRegistryTaskAgentScoped:
    def test_out_of_scope_tool_refuses_truthfully(self) -> None:
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = ToolRegistryTaskAgent(registry)
        result = agent.run_scoped(
            'echo text="in scope"\nexternal x=1', DelegationScope.all("echo")
        )
        assert not result.success
        assert "echo ok" in result.summary
        assert "external: outside the delegation scope" in result.summary

    def test_every_line_out_of_scope_is_no_success(self) -> None:
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = ToolRegistryTaskAgent(registry, approved=True)
        result = agent.run_scoped("echo text=hi", DelegationScope.all("other"))
        assert not result.success
        assert "echo: outside the delegation scope" in result.summary

    def test_scope_none_behaves_exactly_like_run_task(self) -> None:
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = ToolRegistryTaskAgent(registry)
        plain = agent.run_task('echo text="hi"')
        scoped = agent.run_scoped('echo text="hi"')
        assert scoped.success == plain.success
        assert scoped.summary == plain.summary

    def test_approval_and_scope_are_orthogonal_gates(self) -> None:
        registry = ToolRegistry()
        registry.register(_ExternalTool())
        agent = ToolRegistryTaskAgent(registry, approved=True)
        # The scope keeps the gate: even fully approved, an out-of-scope tool refuses.
        result = agent.run_scoped("external x=1", DelegationScope.none())
        assert not result.success
        assert "outside the delegation scope" in result.summary


class TestPydanticAiTaskAgentScoped:
    @pytest.mark.skipif(not _PDAI_AVAILABLE, reason="needs pydantic-ai")
    def test_in_scope_tool_runs_under_a_scope(self) -> None:
        import importlib
        from typing import Any
        from typing import cast as tcast

        from jarvis.infrastructure.provider_settings import ProviderSettings
        from jarvis.infrastructure.pydantic_ai_task_agent import PydanticAiTaskAgent

        def pai(module: str) -> Any:
            return tcast(Any, importlib.import_module(module))

        messages = pai("pydantic_ai.messages")
        function_mod = pai("pydantic_ai.models.function")

        calls = {"n": 0}

        def function(msgs: Any, agent_info: Any) -> Any:
            del msgs, agent_info
            calls["n"] += 1
            if calls["n"] == 1:
                return messages.ModelResponse(
                    parts=[
                        messages.ToolCallPart(
                            tool_name="echo", args={"text": "hi"}
                        )
                    ]
                )
            return messages.ModelResponse(parts=[messages.TextPart("done")])

        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = PydanticAiTaskAgent(
            registry,
            settings=ProviderSettings(provider="pydantic", model="x"),
            model=function_mod.FunctionModel(function),
        )
        result = agent.run_scoped("say hi", DelegationScope.all("echo"))
        assert result.success
        assert "echo ok" in result.summary

    @pytest.mark.skipif(not _PDAI_AVAILABLE, reason="needs pydantic-ai")
    def test_out_of_scope_tool_cannot_run(self) -> None:
        import importlib
        from typing import Any
        from typing import cast as tcast

        from jarvis.infrastructure.provider_settings import ProviderSettings
        from jarvis.infrastructure.pydantic_ai_task_agent import PydanticAiTaskAgent

        def pai(module: str) -> Any:
            return tcast(Any, importlib.import_module(module))

        messages = pai("pydantic_ai.messages")
        function_mod = pai("pydantic_ai.models.function")

        def function(msgs: Any, agent_info: Any) -> Any:
            del msgs, agent_info
            return messages.ModelResponse(
                parts=[messages.ToolCallPart(tool_name="echo", args={"text": "hi"})]
            )

        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = PydanticAiTaskAgent(
            registry,
            settings=ProviderSettings(provider="pydantic", model="x"),
            model=function_mod.FunctionModel(function),
        )
        # The scope removes the tool from the toolset: the model-driven loop can
        # never execute it, so the run is an honest non-success.
        result = agent.run_scoped("say hi", DelegationScope.all("other"))
        assert not result.success


class TestJarvisScopeWiring:
    def test_delegate_hands_a_scope_to_the_agent(self) -> None:
        registry = ToolRegistry()
        registry.register(EchoTool())
        jarvis = Jarvis(task_agent=ToolRegistryTaskAgent(registry))
        result = jarvis.delegate('echo text="hi"', scope=DelegationScope.all("echo"))
        assert result.success
        blocked = jarvis.delegate(
            'echo text="hi"', scope=DelegationScope.all("filesystem")
        )
        assert not blocked.success
        assert "outside the delegation scope" in blocked.summary

    def test_execute_hands_a_scope_to_the_executor(self) -> None:
        registry = ToolRegistry()
        registry.register(EchoTool())
        jarvis = Jarvis(instruction_agent=ToolRegistryTaskAgent(registry))
        result = jarvis.execute(
            'echo text="hi"', scope=DelegationScope.all("echo")
        )
        assert result.success
        blocked = jarvis.execute(
            'echo text="hi"', scope=DelegationScope.all("filesystem")
        )
        assert not blocked.success
        assert "outside the delegation scope" in blocked.summary

    def test_unwired_jarvis_raises_even_with_a_scope(self) -> None:
        jarvis = Jarvis()
        with pytest.raises(RuntimeError, match="agent capability"):
            jarvis.delegate("do a thing", scope=DelegationScope.none())
        with pytest.raises(RuntimeError, match="instruction executor"):
            jarvis.execute("do a thing", scope=DelegationScope.none())

    def test_plain_agent_ignores_scope_and_runs_the_task(self) -> None:
        class _Plain:
            def __init__(self) -> None:
                self.runs: list[str] = []

            def run_task(self, task: str) -> TaskResult:
                self.runs.append(task)
                return TaskResult(task=task, summary="ran", success=True)

        agent = _Plain()
        jarvis = Jarvis(task_agent=agent)  # type: ignore[arg-type]
        result = jarvis.delegate("work", scope=DelegationScope.none())
        assert result.success
        assert agent.runs == ["work"]