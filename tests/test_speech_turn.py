"""The one-call spoken turn: `/api/speech/turn` riding the session ReasoningSpan.

A live-ear console records audio, the ear turns it into text (`/api/speech/transcribe`
or a `final=1` close of `/api/speech/stream`), and the final transcript used to come
back as *another* browser round-trip (`converse(text)`). Roadmap F6d makes the spoken
turn first-class server-side: `POST /api/speech/turn` runs the same conversation
pipeline as a typed `say` turn in one call, so a live-voice session keeps the session
ReasoningSpan exactly like typing does. Everything here is offline and deterministic
(D8): a scripted ear, a scripted reasoner, and the pure `route` contract.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import cast

from jarvis.domain.reasoning.reasoning_span import ThreadPosture
from jarvis.infrastructure.llm_reasoner import LlmReasoner
from jarvis.infrastructure.scripted_language_model import ScriptedLanguageModel
from jarvis.interface.command_center import route, snapshot
from jarvis.jarvis import Jarvis

_AUDIO = b"raw audio"


class _StubEar:
    """A scripted ear: text passes through, audio becomes a fixed transcript."""

    provider = "stub"
    model = "fake-audio"
    can_hear_audio = True
    can_stream_partials = True

    def transcribe(self, utterance: str) -> str:
        return utterance

    def transcribe_audio(self, audio: bytes) -> str:
        return "¿cuánto costaría la migración?" if audio else ""

    def stream_transcribe(self, chunks: Iterable[bytes]) -> Iterator[str]:
        pending = b""
        last = ""
        for chunk in chunks:
            pending += chunk
            if not pending:
                continue
            partial = self.transcribe_audio(pending).strip()
            if partial and partial != last:
                last = partial
                yield partial


def _talking_jarvis() -> Jarvis:
    """A Jarvis that hears through a live ear and reasons with a scripted model."""
    return Jarvis(
        reasoner=LlmReasoner(ScriptedLanguageModel(default="a")),
        speech_perception=_StubEar(),
    )


def _turn(jarvis: Jarvis, text: str):
    """POST one spoken turn through the pure route contract."""
    body = json.dumps({"text": text}).encode()
    return route(jarvis, "POST", "/api/speech/turn", body)


class TestSpokenTurnServerSide:
    def test_a_spoken_turn_is_a_say_turn_server_side(self) -> None:
        jarvis = _talking_jarvis()
        response = _turn(jarvis, "¿cambio la arquitectura?")
        assert response.status == 200
        assert response.content_type == "application/json; charset=utf-8"
        payload = cast(dict[str, object], json.loads(response.body))
        assert str(payload["reply"])
        assert "state" in payload  # one round-trip carries the live control center
        threads = jarvis.reasoning_span()
        assert [thread.trigger for thread in threads] == ["¿cambio la arquitectura?"]
        assert threads[0].posture is ThreadPosture.ACTIVE

    def test_the_span_carries_across_two_spoken_turns(self) -> None:
        jarvis = _talking_jarvis()
        _turn(jarvis, "¿cambio la arquitectura?")
        _turn(jarvis, "¿cuánto costaría?")
        threads = jarvis.reasoning_span()
        assert [t.trigger for t in threads] == [
            "¿cuánto costaría?",
            "¿cambio la arquitectura?",
        ]
        assert threads[0].posture is ThreadPosture.ACTIVE
        assert threads[1].posture is ThreadPosture.MOVED_ON

    def test_the_span_rides_the_actual_stt_transcript(self) -> None:
        jarvis = _talking_jarvis()
        # The ear's *audio* path produces the transcript (the live-voice session),
        # and that text then rides the span server-side as one spoken turn.
        text = jarvis.transcribe(_AUDIO)
        assert text == "¿cuánto costaría la migración?"
        response = _turn(jarvis, text)
        assert response.status == 200
        threads = jarvis.reasoning_span()
        assert [thread.trigger for thread in threads] == ["¿cuánto costaría la migración?"]
        assert threads[0].posture is ThreadPosture.ACTIVE

    def test_a_missing_ear_is_a_clean_400_and_never_runs_the_pipeline(self) -> None:
        jarvis = Jarvis()
        response = _turn(jarvis, "¿cambio la arquitectura?")
        assert response.status == 400
        assert b"set_speech_perception" in response.body
        # The conversation pipeline never ran: no turn was recorded, no span step.
        assert jarvis.reasoning_span() == ()
        assert jarvis.conversation.is_empty()

    def test_empty_text_is_a_graceful_ack_without_a_span_step(self) -> None:
        jarvis = _talking_jarvis()
        response = _turn(jarvis, "   ")
        assert response.status == 200
        payload = cast(dict[str, object], json.loads(response.body))
        assert "I'm here" in str(payload["reply"])
        assert payload["speak"] is False
        assert jarvis.reasoning_span() == ()

    def test_a_failing_reasoner_never_turns_a_turn_into_a_500(self) -> None:
        class _RaisingModel:
            def complete(self, prompt: str) -> str:
                raise RuntimeError("provider down")

        jarvis = Jarvis(reasoner=LlmReasoner(_RaisingModel()), speech_perception=_StubEar())
        response = _turn(jarvis, "¿cambio la arquitectura?")
        assert response.status == 200
        payload = cast(dict[str, object], json.loads(response.body))
        assert str(payload["reply"]).strip()  # a graceful reply, not a crashed request
        assert jarvis.reasoning_span() == ()  # the failed reasoner advanced nothing


class TestSpokenTurnSnapshot:
    def test_the_speech_block_advertises_the_turn_endpoint(self) -> None:
        jarvis = _talking_jarvis()
        block = cast(dict[str, object], snapshot(jarvis)["speech"])
        assert block["turn_endpoint"] == "/api/speech/turn"

    def test_a_closed_ear_still_advertises_an_honest_turn_endpoint(self) -> None:
        block = cast(dict[str, object], snapshot(Jarvis())["speech"])
        assert block["live"] is False
        assert block["turn_endpoint"] == "/api/speech/turn"