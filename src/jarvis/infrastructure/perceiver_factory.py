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

from jarvis.domain.perception.companion_perception import CompanionPerceptionSource
from jarvis.domain.perception.perception_source import PerceptionSource
from jarvis.infrastructure.keyword_perception import KeywordPerception
from jarvis.infrastructure.language_model_registry import available, build_language_model
from jarvis.infrastructure.llm_companion_perception import LlmCompanionPerception
from jarvis.infrastructure.llm_perception import LlmPerception
from jarvis.infrastructure.provider_settings import ProviderSettings
from jarvis.infrastructure.silent_companion_perception import SilentCompanionPerception

_PREFIX = "JARVIS_LLM_"

# Provider names that mean "no LLM in the judgment": use the keyword rule (Vision §38).
KEYWORD = "keyword"
_OFFLINE: frozenset[str] = frozenset({"", KEYWORD, "scripted", "stub"})


def available_providers() -> tuple[str, ...]:
    """Every perceiver a surface can select: the keyword rule plus the real LLM
    providers from the open registry (the offline stubs are folded into ``keyword``).
    """
    real = tuple(p for p in available() if p not in _OFFLINE)
    return (KEYWORD, *real)


def describe(source: PerceptionSource) -> dict[str, str | None]:
    """Describe a live perceiver for the UI -- kind, provider, model.

    A perceiver that reports itself (`describe`) is trusted; anything else is labelled
    generically by its type, so a custom test double never breaks the surface.
    """
    reporter = getattr(source, "describe", None)
    if callable(reporter):
        described = reporter()
        if isinstance(described, dict):
            return described
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


def _settings_from_ui(
    provider: str, model: str, base_url: str | None, environ: Mapping[str, str] | None
) -> ProviderSettings:
    """Compose settings from the UI's non-secret choice, keying from the environment."""
    env = environ if environ is not None else os.environ
    return ProviderSettings(
        provider=provider.strip().lower(),
        model=model.strip(),
        base_url=(base_url or None),
        api_key=(env.get(f"{_PREFIX}API_KEY") or None),
        timeout=float(env.get(f"{_PREFIX}TIMEOUT", "30")),
        temperature=float(env.get(f"{_PREFIX}TEMPERATURE", "0")),
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
