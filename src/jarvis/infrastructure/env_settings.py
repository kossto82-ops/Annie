"""Build a LanguageModel from environment variables (Vision §32).

The composition root -- and a later command center -- picks the provider without a
code change: read `JARVIS_LLM_*` from the environment and hand back a
`LanguageModel`. The secret lives ONLY in `JARVIS_LLM_API_KEY` (an env var), never
in code or the repo. With nothing set, the provider defaults to the offline
`scripted` stub, so importing/using this changes nothing until the developer opts
in.

    JARVIS_LLM_PROVIDER   e.g. "groq", "ollama", "openai-compatible"  (default "scripted")
    JARVIS_LLM_MODEL      e.g. "llama-3.3-70b-versatile"              (required for real providers)
    JARVIS_LLM_BASE_URL   optional endpoint override (needed for a bare "openai-compatible")
    JARVIS_LLM_API_KEY    bearer credential (omit for keyless local SLMs)
    JARVIS_LLM_TIMEOUT    seconds (default 30)
    JARVIS_LLM_TEMPERATURE  default 0
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from jarvis.infrastructure.language_model import LanguageModel
from jarvis.infrastructure.language_model_registry import build_language_model
from jarvis.infrastructure.provider_settings import ProviderSettings

_PREFIX = "JARVIS_LLM_"
_OFFLINE_PROVIDERS = frozenset({"scripted", "stub"})


def settings_from_env(environ: Mapping[str, str] | None = None) -> ProviderSettings:
    """Assemble `ProviderSettings` from `JARVIS_LLM_*`. Defaults to the offline stub."""
    env = environ if environ is not None else os.environ
    provider = env.get(f"{_PREFIX}PROVIDER", "scripted").strip() or "scripted"
    model = env.get(f"{_PREFIX}MODEL", "").strip()
    if provider not in _OFFLINE_PROVIDERS and not model:
        raise ValueError(
            f"{_PREFIX}MODEL is required for provider {provider!r} "
            f"(set it, e.g. {_PREFIX}MODEL=llama-3.3-70b-versatile)"
        )
    return ProviderSettings(
        provider=provider,
        model=model,
        base_url=(env.get(f"{_PREFIX}BASE_URL") or None),
        api_key=(env.get(f"{_PREFIX}API_KEY") or None),
        timeout=float(env.get(f"{_PREFIX}TIMEOUT", "30")),
        temperature=float(env.get(f"{_PREFIX}TEMPERATURE", "0")),
    )


def language_model_from_env(environ: Mapping[str, str] | None = None) -> LanguageModel:
    """Build the configured `LanguageModel` from the environment (the offline stub
    when nothing is configured).
    """
    return build_language_model(settings_from_env(environ))
