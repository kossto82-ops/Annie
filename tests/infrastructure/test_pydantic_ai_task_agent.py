"""PydanticAiTaskAgent: model-driven tool loop over the ToolRegistry (D7, D8, revised D1).

Offline-only: an injected FunctionModel chooses the tool calls, while the real
ToolRegistry holds the gate (permission/approval) and the trace (ToolCall events).
Skipped entirely when pydantic-ai is not installed.
"""

from __future__ import annotations

import importlib
import json
from typing import Any, cast

import pytest

pytest.importorskip("pydantic_ai")  # noqa: E402

from jarvis import Jarvis
from jarvis.domain.enums.permission_level import PermissionLevel
from jarvis.domain.tools.tool_registry import ToolRegistry
from jarvis.domain.value_objects.tool_call import ToolCall
from jarvis.domain.value_objects.tool_call_result import ToolCallResult
from jarvis.domain.value_objects.tool_spec import ToolSpec
from jarvis.infrastructure.echo_tool import EchoTool
from jarvis.infrastructure.provider_settings import ProviderSettings
from jarvis.infrastructure.pydantic_ai_task_agent import PydanticAiTaskAgent
from jarvis.infrastructure.task_agent_source import ToolRegistryTaskAgent


class _WorldTool:
    """A test tool at the EXTERNAL_ACTION level: needs upstream approval."""

    spec = ToolSpec(
        name="world",
        description="touch the outside world",
        args={"url": "the url to reach"},
        permission=PermissionLevel.EXTERNAL_ACTION,
    )

    def run(self, arguments: dict[str, str]) -> ToolCallResult:
        return ToolCallResult(ok=True, value="touched")


class _RecordingObserver:
    """Collects every ToolCall the registry records, for trace assertions."""

    def __init__(self) -> None:
        self.calls: list[ToolCall] = []

    def __call__(self, call: ToolCall) -> None:
        self.calls.append(call)


def _pai(module: str) -> Any:
    return cast(Any, importlib.import_module(module))


def _settings() -> ProviderSettings:
    return ProviderSettings(
        provider="pydantic",
        model="qwen2.5:7b",
        base_url="http://localhost:11434/v1",
    )


def _response(
    *, text: str | None = None, tool_name: str | None = None, tool_args: str = "{}"
) -> Any:
    messages = _pai("pydantic_ai.messages")
    parts: list[Any] = []
    if text is not None:
        parts.append(messages.TextPart(text))
    if tool_name is not None:
        parts.append(messages.ToolCallPart(tool_name=tool_name, args=tool_args))
    return messages.ModelResponse(parts=parts)


def _tool_model(
    order: list[tuple[str, dict[str, str]]], final: str = "done"
) -> Any:
    """A FunctionModel that emits the listed tool calls in order, then finishes."""
    function_mod = _pai("pydantic_ai.models.function")
    actions: list[Any] = [("tool", name, args) for name, args in order] + [
        ("text", final)
    ]
    state = iter(actions)

    def function(messages: Any, agent_info: Any) -> Any:
        del messages, agent_info
        action = next(state)
        if action[0] == "tool":
            return _response(tool_name=action[1], tool_args=json.dumps(action[2]))
        return _response(text=action[1])

    return function_mod.FunctionModel(function)


def _plain_text_model(text: str) -> Any:
    function_mod = _pai("pydantic_ai.models.function")

    def function(messages: Any, agent_info: Any) -> Any:
        del messages, agent_info
        return _response(text=text)

    return function_mod.FunctionModel(function)


def _usage_model() -> Any:
    """A FunctionModel that runs one echo call and reports token usage."""
    function_mod = _pai("pydantic_ai.models.function")
    run_usage = _pai("pydantic_ai.usage").RunUsage
    messages = _pai("pydantic_ai.messages")
    state = {"decided": False}

    def function(msgs: Any, agent_info: Any) -> Any:
        del agent_info
        if not state["decided"]:
            state["decided"] = True
            return messages.ModelResponse(
                parts=[messages.ToolCallPart(tool_name="echo", args=json.dumps({"text": "hi"}))]
            )
        return messages.ModelResponse(
            parts=[messages.TextPart("done")],
            usage=run_usage(request_tokens=4, response_tokens=6),
        )

    return function_mod.FunctionModel(function)


def _registry_script_agent(
    observer: _RecordingObserver | None = None,
) -> ToolRegistryTaskAgent:
    return ToolRegistryTaskAgent(_registry(observer=observer))


def _registry(*, observer: _RecordingObserver | None = None) -> ToolRegistry:
    registry = ToolRegistry(observer=observer)
    registry.register(EchoTool())
    registry.register(_WorldTool())
    return registry


