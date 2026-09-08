"""WhisperTranscriber: a live speech-to-text ear (SpeechPerceptionSource, Vision §32).

One adapter for the family of providers that speak the OpenAI-compatible
``POST /audio/transcriptions`` REST API -- OpenAI Whisper and Groq's Whisper
serving among them, plus any ``openai-compatible`` endpoint with an explicit
base_url. The text path (browser Web Speech already transcribed it) is out of its
reach: ``transcribe`` returns '', and raw audio goes through ``transcribe_audio``.

The actual HTTP send is a ``Transport`` (a callable) so the network stays at the
edge and out of tests: the default uses the standard library (``urllib``, no
dependency); tests inject a fake transport and never touch the network. Whatever
the engine returns is only ever *text* here -- turning it into evidence, and never
into a decision, is the perceiver's job (Vision §38, D6).
"""

from __future__ import annotations

import json
from typing import Protocol

from jarvis.infrastructure.provider_settings import SttSettings


class AudioTransport(Protocol):
    """Sends a multipart POST and returns the response body as text."""

    def __call__(self, url: str, headers: dict[str, str], body: bytes) -> str:
        ...


def _urllib_audio_transport(
    url: str, headers: dict[str, str], body: bytes, timeout: float
) -> str:
    import urllib.request

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload: bytes = response.read()
    return payload.decode("utf-8")


def _build_multipart(model: str, audio: bytes) -> tuple[bytes, str]:
    """Build an ``audio/transcriptions`` multipart body and its boundary."""
    boundary = "jarvis-voice-boundary"
    parts: list[bytes] = []
    parts.append(b"--" + boundary.encode())  # the model field
    parts.append(b'Content-Disposition: form-data; name="model"\r\n\r\n' + model.encode())
    parts.append(b"--" + boundary.encode())  # the audio file field
    parts.append(
        b'Content-Disposition: form-data; name="file"; filename="input.wav"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n"
        + audio
    )
    parts.append(b"--" + boundary.encode() + b"--\r\n")
    return b"\r\n".join(parts), boundary


class WhisperTranscriber:
    """Talks to any OpenAI-compatible ``/audio/transcriptions`` endpoint."""

    def __init__(
        self,
        settings: SttSettings,
        transport: AudioTransport | None = None,
    ) -> None:
        if not settings.base_url:
            raise ValueError("an audio-transcriptions provider needs a base_url")
        self._settings = settings
        self._endpoint = settings.base_url.rstrip("/") + "/audio/transcriptions"
        self._transport: AudioTransport = transport or self._default_transport

    @property
    def endpoint(self) -> str:
        """The exact audio-transcriptions URL this ear posts to (for tests/wiring)."""
        return self._endpoint

    def _default_transport(self, url: str, headers: dict[str, str], body: bytes) -> str:
        return _urllib_audio_transport(url, headers, body, self._settings.timeout)

    def transcribe(self, utterance: str) -> str:
        """This ear cannot hear already-transcribed text -- it stays silent."""
        return ""

    def transcribe_audio(self, audio: bytes) -> str:
        """Transcribe ``audio`` through the configured engine, or '' when it is silent.

        Errors (a missing key, a refused request, an unknown model) propagate loud:
        a misconfigured ear is a configuration error, never a silent guess (Vision
        §37 requires honesty -- '' is only for audio the engine could not hear).
        """
        body, boundary = _build_multipart(self._settings.model, audio)
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        if self._settings.api_key:
            headers["Authorization"] = f"Bearer {self._settings.api_key}"
        response = self._transport(self._endpoint, headers, body)
        parsed = json.loads(response)
        return str(parsed.get("text", ""))