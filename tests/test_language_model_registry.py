"""Tests for the open provider registry + generic adapter (Vision §32) — no network."""

from __future__ import annotations

import json

import pytest

from jarvis import Jarvis
from jarvis.infrastructure.language_model import LanguageModel
from jarvis.infrastructure.language_model_registry import (
    available,
    build_language_model,
    register_endpoint,
    register_factory,
)
from jarvis.infrastructure.llm_perception import LlmPerception
from jarvis.infrastructure.openai_compatible_model import OpenAiCompatibleModel
from jarvis.infrastructure.provider_settings import ProviderSettings
from jarvis.infrastructure.scripted_language_model import ScriptedLanguageModel


class _RecordingTransport:
    """A fake HTTP transport: records the request, returns a canned completion."""

    def __init__(self, content: str) -> None:
        self.url: str | None = None
        self.headers: dict[str, str] = {}
        self.body: bytes = b""
        self._content = content

    def __call__(self, url: str, headers: dict[str, str], body: bytes) -> str:
        self.url, self.headers, self.body = url, headers, body
        return json.dumps({"choices": [{"message": {"content": self._content}}]})


class TestRegistry:
    def test_the_stub_is_the_default_offline_provider(self) -> None:
        model = build_language_model(ProviderSettings(provider="scripted", model="none"))
        assert isinstance(model, ScriptedLanguageModel)
        assert isinstance(model, LanguageModel)

    def test_many_providers_are_known_out_of_the_box(self) -> None:
        names = available()
        for provider in ("groq", "grok", "deepseek", "kimi", "ollama", "lmstudio", "openrouter"):
            assert provider in names

    def test_a_known_provider_builds_the_generic_adapter(self) -> None:
        model = build_language_model(ProviderSettings(provider="groq", model="llama-3.3-70b"))
        assert isinstance(model, OpenAiCompatibleModel)

    def test_an_arbitrary_endpoint_needs_no_new_code(self) -> None:
        # A provider we never listed, reached purely by base_url.
        settings = ProviderSettings(
            provider="openai-compatible", model="my-model", base_url="https://example.test/v1"
        )
        assert isinstance(build_language_model(settings), OpenAiCompatibleModel)

    def test_a_local_slm_is_just_another_endpoint(self) -> None:
        model = build_language_model(ProviderSettings(provider="ollama", model="llama3"))
        assert isinstance(model, OpenAiCompatibleModel)

    def test_an_unknown_provider_is_a_clear_error(self) -> None:
        with pytest.raises(ValueError, match="unknown language-model provider"):
            build_language_model(ProviderSettings(provider="nope", model="x"))

    def test_new_endpoints_and_factories_can_be_registered(self) -> None:
        register_endpoint("acme", "https://acme.test/v1")
        assert "acme" in available()
        register_factory("myfake", lambda settings: ScriptedLanguageModel())
        assert isinstance(
            build_language_model(ProviderSettings(provider="myfake", model="x")),
            ScriptedLanguageModel,
        )


class TestOpenAiCompatibleModel:
    def test_it_builds_the_request_and_reads_the_reply(self) -> None:
        transport = _RecordingTransport("hello from the model")
        settings = ProviderSettings(
            provider="groq", model="llama-3.3-70b", base_url="https://api.groq.com/openai/v1",
            api_key="secret-key",
        )
        reply = OpenAiCompatibleModel(settings, transport=transport).complete("hi")

        assert reply == "hello from the model"
        assert transport.url == "https://api.groq.com/openai/v1/chat/completions"
        assert transport.headers["Authorization"] == "Bearer secret-key"
        sent = json.loads(transport.body)
        assert sent["model"] == "llama-3.3-70b"
        assert sent["messages"] == [{"role": "user", "content": "hi"}]

    def test_a_keyless_local_model_sends_no_auth_header(self) -> None:
        transport = _RecordingTransport("ok")
        settings = ProviderSettings(
            provider="ollama", model="llama3", base_url="http://localhost:11434/v1"
        )
        OpenAiCompatibleModel(settings, transport=transport).complete("hi")
        assert "Authorization" not in transport.headers

    def test_no_base_url_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="needs a base_url"):
            OpenAiCompatibleModel(ProviderSettings(provider="x", model="y"))


class TestEndToEndThroughPerception:
    def test_an_llm_provider_feeds_perception_without_a_network(self) -> None:
        claims = json.dumps([{"content": "revenue grew", "supports": True, "weight": 0.9}])
        transport = _RecordingTransport(claims)
        settings = ProviderSettings(
            provider="deepseek", model="deepseek-chat", base_url="https://api.deepseek.com/v1",
            api_key="k",
        )
        model = OpenAiCompatibleModel(settings, transport=transport)
        jarvis = Jarvis(perception=LlmPerception(model))

        belief = jarvis.perceive("the quarterly note").working_belief
        assert belief is not None
        assert belief.confidence.value > 0.0
