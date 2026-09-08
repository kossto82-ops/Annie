"""PydanticAiModel: the Pydantic AI adapter over the LanguageModel seam (D7, D8).

Offline-only. A `FunctionModel` is injected as the Pydantic AI model, so no network and
no API key are ever needed; the module is skipped entirely when pydantic-ai is absent.
The test reaches pydantic-ai through importlib (like the adapter) so the pyright gate
stays green even when the package is not installed.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import AsyncGenerator
from typing import Any, TypedDict, cast

import pytest

pytest.importorskip("pydantic_ai")  # noqa: E402

from jarvis import Jarvis
from jarvis.infrastructure.llm_perception import LlmPerception
from jarvis.infrastructure.provider_settings import ProviderSettings
from jarvis.infrastructure.pydantic_ai_model import PydanticAiModel


class _Claim(TypedDict, total=False):
    content: str
    supports: bool
    weight: float


def _pai(module: str) -> Any:
    """Import a pydantic-ai submodule lazily (guarded by the importorskip above)."""
    return cast(Any, importlib.import_module(module))


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


def _usage_model() -> Any:
    """A FunctionModel whose responses report token usage (Phase 5 bookkeeping)."""
    function_mod = _pai("pydantic_ai.models.function")
    run_usage = _pai("pydantic_ai.usage").RunUsage
    messages = _pai("pydantic_ai.messages")

    def function(messages_: Any, agent_info: Any) -> Any:
        del messages_, agent_info
        return messages.ModelResponse(
            parts=[messages.TextPart("hi")],
            usage=run_usage(request_tokens=7, response_tokens=3),
        )

    return function_mod.FunctionModel(function)


def _text_model(text: str) -> Any:
    function_mod = _pai("pydantic_ai.models.function")

    def function(messages: Any, agent_info: Any) -> Any:
        del messages, agent_info
        return _response(text=text)

    return function_mod.FunctionModel(function)


def _structured_model(claims: list[dict[str, Any]]) -> Any:
    function_mod = _pai("pydantic_ai.models.function")

    def function(messages: Any, agent_info: Any) -> Any:
        del messages
        tool_name = agent_info.output_tools[0].name
        return _response(
            tool_name=tool_name,
            tool_args=json.dumps({"response": claims}),
        )

    return function_mod.FunctionModel(function)


def _settings() -> ProviderSettings:
    return ProviderSettings(
        provider="pydantic",
        model="qwen2.5:7b",
        base_url="http://localhost:11434/v1",
    )


class TestComplete:
    def test_plain_text_output_passes_through(self) -> None:
        model = PydanticAiModel(_settings(), model=_text_model("hello from the model"))
        assert model.complete("hi") == "hello from the model"

    def test_structured_output_comes_back_as_json(self) -> None:
        claims = [{"content": "revenue grew", "supports": True, "weight": 0.9}]
        model = PydanticAiModel(
            _settings(),
            instructions="extract claims",
            output_type=list[_Claim],
            model=_structured_model(claims),
        )
        raw = model.complete("observe")
        assert json.loads(raw) == claims

    def test_construction_from_real_settings_is_lazy_and_offline(self) -> None:
        # Building the adapter must not touch the network nor import pydantic-ai.
        model = PydanticAiModel(_settings())
        assert model is not None

    def test_unreadable_structured_reply_is_honest_silence(self) -> None:
        # A reply that fails schema validation (content is not a string) -> "",
        # never a fabricated reading (Vision §37).
        bad = [{"content": 123, "supports": True, "weight": 0.5}]
        model = PydanticAiModel(
            _settings(),
            instructions="extract claims",
            output_type=list[_Claim],
            model=_structured_model(bad),
        )
        assert model.complete("observe") == ""

    def test_a_provider_error_is_honest_silence(self) -> None:
        function_mod = _pai("pydantic_ai.models.function")

        def boom(messages: Any, agent_info: Any) -> Any:
            del messages, agent_info
            raise RuntimeError("provider exploded")

        model = PydanticAiModel(_settings(), model=function_mod.FunctionModel(boom))
        assert model.complete("hi") == ""


class TestStream:
    def test_it_streams_text_deltas(self) -> None:
        function_mod = _pai("pydantic_ai.models.function")

        async def stream_function(messages: Any, agent_info: Any) -> AsyncGenerator[str]:
            del messages, agent_info
            yield "alpha "
            yield "beta"

        fake = function_mod.FunctionModel(stream_function=stream_function)
        model = PydanticAiModel(_settings(), model=fake)
        assert "".join(model.stream("hi")) == "alpha beta"

    def test_a_stream_error_yields_nothing(self) -> None:
        function_mod = _pai("pydantic_ai.models.function")

        async def stream_function(messages: Any, agent_info: Any) -> AsyncGenerator[str]:
            del messages, agent_info
            raise RuntimeError("stream exploded")
            yield ""  # pragma: no cover

        fake = function_mod.FunctionModel(stream_function=stream_function)
        model = PydanticAiModel(_settings(), model=fake)
        assert list(model.stream("hi")) == []


class TestUsage:
    def test_complete_accounts_for_the_run(self) -> None:
        model = PydanticAiModel(_settings(), model=_usage_model())
        model.complete("hi")
        assert model.usage().total_tokens == 10
        assert model.usage().request_tokens == 7
        assert model.usage().response_tokens == 3

    def test_usage_accumulates_across_calls(self) -> None:
        model = PydanticAiModel(_settings(), model=_usage_model())
        model.complete("hi")
        model.complete("again")
        assert model.usage().total_tokens == 20

    def test_a_failed_run_accounts_for_nothing(self) -> None:
        function_mod = _pai("pydantic_ai.models.function")

        def boom(messages: Any, agent_info: Any) -> Any:
            del messages, agent_info
            raise RuntimeError("provider exploded")

        model = PydanticAiModel(_settings(), model=function_mod.FunctionModel(boom))
        model.complete("hi")
        assert model.usage().total_tokens == 0

    def test_stream_accounts_defensively(self) -> None:
        # A stream_function-only model reports no usage; the accounting must still read
        # it cleanly as zero instead of crashing the stream.
        function_mod = _pai("pydantic_ai.models.function")

        async def stream_function(messages: Any, agent_info: Any) -> AsyncGenerator[str]:
            del messages, agent_info
            yield "alpha "
            yield "beta"

        fake = function_mod.FunctionModel(
            function=None, stream_function=stream_function
        )
        model = PydanticAiModel(_settings(), model=fake)
        pieces = list(model.stream("hi"))
        assert "".join(pieces) == "alpha beta"
        assert model.usage().total_tokens == 0


class TestEndToEndThroughPerception:
    def test_a_pydantic_ai_provider_feeds_perception_structured(self) -> None:
        claims = [{"content": "revenue grew", "supports": True, "weight": 0.9}]
        model = PydanticAiModel(
            _settings(),
            instructions="extract claims",
            output_type=list[_Claim],
            model=_structured_model(claims),
        )
        jarvis = Jarvis(perception=LlmPerception(model))

        belief = jarvis.perceive("the quarterly note").working_belief
        assert belief is not None
        assert belief.confidence.value > 0.0