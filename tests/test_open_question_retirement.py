"""Open-question auto-retirement (roadmap F3): the loop closes conversationally.

Inc 170 opens a question when Jarvis cannot settle it; this closes it: once a
conversational turn *re-triggers* an open question and Jarvis holds a grounded
belief about it (confidence >= the grounded knob), the turn's answer retires the
question through the ordinary flow. An ungrounded re-ask ("I still wonder ...")
never retires -- only a grounded belief settles. The retire/echo surfaces are
explicit, and curiosity keeps proposing the oldest still-unsatisfied question.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.domain.value_objects.unresolved_item import UnresolvedStatus
from jarvis.interface.command_center import handle
from jarvis.jarvis import Jarvis

_Q = "why do the swallows return?"
_ANSWER = "the swallows return because the nights grow short"


def _open_question(jarvis: Jarvis) -> None:
    """The Inc-170 writer opens a question when a full question-think stays ungrounded."""
    episode = jarvis.think(_Q)
    assert episode.evidence_request is not None
    assert [i.question for i in jarvis.open_questions()] == [_Q]


class TestConversationAutoRetirement:
    def test_statement_answer_auto_retires_across_restart(self, tmp_path: Path) -> None:
        day_one = Jarvis.persistent(tmp_path)
        _open_question(day_one)

        day_two = Jarvis.persistent(tmp_path)
        assert [i.question for i in day_two.open_questions()] == [_Q]
        handle(day_two, "say", {"text": _ANSWER})

        assert day_two.open_questions() == ()
        history = {
            item.question: item for item in day_two.unresolved_history()
        }
        assert history[_Q].status is UnresolvedStatus.RESOLVED
        assert history[_Q].resolution == _ANSWER
        # The answer grounds as a real belief, so later reasoning reasons *with* it.
        assert any(
            "nights grow short" in piece.content
            for belief in day_two.beliefs.beliefs_about("swallows")
            for piece in belief.evidence
        )

    def test_ungrounded_rea_k_stays_open_the_grace_rule(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        _open_question(jarvis)

        # A re-ask that Jarvis cannot ground must NOT retire the question.
        handle(jarvis, "say", {"text": "I still wonder why do the swallows return?"})
        assert [i.question for i in jarvis.open_questions()] == [_Q]
        handle(jarvis, "say", {"text": _Q})
        assert [i.question for i in jarvis.open_questions()] == [_Q]

    def test_confirmation_grounds_the_echo_and_retires(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        _open_question(jarvis)
        reply = handle(jarvis, "say", {"text": "yes"})
        assert reply.get("stance") == "confirmation"
        assert jarvis.open_questions() == ()

    def test_confirming_a_pursued_question_retires_it(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        _open_question(jarvis)
        impulse = jarvis.feel_curious()
        assert impulse is not None and _Q in impulse.trigger
        jarvis.pursue(impulse)

        handle(jarvis, "say", {"text": "yes"})
        assert jarvis.open_questions() == ()
        history = {
            item.question: item for item in jarvis.unresolved_history()
        }
        assert history[_Q].status is UnresolvedStatus.RESOLVED


class TestRetirableOpenQuestions:
    def test_no_open_questions_matches_nothing(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        assert jarvis.retirable_open_questions("why do the swallows return?") == ()

    def test_no_grounded_answer_is_not_retirable(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        jarvis.think(_Q)  # opens the question; the faint answer stays below ground
        assert jarvis.retirable_open_questions("why do the swallows return?") == ()
        assert [i.question for i in jarvis.open_questions()] == [_Q]

    def test_unrelated_grounded_answers_are_not_retirable(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        jarvis.think(_Q)
        handle(jarvis, "say", {"text": "the kettle whistles at dawn"})
        # The turn re-triggers the question, but no *grounded belief* answers it.
        assert jarvis.retirable_open_questions("why do the swallows return?") == ()

    def test_a_turn_below_the_relevance_floor_does_not_retrigger(
        self, tmp_path: Path
    ) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        jarvis.think(_Q)
        unrelated = "the weather is nice today"
        handle(jarvis, "say", {"text": unrelated})
        assert jarvis.retirable_open_questions(unrelated) == ()
        assert [i.question for i in jarvis.open_questions()] == [_Q]

    def test_a_grounded_answer_is_retirable_with_the_companion_wording(
        self, tmp_path: Path
    ) -> None:
        from jarvis.domain.enums.evidence_source import EvidenceSource
        from jarvis.domain.value_objects.confidence import Confidence
        from jarvis.domain.value_objects.evidence import Evidence

        jarvis = Jarvis.persistent(tmp_path)
        jarvis.think(_Q)
        jarvis.think(
            _ANSWER,
            evidence=[
                Evidence(
                    content=_ANSWER,
                    source=EvidenceSource.USER_STATEMENT,
                    weight=Confidence(1.0),
                    supports=True,
                )
            ],
        )

        pairs = jarvis.retirable_open_questions("why do the swallows return?")
        assert len(pairs) == 1
        item, answer = pairs[0]
        assert item.question == _Q
        assert item.status is UnresolvedStatus.OPEN
        assert answer == _ANSWER


class TestQuestionSurfaces:
    def test_open_questions_lists_the_queue(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        jarvis.note_open_question(_Q)
        result = handle(jarvis, "open-questions", {})
        assert result["reply"]
        assert result["open_questions"] == [_Q]

    def test_settle_question_resolves_explicitly(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        jarvis.note_open_question(_Q)
        result = handle(
            jarvis,
            "settle-question",
            {"question": _Q, "resolution": _ANSWER},
        )
        assert str(result["reply"]).startswith("Settled:")
        assert jarvis.open_questions() == ()
        history = {
            item.question: item for item in jarvis.unresolved_history()
        }
        assert history[_Q].resolution == _ANSWER

    def test_settle_question_requires_a_resolution(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        jarvis.note_open_question(_Q)
        result = handle(jarvis, "settle-question", {"question": _Q})
        assert "resolution" in str(result["error"])
        assert [i.question for i in jarvis.open_questions()] == [_Q]

    def test_settle_question_refuses_an_unknown_question(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        jarvis.note_open_question(_Q)
        result = handle(
            jarvis, "settle-question", {"question": "never asked", "resolution": "nope"}
        )
        assert "no open question" in str(result["error"])
        assert [i.question for i in jarvis.open_questions()] == [_Q]

    def test_open_questions_surface_in_the_state_snapshot(self, tmp_path: Path) -> None:
        from typing import cast

        jarvis = Jarvis.persistent(tmp_path)
        jarvis.note_open_question(_Q)
        result = handle(jarvis, "open-questions", {})
        state = cast("dict[str, object]", result["state"])
        memory = cast("dict[str, object]", state["memory"])
        assert cast("list[str]", memory["open_questions"]) == [_Q]


class TestCuriosityOldestStillUnsatisfied:
    def test_curiosity_proposes_the_oldest_then_the_next_after_retirement(
        self, tmp_path: Path
    ) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        jarvis.note_open_question(_Q)
        jarvis.note_open_question("why does the wind turn?")

        impulse = jarvis.feel_curious()
        assert impulse is not None and "why do the swallows return?" in impulse.trigger

        jarvis.resolve_open_question(_Q, _ANSWER)
        remaining = jarvis.open_questions()
        assert [i.question for i in remaining] == ["why does the wind turn?"]

        next_impulse = jarvis.feel_curious()
        assert next_impulse is not None and "why does the wind turn?" in next_impulse.trigger