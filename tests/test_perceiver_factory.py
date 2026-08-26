"""The perceiver factory: build/describe a PerceptionSource by name, offline (§32, §38).

No network: building only constructs an adapter. The secret comes from the env, never
from the caller's provider/model choice.
"""

from __future__ import annotations

from jarvis.infrastructure.keyword_perception import KeywordPerception
from jarvis.infrastructure.llm_perception import LlmPerception
from jarvis.infrastructure.perceiver_factory import (
    available_providers,
    build_perceiver,
    describe,
)


class TestAvailableProviders:
    def test_it_offers_keyword_plus_real_providers(self) -> None:
        providers = available_providers()
        assert providers[0] == "keyword"
        assert "groq" in providers  # a registered real provider
        # the offline stubs are folded into "keyword", never offered separately
        assert "scripted" not in providers
        assert "stub" not in providers


class TestDescribe:
    def test_it_labels_the_keyword_rule(self) -> None:
        assert describe(KeywordPerception()) == {
            "kind": "keyword",
            "provider": "keyword",
            "model": None,
        }

    def test_it_labels_an_llm_perceiver_by_provider_and_model(self) -> None:
        source = build_perceiver("ollama", "llama-3.3-70b", environ={})
        assert describe(source) == {
            "kind": "llm",
            "provider": "ollama",
            "model": "llama-3.3-70b",
        }

    def test_a_bare_custom_source_is_labelled_generically(self) -> None:
        class _Silent:
            def perceive(self, observation: str) -> tuple[()]:
                return ()

        described = describe(_Silent())
        assert described["kind"] == "custom"
        assert described["provider"] == "_Silent"


class TestBuildPerceiver:
    def test_offline_names_yield_the_keyword_rule(self) -> None:
        for name in ("", "keyword", "scripted", "stub"):
            assert isinstance(build_perceiver(name, environ={}), KeywordPerception)

    def test_a_real_provider_yields_an_llm_perceiver_without_a_network_call(self) -> None:
        source = build_perceiver("groq", "llama-3.3-70b", environ={})
        assert isinstance(source, LlmPerception)

    def test_the_api_key_comes_only_from_the_environment(self) -> None:
        # No key in env, none from the caller -> a keyless perceiver still builds.
        source = build_perceiver("ollama", "qwen2.5", environ={})
        assert isinstance(source, LlmPerception)

    def test_a_real_provider_needs_a_model(self) -> None:
        try:
            build_perceiver("groq", "", environ={})
        except ValueError:
            return
        raise AssertionError("expected a ValueError for a real provider with no model")
