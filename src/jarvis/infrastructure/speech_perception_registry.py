"""An open registry of speech-to-text providers (Vision §32).

The choice of the ear is config, not a closed list. Most cloud STT engines -- big
and small -- speak the OpenAI-compatible ``POST /audio/transcriptions`` REST API
(OpenAI Whisper, Groq's Whisper serving, and anything reachable by an explicit
base_url), so one generic adapter plus a table of default endpoints covers them,
and adding another is a one-line entry (or just a ``base_url`` on the settings).
Nothing here calls a network; building a transcriber only constructs it.

Known out of the box: OpenAI Whisper and Groq (via the generic adapter), plus
"openai-compatible" for any other endpoint by ``base_url`` -- and "echo" (the
offline pass-through, the default), which returns already-transcribed text from
the browser's Web Speech API and cannot hear raw audio.
"""

from __future__ import annotations

from jarvis.domain.perception.speech_perception import SpeechPerceptionSource
from jarvis.infrastructure.provider_settings import SttSettings
from jarvis.infrastructure.speech_perception import EchoSpeechPerception
from jarvis.infrastructure.whisper_transcriber import WhisperTranscriber

# Provider name -> its default OpenAI-compatible base (audio transcriptions appended).
# Extend freely; a user can always override with `SttSettings.base_url`.
_ENDPOINTS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
}

# Payload-shaping is identical across whisper-compatible engines: model + base_url.
_OFFLINE_PROVIDERS = frozenset({"echo", "stub", "scripted"})


def register_endpoint(name: str, base_url: str) -> None:
    """Add (or override) a whisper-compatible provider by name and endpoint."""
    _ENDPOINTS[name] = base_url


def available() -> tuple[str, ...]:
    """Every provider name that can build an ear, sorted."""
    return tuple(sorted(set(_ENDPOINTS) | _OFFLINE_PROVIDERS | {"openai-compatible"}))


def build_speech_perception(settings: SttSettings) -> SpeechPerceptionSource:
    """Build the `SpeechPerceptionSource` for ``settings.provider`` -- config, not code.

    Offline providers (echo/stub/scripted) are the pass-through ear; an endpoint
    provider is the generic whisper-compatible adapter pointed at its base_url. An
    unknown provider is a clear error, never a silent fallback that would hide a
    misconfiguration.
    """
    provider = settings.provider
    if provider in _OFFLINE_PROVIDERS:
        return EchoSpeechPerception()
    base_url = settings.base_url or _ENDPOINTS.get(provider)
    if base_url is not None:
        return WhisperTranscriber(
            SttSettings(
                provider=provider,
                model=settings.model,
                base_url=base_url,
                api_key=settings.api_key,
                timeout=settings.timeout,
            )
        )
    raise ValueError(
        f"unknown speech-to-text provider {provider!r}; "
        f"known providers: {', '.join(available())} "
        "(or use 'openai-compatible' with an explicit base_url)"
    )