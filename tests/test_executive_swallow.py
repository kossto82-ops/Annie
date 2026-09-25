"""The executive error path speaks, never swallows (roadmap F7).

The broad-``except`` audit (Increment 181) pinned the boundary contract at
``jarvis/interface/_conversation.py:269``: a crash inside the reasoner or the
rest of the `say` pipeline returns an honest, loud ``provider_error`` message
(Vision §37) — it must never be swallowed into a fake-success or an empty
``""`` reply. The guardrail (Increment 157) is the *other* honest signal and
stays untouched: a recognised provider *refusal* becomes ``""``, while a
provider *failure* becomes a non-empty diagnostic. This test pins both signals
and the empty-turn calm default that a swallowed crash could otherwise mimic.
"""

from __future__ import annotations

from typing import Any

import pytest

from jarvis import Jarvis
from jarvis.infrastructure.guardrail import guard_reply
from jarvis.interface import _conversation
from jarvis.interface._shared import provider_error
from jarvis.interface.command_center import handle, stream_say


class _ProviderCrash(Exception):
    """An HTTP-style provider failure: ``code`` is what ``provider_error`` reads."""

    code: int = 401


def _boom(jarvis: Jarvis, text: str) -> dict[str, object]:
    raise _ProviderCrash("model refused the request")


def _reason_boom(self: object, text: str, **_: object) -> Any:
    raise _ProviderCrash("model refused the request")


def test_a_reasoner_failure_is_loud_not_a_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The realistic path (Increment 153 reasoner seam): the model call inside
    # _knowledge_reply raises; the say boundary must surface it, not reply.
    monkeypatch.setattr(Jarvis, "reason", _reason_boom, raising=False)
    result = handle(Jarvis(), "say", {"text": "¿cuándo será la entrega?"})
    reply = str(result["reply"])
    assert reply
    assert "authorization failed" in reply
    assert result.get("speak") is True
    assert reply != "I'm here — tell me something, or ask."


def test_the_executive_boundary_never_swallows_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_conversation, "_say_core", _boom, raising=False)
    result = handle(Jarvis(), "say", {"text": "resume lo que viste ayer"})
    assert str(result["reply"]) == provider_error(_ProviderCrash("boom"))
    assert str(result["reply"]) != ""


def test_an_empty_turn_is_the_calm_default_not_a_swallowed_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_conversation, "_say_core", _boom, raising=False)
    result = handle(Jarvis(), "say", {"text": "   "})
    assert str(result["reply"]) == "I'm here — tell me something, or ask."
    assert result.get("speak") is False


def test_crash_and_refusal_are_distinct_honest_signals() -> None:
    # Increment 157's refusal guardrail is the silent honest signal; the failure
    # path is the loud one. Neither may turn into the other.
    assert guard_reply("I'm sorry, but I can't help with that.") == ""
    assert provider_error(_ProviderCrash("model declined")) != ""


def test_the_streamed_boundary_ends_in_one_done_event_on_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_conversation, "_say_core", _boom, raising=False)
    events = list(stream_say(Jarvis(), {"text": "cuéntame del proyecto"}))
    assert len(events) == 1
    name, data = events[0]
    assert name == "done"
    assert data["reply"]
    assert data["speak"] is True


def test_a_non_provider_executive_crash_is_still_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _panic(jarvis: Jarvis, text: str) -> dict[str, Any]:
        raise RuntimeError("integration bug")

    monkeypatch.setattr(_conversation, "_say_core", _panic, raising=False)
    result = handle(Jarvis(), "say", {"text": "¿qué sabes de la migración?"})
    reply = str(result["reply"])
    assert reply and "language model" in reply