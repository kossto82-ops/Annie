"""Provider instrumentation (Phase 4): the shared collector and its wrappers.

The wrappers observe the `LanguageModel` and `TaskAgent` seams, so the counting must
hold for any concrete adapter -- including the scripted offline stub and a decided
script agent -- not just the pydantic-ai live path.
"""

from __future__ import annotations

import importlib.util
from typing import Any

import pytest

from jarvis.domain.value_objects.task_result import TaskResult
from jarvis.infrastructure.instrumented_language_model import instrument_model
from jarvis.infrastructure.instrumented_task_agent import instrument_agent
from jarvis.infrastructure.provider_stats import (
    InMemoryInstrumentation,
    ProviderCall,
)
from jarvis.infrastructure.scripted_language_model import ScriptedLanguageModel
from jarvis.infrastructure.usage import Usage

_PDAI_AVAILABLE = importlib.util.find_spec("pydantic_ai") is not None


class _ScriptedAgent:
    def run_task(self, task: str) -> TaskResult:
        return TaskResult(
            task=task,
            summary="echo ok",
            success=task.strip() != "break",
        )


class TestInMemoryInstrumentation:
    def test_starts_empty_and_aggregates(self) -> None:
        store = InMemoryInstrumentation()
        snap = store.snapshot()
        assert snap.calls == 0
        assert snap.successes == 0
        assert snap.total_seconds == 0.0

        store.record(
            ProviderCall(
                channel="chat",
                ok=True,
                duration_seconds=1.0,
                usage=Usage(),
            )
        )
        store.record(
            ProviderCall(
                channel="chat",
                ok=False,
                duration_seconds=0.5,
                usage=Usage(request_tokens=3),
            )
        )
        store.record(
            ProviderCall(
                channel="agent",
                ok=True,
                duration_seconds=2.0,
                usage=Usage(request_tokens=1),
            )
        )

        snap = store.snapshot()
        assert snap.calls == 3
        assert snap.successes == 2
        assert snap.failures == 1
        assert snap.chat_calls == 2
        assert snap.agent_calls == 1
        assert snap.total_seconds == 3.5
        assert snap.slowest_seconds == 2.0
        assert snap.usage.total_tokens == 4
        assert snap.success_rate == pytest.approx(2 / 3)


class TestInstrumentedLanguageModel:
    def test_records_success_and_honest_silence(self) -> None:
        store = InMemoryInstrumentation()
        model = instrument_model(
            ScriptedLanguageModel({"hi": "hello"}, default=""), instrumentation=store
        )

        assert model.complete("hi") == "hello"
        assert model.complete("absent-subject") == ""

        snap = store.snapshot()
        assert snap.calls == 2
        assert snap.successes == 1
        assert snap.failures == 1
        assert snap.chat_calls == 2

    def test_stream_counts_one_call_when_present(self) -> None:
        class _Streaming:
            def complete(self, prompt: str) -> str:
                del prompt
                return "one"

            def stream(self, prompt: str) -> list[str] | None:
                del prompt
                return ["one", "two"]

        store = InMemoryInstrumentation()
        model = instrument_model(_Streaming(), instrumentation=store)  # type: ignore[arg-type]

        pieces: list[str] = []
        for piece in model.stream("hi"):
            pieces.append(piece)
        assert pieces == ["one", "two"]
        assert store.snapshot().calls == 1
        assert store.snapshot().successes == 1

    def test_stream_falls_back_to_complete_without_a_stream_seam(self) -> None:
        class _CompleteOnly:
            def complete(self, prompt: str) -> str:
                del prompt
                return "answer"

        store = InMemoryInstrumentation()
        model = instrument_model(_CompleteOnly(), instrumentation=store)  # type: ignore[arg-type]
        assert list(model.stream("hi")) == ["answer"]
        assert store.snapshot().calls == 1
        assert store.snapshot().successes == 1

    def test_usage_forwarded_from_the_inner_adapter(self) -> None:
        class _WithUsage:
            def complete(self, prompt: str) -> str:
                del prompt
                return "x"

            def usage(self) -> Usage:
                return Usage(request_tokens=5)

        model = instrument_model(_WithUsage())  # type: ignore[arg-type]
        assert model.usage() == Usage(request_tokens=5)


class TestInstrumentedTaskAgent:
    def test_records_success_and_failure(self) -> None:
        store = InMemoryInstrumentation()
        agent = instrument_agent(_ScriptedAgent(), instrumentation=store)

        assert agent.run_task("go").success
        assert not agent.run_task("break").success

        snap = store.snapshot()
        assert snap.calls == 2
        assert snap.successes == 1
        assert snap.failures == 1
        assert snap.agent_calls == 2


@pytest.mark.skipif(not _PDAI_AVAILABLE, reason="needs pydantic-ai")
def test_live_pydantic_agent_runs_report_through_instrumentation() -> None:
    import importlib
    from typing import cast as tcast

    from jarvis.infrastructure.provider_settings import ProviderSettings
    from jarvis.infrastructure.pydantic_ai_task_agent import PydanticAiTaskAgent

    def pai(module: str) -> Any:
        return tcast(Any, importlib.import_module(module))

    messages = pai("pydantic_ai.messages")
    function_mod = pai("pydantic_ai.models.function")

    def function(msgs: Any, agent_info: Any) -> Any:
        del msgs, agent_info
        return messages.ModelResponse(parts=[messages.TextPart("no tools decided")])

    settings = ProviderSettings(
        provider="pydantic", model="qwen2.5:7b", base_url="http://localhost:11434/v1"
    )
    registry = _echo_only_registry()
    agent = PydanticAiTaskAgent(
        registry, settings=settings, model=function_mod.FunctionModel(function)
    )
    store = InMemoryInstrumentation()
    instrumented = instrument_agent(agent, instrumentation=store)

    result = instrumented.run_task("just look")
    assert not result.success  # no tool calls ran -> honest failed account
    assert store.snapshot().calls == 1
    assert store.snapshot().agent_calls == 1


def _echo_only_registry() -> Any:
    from jarvis.domain.tools.tool_registry import ToolRegistry
    from jarvis.infrastructure.echo_tool import EchoTool

    registry = ToolRegistry()
    registry.register(EchoTool())
    return registry