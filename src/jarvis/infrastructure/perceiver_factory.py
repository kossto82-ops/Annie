"""Build and describe a PerceptionSource by provider name (Vision §32, §38; Track B).

The choice of perceiver -- the dumb offline keyword rule, or a real LLM behind the
same seam -- is config, and it is selectable at runtime from the command center. This
module is the one place that maps a provider name to a `PerceptionSource` and, in the
other direction, describes a live perceiver for a surface to display.

The epistemic boundary holds: whatever is built only *produces evidence*; confidence
is still derived downstream and the executive still decides (Vision §38).

The secret stays in the environment. `build_perceiver` (what the UI calls) takes only
a provider, model, and optional endpoint from the page; the API key is read from
`JARVIS_LLM_API_KEY` and never travels over the wire from the browser. Building only
constructs an adapter -- no network call happens until an observation is perceived.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import cast

from jarvis.domain.perception.companion_perception import CompanionPerceptionSource
from jarvis.domain.perception.perception_source import PerceptionSource
from jarvis.domain.reasoning.reasoner import Reasoner
from jarvis.infrastructure.keyword_perception import KeywordPerception
from jarvis.infrastructure.language_model_registry import available, build_language_model
from jarvis.infrastructure.llm_companion_perception import LlmCompanionPerception
from jarvis.infrastructure.llm_config_store import resolve_api_key, resolve_model
from jarvis.infrastructure.llm_perception import LlmPerception
from jarvis.infrastructure.llm_reasoner import LlmReasoner
from jarvis.infrastructure.llm_response_renderer import LlmResponseRenderer
from jarvis.infrastructure.openai_compatible_embedder import OpenAiCompatibleEmbedder
from jarvis.infrastructure.provider_settings import ProviderSettings
from jarvis.infrastructure.response_renderer import IdentityRenderer, ResponseRenderer
from jarvis.infrastructure.silent_companion_perception import SilentCompanionPerception
from jarvis.infrastructure.silent_reasoner import SilentReasoner
from jarvis.infrastructure.text_embedder import TextEmbedder

_PREFIX = "JARVIS_LLM_"
_EMBED_PREFIX = "JARVIS_EMBED_"
# Embeddings default to a local ollama, independent of the chat provider: you can chat
# with a hosted model and still recall by meaning with a local embedder (e.g. bge-m3).
_DEFAULT_EMBED_BASE_URL = "http://localhost:11434/v1"

# Provider names that mean "no LLM in the judgment": use the keyword rule (Vision §38).
KEYWORD = "keyword"
_OFFLINE: frozenset[str] = frozenset({"", KEYWORD, "scripted", "stub"})


def available_providers() -> tuple[str, ...]:
    """Every perceiver a surface can select: the keyword rule plus the real LLM
    providers from the open registry (the offline stubs are folded into ``keyword``).
    """
    real = tuple(p for p in available() if p not in _OFFLINE)
    return (KEYWORD, *real)


def saved_models(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Each provider's remembered model, so the UI can auto-fill the model field when
    you pick a provider (mirrors the per-provider key memory).
    """
    env = environ if environ is not None else os.environ
    prefix = f"{_PREFIX}MODEL_"
    return {
        name[len(prefix) :].lower(): value
        for name, value in env.items()
        if name.startswith(prefix) and value
    }


def describe(source: PerceptionSource) -> dict[str, str | None]:
    """Describe a live perceiver for the UI -- kind, provider, model.

    A perceiver that reports itself (`describe`) is trusted; anything else is labelled
    generically by its type, so a custom test double never breaks the surface.
    """
    reporter = getattr(source, "describe", None)
    if callable(reporter):
        described = reporter()
        if isinstance(described, dict):
            return cast("dict[str, str | None]", described)
    return {"kind": "custom", "provider": type(source).__name__, "model": None}


def perceiver_from_settings(settings: ProviderSettings) -> PerceptionSource:
    """The `PerceptionSource` for fully-formed settings (including any API key).

    An offline provider yields the keyword rule (no LLM); any other provider is an
    LLM-backed perceiver built through the open registry, tagged with its identity so
    the surface can name it.
    """
    if settings.provider in _OFFLINE:
        return KeywordPerception()
    if not settings.model:
        raise ValueError(
            f"a model id is required for provider {settings.provider!r} "
            "(e.g. llama-3.3-70b)"
        )
    model = build_language_model(settings)
    return LlmPerception(model, provider=settings.provider, model_name=settings.model)


def companion_perceiver_from_settings(
    settings: ProviderSettings,
) -> CompanionPerceptionSource:
    """The relational perceiver (Vision §5) for fully-formed settings.

    Offline -> silent (the dumb rule cannot read free utterances into traits); any real
    provider -> an LLM-backed companion perceiver over the same model as the world one.
    """
    if settings.provider in _OFFLINE:
        return SilentCompanionPerception()
    if not settings.model:
        raise ValueError(
            f"a model id is required for provider {settings.provider!r} "
            "(e.g. llama-3.3-70b)"
        )
    return LlmCompanionPerception(build_language_model(settings))


