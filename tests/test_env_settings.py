"""Tests for building a LanguageModel from JARVIS_LLM_* (Vision §32) — no network."""

from __future__ import annotations

import pytest

from jarvis.infrastructure.env_settings import (
    language_model_from_env,
    openbot_settings_from_env,
    settings_from_env,
)
from jarvis.infrastructure.openai_compatible_model import OpenAiCompatibleModel
from jarvis.infrastructure.scripted_language_model import ScriptedLanguageModel


class TestSettingsFromEnv:
    def test_empty_environment_defaults_to_the_offline_stub(self) -> None:
        settings = settings_from_env({})
        assert settings.provider == "scripted"
        assert isinstance(language_model_from_env({}), ScriptedLanguageModel)

    def test_groq_is_configured_from_env(self) -> None:
        env = {
            "JARVIS_LLM_PROVIDER": "groq",
            "JARVIS_LLM_MODEL": "llama-3.3-70b-versatile",
            "JARVIS_LLM_API_KEY": "secret",
        }
        settings = settings_from_env(env)
        assert settings.provider == "groq"
        assert settings.model == "llama-3.3-70b-versatile"
        assert settings.api_key == "secret"
        assert isinstance(language_model_from_env(env), OpenAiCompatibleModel)

    def test_a_real_provider_without_a_model_is_a_clear_error(self) -> None:
        with pytest.raises(ValueError, match="JARVIS_LLM_MODEL is required"):
            settings_from_env({"JARVIS_LLM_PROVIDER": "groq"})

    def test_a_local_slm_needs_no_key(self) -> None:
        env = {"JARVIS_LLM_PROVIDER": "ollama", "JARVIS_LLM_MODEL": "llama3"}
        settings = settings_from_env(env)
        assert settings.api_key is None
        assert isinstance(language_model_from_env(env), OpenAiCompatibleModel)

    def test_timeout_and_temperature_are_read(self) -> None:
        settings = settings_from_env(
            {
                "JARVIS_LLM_PROVIDER": "scripted",
                "JARVIS_LLM_TIMEOUT": "12.5",
                "JARVIS_LLM_TEMPERATURE": "0.4",
            }
        )
        assert settings.timeout == 12.5
        assert settings.temperature == 0.4


class TestOpenBotSettingsFromEnv:
    def test_empty_environment_yields_none(self) -> None:
        assert openbot_settings_from_env({}) is None

    def test_enabled_with_endpoint_yields_settings(self) -> None:
        env = {
            "JARVIS_OPENBOT_ENABLED": "1",
            "JARVIS_OPENBOT_ENDPOINT": "http://localhost:4600",
        }
        s = openbot_settings_from_env(env)
        assert s is not None
        assert s.endpoint == "http://localhost:4600"
        assert s.agent_token is None
        assert s.timeout == 120.0

    def test_disabled_explicitly_yields_none(self) -> None:
        env = {
            "JARVIS_OPENBOT_ENABLED": "0",
            "JARVIS_OPENBOT_ENDPOINT": "http://x",
        }
        assert openbot_settings_from_env(env) is None

    def test_disabled_false_yields_none(self) -> None:
        env = {"JARVIS_OPENBOT_ENABLED": "false", "JARVIS_OPENBOT_ENDPOINT": "http://x"}
        assert openbot_settings_from_env(env) is None

    def test_endpoint_without_enabled_defaults_enabled(self) -> None:
        env = {"JARVIS_OPENBOT_ENDPOINT": "http://x"}
        s = openbot_settings_from_env(env)
        assert s is not None
        assert s.endpoint == "http://x"

    def test_trailing_slash_is_stripped(self) -> None:
        env = {"JARVIS_OPENBOT_ENDPOINT": "http://x:4600/"}
        s = openbot_settings_from_env(env)
        assert s is not None
        assert s.endpoint == "http://x:4600"

    def test_agent_token_is_read(self) -> None:
        env = {"JARVIS_OPENBOT_ENDPOINT": "http://x", "JARVIS_OPENBOT_AGENT_TOKEN": "secret"}
        s = openbot_settings_from_env(env)
        assert s is not None
        assert s.agent_token == "secret"

    def test_custom_timeout_is_read(self) -> None:
        env = {"JARVIS_OPENBOT_ENDPOINT": "http://x", "JARVIS_OPENBOT_TIMEOUT": "45"}
        s = openbot_settings_from_env(env)
        assert s is not None
        assert s.timeout == 45.0

    def test_empty_endpoint_yields_none(self) -> None:
        env = {"JARVIS_OPENBOT_ENDPOINT": ""}
        assert openbot_settings_from_env(env) is None

    def test_whitespace_only_endpoint_yields_none(self) -> None:
        env = {"JARVIS_OPENBOT_ENDPOINT": "   "}
        assert openbot_settings_from_env(env) is None
