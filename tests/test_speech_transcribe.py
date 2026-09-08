"""The live STT path: Jarvis.transcribe(audio) and its command-center endpoint."""

from __future__ import annotations

from jarvis import Jarvis
from jarvis.interface.command_center import route


class _StubEar:
    """A scripted ear: text passes through, audio becomes a fixed transcript."""

    def transcribe(self, utterance: str) -> str:
        return utterance

    def transcribe_audio(self, audio: bytes) -> str:
        return "hola, mundo" if audio else ""


class _BrokenEar:
    def transcribe(self, utterance: str) -> str:
        return utterance

    def transcribe_audio(self, audio: bytes) -> str:
        raise RuntimeError("401 unauthorized")


class TestJarvisTranscribe:
    def test_transcribing_without_an_ear_is_a_clear_error(self) -> None:
        jarvis = Jarvis()
        try:
            jarvis.transcribe(b"some audio")
        except RuntimeError as error:
            assert "set_speech_perception" in str(error)
            return
        raise AssertionError("transcribing without an ear must raise")

    def test_transcribe_routes_audio_to_the_live_ear(self) -> None:
        jarvis = Jarvis(speech_perception=_StubEar())
        assert jarvis.transcribe(b"raw audio") == "hola, mundo"

    def test_the_echo_ear_cannot_hear_raw_audio(self) -> None:
        from jarvis.infrastructure.speech_perception import EchoSpeechPerception

        jarvis = Jarvis(speech_perception=EchoSpeechPerception())
        assert jarvis.transcribe(b"raw audio") == ""

    def test_transcribing_flips_no_capability_when_none_is_wired(self) -> None:
        jarvis = Jarvis()
        assert not jarvis.can_do("perceive speech")


class TestTranscribeEndpoint:
    def test_audio_in_text_out(self) -> None:
        jarvis = Jarvis(speech_perception=_StubEar())
        response = route(jarvis, "POST", "/api/speech/transcribe", b"raw audio")
        assert response.status == 200
        assert b'"hola, mundo"' in response.body

    def test_a_missing_ear_is_a_clean_400(self) -> None:
        response = route(Jarvis(), "POST", "/api/speech/transcribe", b"raw audio")
        assert response.status == 400
        assert b"set_speech_perception" in response.body

    def test_a_failing_provider_is_a_structured_502(self) -> None:
        jarvis = Jarvis(speech_perception=_BrokenEar())
        response = route(jarvis, "POST", "/api/speech/transcribe", b"raw audio")
        assert response.status == 502
        assert b"401 unauthorized" in response.body