"""An open registry of language-model providers (Vision §32).

The choice of LLM is config, and it is *not* a closed list. Most providers -- big
and small, cloud and local -- speak the OpenAI chat API, so one generic adapter
plus a table of default endpoints covers them all, and adding another is a one-line
entry (or just a `base_url` on the settings). Anything exotic registers its own
factory. Nothing here calls a network; building a model only constructs it.

Known out of the box (all via the generic OpenAI-compatible adapter):
OpenAI, Groq, xAI/Grok, DeepSeek, Moonshot/Kimi, OpenRouter, Together, Mistral,
Perplexity, a local Ollama, a local LM Studio -- plus "openai-compatible" for any
other endpoint by `base_url`, and "scripted" (the offline stub, the default).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from jarvis.infrastructure.language_model import LanguageModel
from jarvis.infrastructure.openai_compatible_model import OpenAiCompatibleModel
from jarvis.infrastructure.provider_settings import ProviderSettings
from jarvis.infrastructure.scripted_language_model import ScriptedLanguageModel

# Provider name -> its default OpenAI-compatible endpoint. Extend freely; a user can
# always override with `ProviderSettings.base_url`, and reach any local SLM server.
_ENDPOINTS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "xai": "https://api.x.ai/v1",
    "grok": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "kimi": "https://api.moonshot.cn/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "together": "https://api.together.xyz/v1",
    "mistral": "https://api.mistral.ai/v1",
    "perplexity": "https://api.perplexity.ai",
    "ollama": "http://localhost:11434/v1",  # local SLM server
    "lmstudio": "http://localhost:1234/v1",  # local SLM server
}

ProviderFactory = Callable[[ProviderSettings], LanguageModel]

# Providers whose construction is not "generic OpenAI-compatible + a base_url".
_FACTORIES: dict[str, ProviderFactory] = {
    "scripted": lambda settings: ScriptedLanguageModel(),
    "stub": lambda settings: ScriptedLanguageModel(),
    "openai-compatible": lambda settings: OpenAiCompatibleModel(settings),
}


def register_endpoint(name: str, base_url: str) -> None:
    """Add (or override) an OpenAI-compatible provider by name and endpoint."""
    _ENDPOINTS[name] = base_url


def register_factory(name: str, factory: ProviderFactory) -> None:
    """Register a provider whose model is built by a custom factory."""
    _FACTORIES[name] = factory


def available() -> tuple[str, ...]:
    """Every provider name that can be built, sorted."""
    return tuple(sorted(set(_FACTORIES) | set(_ENDPOINTS)))


def build_language_model(settings: ProviderSettings) -> LanguageModel:
    """Build the `LanguageModel` for ``settings.provider`` — config, not code.

    A custom-factory provider is built by its factory; any endpoint provider is the
    generic OpenAI-compatible adapter pointed at its base_url. An unknown provider is
    a clear error, never a silent fallback that would hide a misconfiguration.
    """
    provider = settings.provider
    factory = _FACTORIES.get(provider)
    if factory is not None:
        return factory(settings)
    endpoint = settings.base_url or _ENDPOINTS.get(provider)
    if endpoint is not None:
        return OpenAiCompatibleModel(replace(settings, base_url=endpoint))
    raise ValueError(
        f"unknown language-model provider {provider!r}; "
        f"known providers: {', '.join(available())} "
        "(or use 'openai-compatible' with an explicit base_url)"
    )