class TestModelDrivenLoop:
    def test_a_decided_step_runs_the_tool_through_the_registry(self) -> None:
        observer = _RecordingObserver()
        registry = _registry(observer=observer)
        agent = PydanticAiTaskAgent(
            registry, settings=_settings(), model=_tool_model([("echo", {"text": "hola"})])
        )

        result = agent.run_task("say hello")

        assert result.success
        assert "echo ok: hola" in result.summary
        assert len(observer.calls) == 1
        assert observer.calls[0].tool == "echo"
        assert observer.calls[0].arguments == {"text": "hola"}
        assert observer.calls[0].ok

    def test_a_failed_call_then_a_recovery_still_succeeds(self) -> None:
        # "world" is refused without approval; the model recovers with echo (EXECUTE).
        agent = PydanticAiTaskAgent(
            _registry(),
            settings=_settings(),
            approved=False,
            model=_tool_model([("world", {"url": "x"}), ("echo", {"text": "ok"})]),
        )

        result = agent.run_task("do the thing")

        assert result.success
        assert "world failed:" in result.summary
        assert "echo ok: ok" in result.summary

    def test_an_approval_refused_call_is_an_honest_failure(self) -> None:
        agent = PydanticAiTaskAgent(
            _registry(),
            settings=_settings(),
            approved=False,
            model=_tool_model([("world", {"url": "x"})]),
        )

        result = agent.run_task("touch the world")

        assert not result.success
        assert "world failed:" in result.summary
        assert "requires" in result.summary

    def test_with_upstream_approval_a_risky_call_runs(self) -> None:
        agent = PydanticAiTaskAgent(
            _registry(),
            settings=_settings(),
            model=_tool_model([("world", {"url": "https://example.test"})]),
        )

        result = agent.run_task("approved touch")

        assert result.success
        assert "world ok: touched" in result.summary

    def test_no_tool_calls_is_not_a_success(self) -> None:
        agent = PydanticAiTaskAgent(
            _registry(), settings=_settings(), model=_plain_text_model("no action")
        )

        result = agent.run_task("answer the question")

        assert not result.success
        assert result.summary == "no tool calls ran"

    def test_a_provider_failure_is_an_honest_failure(self) -> None:
        function_mod = _pai("pydantic_ai.models.function")

        def boom(messages: Any, agent_info: Any) -> Any:
            del messages, agent_info
            raise RuntimeError("provider down")

        agent = PydanticAiTaskAgent(
            _registry(),
            settings=_settings(),
            model=function_mod.FunctionModel(boom),
        )

        result = agent.run_task("act")

        assert not result.success
        assert "failed" in result.summary


class TestUsageAccounting:
    def test_the_loop_accounts_for_the_decision_run(self) -> None:
        agent = PydanticAiTaskAgent(
            _registry(), settings=_settings(), model=_usage_model()
        )

        agent.run_task("say hello")

        assert agent.usage().request_tokens == 4
        assert agent.usage().response_tokens == 6
        assert agent.usage().total_tokens == 10

    def test_a_failed_run_accounts_for_nothing(self) -> None:
        function_mod = _pai("pydantic_ai.models.function")

        def boom(messages: Any, agent_info: Any) -> Any:
            del messages, agent_info
            raise RuntimeError("provider down")

        agent = PydanticAiTaskAgent(
            _registry(), settings=_settings(), model=function_mod.FunctionModel(boom)
        )

        agent.run_task("act")

        assert agent.usage().total_tokens == 0


class TestFallback:
    def test_a_provider_outage_falls_back_to_a_decided_script_agent(self) -> None:
        function_mod = _pai("pydantic_ai.models.function")

        def boom(messages: Any, agent_info: Any) -> Any:
            del messages, agent_info
            raise RuntimeError("provider down")

        agent = PydanticAiTaskAgent(
            _registry(),
            settings=_settings(),
            model=function_mod.FunctionModel(boom),
            fallback=_registry_script_agent(),
        )

        result = agent.run_task("echo text=fallback-ok")

        # A decided script-shaped task still executes, honestly, through the fallback.
        assert result.success
        assert "echo ok" in result.summary

    def test_without_a_fallback_a_provider_outage_is_an_honest_failure(self) -> None:
        function_mod = _pai("pydantic_ai.models.function")

        def boom(messages: Any, agent_info: Any) -> Any:
            del messages, agent_info
            raise RuntimeError("provider down")

        agent = PydanticAiTaskAgent(
            _registry(), settings=_settings(), model=function_mod.FunctionModel(boom)
        )

        result = agent.run_task("act")

        assert not result.success
        assert "delegated task failed" in result.summary


class TestToolSchema:
    def test_the_schema_is_baked_from_the_spec(self) -> None:
        seen: dict[str, Any] = {}

        def inspect(messages: Any, agent_info: Any) -> Any:
            del messages
            seen["tools"] = [
                {
                    "name": ft.name,
                    "description": ft.description,
                    "schema": ft.parameters_json_schema,
                }
                for ft in agent_info.function_tools
            ]
            return _response(text="inspected")

        agent = PydanticAiTaskAgent(
            _registry(),
            settings=_settings(),
            model=_pai("pydantic_ai.models.function").FunctionModel(inspect),
        )

        agent.run_task("inspect")

        echo = next(t for t in seen["tools"] if t["name"] == "echo")
        assert echo["description"] == "echo the given text back verbatim"
        assert echo["schema"] == {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "the text to echo back"}},
            "required": ["text"],
            "additionalProperties": False,
        }


class TestDelegationThroughJarvis:
    def test_the_agent_rides_the_task_agent_seam_without_a_network(self) -> None:
        registry = _registry()
        agent = PydanticAiTaskAgent(
            registry, settings=_settings(), model=_tool_model([("echo", {"text": "hola"})])
        )

        jarvis = Jarvis(task_agent=agent)
        outcome = jarvis.delegate("say hello")

        assert outcome.success
        assert "echo ok" in outcome.summary