def renderer_from_settings(settings: ProviderSettings) -> ResponseRenderer:
    """The reply renderer (Vision §40) for fully-formed settings.

    Offline -> the identity renderer (canonical reply, unchanged); a real provider -> an
    LLM voice over the same model, so replies come back in the companion's language.
    """
    if settings.provider in _OFFLINE or not settings.model:
        return IdentityRenderer()
    return LlmResponseRenderer(build_language_model(settings))


def reasoner_from_settings(settings: ProviderSettings) -> Reasoner:
    """The reasoner (Vision §37) for fully-formed settings.

    Offline -> the silent reasoner (no inference; an unremembered question stays an
    honest "I don't have enough"); a real provider -> an LLM reasoner over the same
    model, so a provisional answer is reasoned when belief and memory have none.
    """
    if settings.provider in _OFFLINE or not settings.model:
        return SilentReasoner()
    return LlmReasoner(build_language_model(settings))


def build_embedder(environ: Mapping[str, str] | None = None) -> TextEmbedder | None:
    """Build the embedder for semantic recall from ``JARVIS_EMBED_*``, or None.

    Independent of the chat provider (Vision §3, D11): set ``JARVIS_EMBED_MODEL`` (e.g.
    ``bge-m3``) to enable meaning-based recall; the endpoint defaults to a local ollama.
    Absent model -> None -> recall stays lexical. Building only constructs the adapter;
    no network call happens until a recall embeds something.
    """
    env = environ if environ is not None else os.environ
    model = (env.get(f"{_EMBED_PREFIX}MODEL") or "").strip()
    if not model:
        return None
    base_url = (env.get(f"{_EMBED_PREFIX}BASE_URL") or _DEFAULT_EMBED_BASE_URL).strip()
    return OpenAiCompatibleEmbedder(
        base_url=base_url,
        model=model,
        api_key=(env.get(f"{_EMBED_PREFIX}API_KEY") or None),
        timeout=float(env.get(f"{_EMBED_PREFIX}TIMEOUT", "60")),
    )


def _settings_from_ui(
    provider: str, model: str, base_url: str | None, environ: Mapping[str, str] | None
) -> ProviderSettings:
    """Compose settings from the UI's non-secret choice, keying from the environment."""
    env = environ if environ is not None else os.environ
    name = provider.strip().lower()
    return ProviderSettings(
        provider=name,
        model=model.strip() or resolve_model(name, env),  # recall the remembered model
        base_url=(base_url or None),
        api_key=resolve_api_key(name, env),  # this provider's stored key
        timeout=float(env.get(f"{_PREFIX}TIMEOUT", "30")),
        temperature=float(env.get(f"{_PREFIX}TEMPERATURE", "0")),
        reasoning_effort=(env.get(f"{_PREFIX}REASONING_EFFORT") or None),
    )


def build_perceiver(
    provider: str,
    model: str = "",
    base_url: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> PerceptionSource:
    """Build a world perceiver from the UI's non-secret choice, keying it from the env.

    The page supplies only the provider, model, and (optional) endpoint. The API key,
    timeout, and temperature come from `JARVIS_LLM_*`, so the secret never leaves the
    environment. An offline provider needs no env at all.
    """
    name = provider.strip().lower()
    if name in _OFFLINE:
        return KeywordPerception()
    return perceiver_from_settings(_settings_from_ui(provider, model, base_url, environ))


def build_companion_perceiver(
    provider: str,
    model: str = "",
    base_url: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> CompanionPerceptionSource:
    """Build the relational perceiver from the UI's non-secret choice (Vision §5).

    Mirrors `build_perceiver`: offline -> silent; a real provider -> an LLM companion
    perceiver over the same model, with the key read from the environment only.
    """
    name = provider.strip().lower()
    if name in _OFFLINE:
        return SilentCompanionPerception()
    return companion_perceiver_from_settings(
        _settings_from_ui(provider, model, base_url, environ)
    )


def build_renderer(
    provider: str,
    model: str = "",
    base_url: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> ResponseRenderer:
    """Build the reply renderer from the UI's non-secret choice (Vision §40).

    Offline -> identity (canonical reply); a real provider -> an LLM voice over the same
    model, keyed from the environment only, so replies are phrased in the user's language.
    """
    name = provider.strip().lower()
    if name in _OFFLINE:
        return IdentityRenderer()
    return renderer_from_settings(_settings_from_ui(provider, model, base_url, environ))


def build_reasoner(
    provider: str,
    model: str = "",
    base_url: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> Reasoner:
    """Build the reasoner from the UI's non-secret choice (Vision §37).

    Offline -> silent (no inference); a real provider -> an LLM reasoner over the same
    model, keyed from the environment only, so a provisional answer comes from the same
    model that perceives and voices.
    """
    name = provider.strip().lower()
    if name in _OFFLINE:
        return SilentReasoner()
    return reasoner_from_settings(_settings_from_ui(provider, model, base_url, environ))
