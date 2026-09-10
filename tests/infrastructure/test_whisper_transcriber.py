"""WhisperTranscriber talks to an OpenAI-compatible /audio/transcriptions endpoint.

Offline: a fake transport captures the request and fakes the response, so nothing
here touches the network (D8). Registry tests cover provider selection.
"""

from __future__ import annotations

import json

import pytest

from jarvis.infrastructure.provider_settings import SttSettings
from jarvis.infrastructure.speech_perception import EchoSpeechPerception
from jarvis.infrastructure.speech_perception_registry import (
    build_speech_perception,
    register_endpoint,
)
from jarvis.infrastructure.whisper_transcriber import WhisperTranscriber

_AUDIO = b"RIFF\x00\x00\x00\x00WAVEfmt "

_SENT: list[tuple[str, dict[str, str], bytes]] = []


def _fake_transport(url: str, headers: dict[str, str], body: bytes) -> str:
    _SENT.append((url, headers, body))
    return json.dumps({"text": "hola, mundo"})


class TestWhisperTranscriber:
    def test_a_base_url_is_required(self) -> None:
        with pytest.raises(ValueError):
            WhisperTranscriber(
                SttSettings(provider="openai", model="whisper-1", base_url=None)
            )

    def test_audio_becomes_a_multipart_request_to_audio_transcriptions(self) -> None:
        target = SttSettings(
            provider="openai",
            model="whisper-1",
            base_url="https://api.openai.com/v1",
        )
        ear = WhisperTranscriber(target, transport=_fake_transport)
        text = ear.transcribe_audio(_AUDIO)

        assert text == "hola, mundo"
        sent_url, headers, body = _SENT[-1]
        assert sent_url == ear.endpoint
        assert headers["Content-Type"].startswith("multipart/form-data; boundary=")
        assert b'name="model"' in body and b"whisper-1" in body
        assert b'name="file"; filename="input.wav"' in body
        assert _AUDIO in body

    def test_an_api_key_is_sent_as_a_bearer_token(self) -> None:
        ear = WhisperTranscriber(
            SttSettings(
                provider="groq",
                model="whisper-large-v3",
                base_url="https://api.groq.com/openai/v1",
                api_key="gsk_secret",
            ),
            transport=_fake_transport,
        )
        ear.transcribe_audio(_AUDIO)
        assert _SENT[-1][1]["Authorization"] == "Bearer gsk_secret"

    def test_a_keyless_engine_sends_no_authorization_header(self) -> None:
        ear = WhisperTranscriber(
            SttSettings(
                provider="openai-compatible",
                model="whisper-1",
                base_url="http://localhost:9000/v1",
            ),
            transport=_fake_transport,
        )
        ear.transcribe_audio(_AUDIO)
        assert "Authorization" not in _SENT[-1][1]

    def test_silent_when_the_response_has_no_text(self) -> None:
        def silent(url: str, headers: dict[str, str], body: bytes) -> str:
            return json.dumps({"not_text": True})

        ear = WhisperTranscriber(
            SttSettings(provider="openai", model="whisper-1", base_url="https://x/v1"),
            transport=silent,
        )
        assert ear.transcribe_audio(_AUDIO) == ""

    def test_the_text_path_is_out_of_reach(self) -> None:
        ear = WhisperTranscriber(
            SttSettings(provider="openai", model="whisper-1", base_url="https://x/v1"),
            transport=_fake_transport,
        )
        assert ear.transcribe("already transcribed") == ""

    def test_a_live_ear_describes_itself(self) -> None:
        ear = WhisperTranscriber(
            SttSettings(
                provider="groq",
                model="whisper-large-v3",
                base_url="https://api.groq.com/openai/v1",
            ),
            transport=_fake_transport,
        )
        assert ear.can_hear_audio is True
        assert ear.provider == "groq"
        assert ear.model == "whisper-large-v3"

    def test_transcription_errors_stay_loud(self) -> None:
        def refusing(url: str, headers: dict[str, str], body: bytes) -> str:
            raise RuntimeError("401 unauthorized")

        ear = WhisperTranscriber(
            SttSettings(provider="openai", model="whisper-1", base_url="https://x/v1"),
            transport=refusing,
        )
        with pytest.raises(RuntimeError):
            ear.transcribe_audio(_AUDIO)


class TestRegistry:
    def test_default_builds_the_offline_echo_ear(self) -> None:
        ear = build_speech_perception(
            SttSettings(provider="echo", model="")
        )
        assert isinstance(ear, EchoSpeechPerception)
        assert ear.can_hear_audio is False
        assert ear.provider == "echo"
        assert ear.model == ""

    def test_an_offline_provider_never_requires_a_model(self) -> None:
        for provider in ("echo", "stub", "scripted"):
            ear = build_speech_perception(SttSettings(provider=provider, model=""))
            assert isinstance(ear, EchoSpeechPerception)

    def test_known_endpoint_providers_build_a_whisper_transcriber(self) -> None:
        provider = build_speech_perception(
            SttSettings(provider="openai", model="whisper-1", api_key="k")
        )
        assert isinstance(provider, WhisperTranscriber)
        assert provider.endpoint == "https://api.openai.com/v1/audio/transcriptions"

    def test_base_url_overrides_the_default_endpoint(self) -> None:
        provider = build_speech_perception(
            SttSettings(
                provider="openai-compatible",
                model="whisper-1",
                base_url="http://localhost:9000/v1",
            )
        )
        assert isinstance(provider, WhisperTranscriber)
        assert provider.endpoint == "http://localhost:9000/v1/audio/transcriptions"

    def test_an_unknown_provider_is_a_clear_error(self) -> None:
        with pytest.raises(ValueError):
            build_speech_perception(
                SttSettings(provider="boombox", model="whisper-1")
            )

    def test_a_custom_endpoint_registers_like_the_llm_registry(self) -> None:
        register_endpoint("localwhisper", "http://localhost:8000/v1")
        provider = build_speech_perception(
            SttSettings(provider="localwhisper", model="whisper-1")
        )
        assert isinstance(provider, WhisperTranscriber)
        assert provider.endpoint == "http://localhost:8000/v1/audio/transcriptions"