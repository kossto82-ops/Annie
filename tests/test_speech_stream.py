"""F5: the live-voice streaming contract — seam flag, partial assembly, endpoint.

The streaming ear has an offline, provider-agnostic shape: ``can_stream_partials``
is the feature-detect and ``stream_transcribe(chunks)`` yields the *new* growing
partial exactly once per committed chunk. Nothing here touches the network: the
Whisper transcribing is driven by a scripted transport (D8), the endpoint is
routed in-process, and the snapshot is read off a real fresh Jarvis.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator

import pytest

from jarvis import Jarvis
from jarvis.infrastructure.provider_settings import SttSettings
from jarvis.infrastructure.speech_perception import EchoSpeechPerception
from jarvis.infrastructure.whisper_transcriber import WhisperTranscriber
from jarvis.interface.command_center import route

_AUDIO = b"RIFF\x00\x00\x00\x00WAVEfmt "


class _GrowingTransport:
    """Returns one scripted transcript per POST, recording what was sent."""

    def __init__(self, transcripts: list[str]) -> None:
        self._transcripts = list(transcripts)
        self.sent: list[bytes] = []

    def __call__(self, url: str, headers: dict[str, str], body: bytes) -> str:
        self.sent.append(body)
        return json.dumps({"text": self._transcripts.pop(0)})


class _StreamingEar:
    """A live ear that streams: one growing partial per audio chunk."""

    provider = "fake"
    model = "stream"
    can_hear_audio = True
    can_stream_partials = True

    def transcribe(self, utterance: str) -> str:
        return utterance

    def transcribe_audio(self, audio: bytes) -> str:
        return "hola, mundo" if audio else ""

    def stream_transcribe(self, chunks: Iterable[bytes]) -> Iterator[str]:
        for chunk in chunks:
            if chunk:
                yield "hola, mundo"


def _ear(transcripts: list[str]) -> WhisperTranscriber:
    return WhisperTranscriber(
        SttSettings(
            provider="openai",
            model="whisper-1",
            base_url="https://api.openai.com/v1",
        ),
        transport=_GrowingTransport(transcripts),
    )


class TestStreamingSeamContract:
    def test_the_echo_ear_cannot_stream_and_stays_silent(self) -> None:
        ear = EchoSpeechPerception()
        assert ear.can_stream_partials is False
        assert list(ear.stream_transcribe([_AUDIO])) == []

    def test_a_whisper_ear_reports_the_streaming_flag(self) -> None:
        assert _ear(["hola"]).can_stream_partials is True

    def test_the_protocol_feature_detects_both_ears(self) -> None:
        from jarvis.domain.perception.speech_perception import SpeechPerceptionSource

        assert isinstance(EchoSpeechPerception(), SpeechPerceptionSource)
        assert isinstance(_ear(["hola"]), SpeechPerceptionSource)


class TestPartialAssembly:
    def test_partials_grow_with_the_accumulated_audio(self) -> None:
        transport = _GrowingTransport(["hola", "hola, mundo"])
        ear = WhisperTranscriber(
            SttSettings(
                provider="openai",
                model="whisper-1",
                base_url="https://x/v1",
            ),
            transport=transport,
        )
        partials = list(ear.stream_transcribe([b"seg1", b"seg2"]))
        # Each committed chunk extends the audio; each transcript of that truth
        # is yielded exactly once, in order.
        assert partials == ["hola", "hola, mundo"]
        assert len(transport.sent) == 2

    def test_a_flat_partial_is_never_repeated(self) -> None:
        ear = _ear(["hola", "hola"])
        assert list(ear.stream_transcribe([b"a", b"b"])) == ["hola"]

    def test_empty_chunks_produce_no_partials(self) -> None:
        ear = _ear([])  # the transport is never reached
        assert list(ear.stream_transcribe([b"", b""])) == []

    def test_one_preview_tick_yields_the_growing_partial(self) -> None:
        # The console's live-preview exchange posts the segment-so-far once.
        ear = _ear(["hola, mundo"])
        assert list(ear.stream_transcribe([_AUDIO])) == ["hola, mundo"]

    def test_a_streaming_ear_fails_loud_on_provider_errors(self) -> None:
        def refusing(url: str, headers: dict[str, str], body: bytes) -> str:
            raise RuntimeError("401 unauthorized")

        ear = WhisperTranscriber(
            SttSettings(provider="openai", model="whisper-1", base_url="https://x/v1"),
            transport=refusing,
        )
        with pytest.raises(RuntimeError):
            list(ear.stream_transcribe([_AUDIO]))


class TestJarvisStream:
    def test_transcribe_stream_routes_to_the_live_ear(self) -> None:
        class _GrowingEar(_StreamingEar):
            def stream_transcribe(self, chunks: Iterable[bytes]) -> Iterator[str]:
                for i, chunk in enumerate(chunks):
                    if chunk:
                        yield "hola, mundo" if i > 0 else "hola"

        jarvis = Jarvis(speech_perception=_GrowingEar())
        assert list(jarvis.transcribe_stream([b"a", b"b"])) == ["hola", "hola, mundo"]

    def test_transcribe_stream_without_an_ear_is_a_clear_error(self) -> None:
        jarvis = Jarvis()
        with pytest.raises(RuntimeError, match="set_speech_perception"):
            list(jarvis.transcribe_stream([_AUDIO]))


class TestStreamEndpoint:
    def test_audio_becomes_a_live_partial_exchange(self) -> None:
        jarvis = Jarvis(speech_perception=_StreamingEar())
        response = route(jarvis, "POST", "/api/speech/stream", _AUDIO)
        assert response.status == 200
        payload = json.loads(response.body)
        assert payload["final"] is False
        assert payload["partials"] == ["hola, mundo"]
        assert payload["text"] == "hola, mundo"

    def test_final_flush_closes_a_segment(self) -> None:
        jarvis = Jarvis(speech_perception=_StreamingEar())
        response = route(jarvis, "POST", "/api/speech/stream?final=1", _AUDIO)
        assert response.status == 200
        payload = json.loads(response.body)
        assert payload["final"] is True
        assert payload["text"] == "hola, mundo"

    def test_a_missing_ear_is_a_clean_400(self) -> None:
        response = route(Jarvis(), "POST", "/api/speech/stream", _AUDIO)
        assert response.status == 400
        assert b"set_speech_perception" in response.body

    def test_a_non_streaming_ear_is_an_honest_400(self) -> None:
        jarvis = Jarvis(speech_perception=EchoSpeechPerception())
        response = route(jarvis, "POST", "/api/speech/stream", _AUDIO)
        assert response.status == 400
        assert b"cannot stream partials" in response.body

    def test_a_failing_provider_is_a_structured_502(self) -> None:
        class _BrokenStreamingEar(_StreamingEar):
            def stream_transcribe(self, chunks: Iterable[bytes]) -> Iterator[str]:
                for _chunk in chunks:
                    raise RuntimeError("401 unauthorized")
                yield ""  # unreachable; keeps this a generator for the endpoint

        jarvis = Jarvis(speech_perception=_BrokenStreamingEar())
        response = route(jarvis, "POST", "/api/speech/stream", _AUDIO)
        assert response.status == 502
        assert b"401 unauthorized" in response.body


class TestStreamingSnapshot:
    def test_the_default_ear_keeps_web_speech_honestly(self) -> None:
        from typing import cast

        from jarvis.interface.command_center import snapshot

        block = cast(dict[str, object], snapshot(Jarvis())["speech"])
        assert block["live"] is False
        assert block["streaming"] is False
        assert block["stream_endpoint"] == "/api/speech/stream"

    def test_the_whisper_ear_reports_streaming_true(self) -> None:
        from typing import cast

        from jarvis.interface.command_center import snapshot

        jarvis = Jarvis(speech_perception=_StreamingEar())
        block = cast(dict[str, object], snapshot(jarvis)["speech"])
        assert block["live"] is True
        assert block["streaming"] is True