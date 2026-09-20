"""Episode Evidence-Request Writer v1 (gate tests A-E).

A COMPANION-origin, FULL-attention episode that concludes ungrounded and asks
for evidence ("does my companion prefer simplicity?", no grounding) leaves its
question in the unresolved store -- but only when the trigger reads as a question
and no identical question is already open. Echoes (CURIOSITY), probe routing
(BRIEF/CHEAP), grounded statements and statement-shaped triggers never write.
The write is epistemically inert over beliefs, evidence, confidence, semantic
memory, topic identity and the reasoning span.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from jarvis import Jarvis
from jarvis.domain.enums.deliberation_value import DeliberationValue
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence

_TRIGGER = "does my companion prefer simplicity?"
_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _ev(
    weight: float,
    *,
    supports: bool = True,
    content: str = "an observation",
    at: datetime | None = None,
) -> Evidence:
    kwargs: dict[str, object] = {
        "content": content,
        "source": EvidenceSource.USER_STATEMENT,
        "weight": Confidence(weight),
        "supports": supports,
    }
    if at is not None:
        kwargs["observed_at"] = at
    return Evidence(**kwargs)  # type: ignore[arg-type]


def _grounded_evidence() -> tuple[Evidence, ...]:
    """Evidence strong and time-spread enough to ground a conclusion."""
    return (
        _ev(0.9, content="a solid reason for it", at=_BASE),
        _ev(0.9, content="a second solid reason for it", at=_BASE + timedelta(days=30)),
    )


class TestWriterOccurrence:
    def test_an_ungrounded_question_shaped_episode_writes_one_item(
        self, tmp_path: Path
    ) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        episode = jarvis.think(_TRIGGER)
        assert episode.evidence_request is not None
        assert [i.question for i in jarvis.open_questions()] == [_TRIGGER]

        # An identical re-think is guarded (exact-string over OPEN items): still one.
        jarvis.think(_TRIGGER)
        assert [i.question for i in jarvis.open_questions()] == [_TRIGGER]

    def test_non_question_shaped_triggers_do_not_write(self) -> None:
        jarvis = Jarvis()
        episode = jarvis.think("an unfounded claim about submarines")
        # The conclusion still asks for evidence (it is ungrounded)...
        assert episode.evidence_request is not None
        # ...but the trigger does not read as a question, so nothing is persisted.
        assert jarvis.open_questions() == ()


class TestWriterExclusions:
    def test_an_undecided_deliberation_writes_nothing(self) -> None:
        jarvis = Jarvis()
        deliberation = jarvis.consider(
            "why did my companion go quiet?", {"they are busy": [], "they stopped": []}
        )
        assert deliberation.evidence_request is not None
        assert jarvis.open_questions() == ()

    def test_a_curiosity_echo_writes_nothing_new(self) -> None:
        jarvis = Jarvis()
        jarvis.note_open_question(_TRIGGER)
        impulse = jarvis.feel_curious()
        assert impulse is not None and "Investigate the open question" in impulse.trigger
        episode = jarvis.pursue(impulse)
        # The echo is itself ungrounded (it would, in isolation, request evidence)
        # but it is CURIOSITY-origin, so the predicate excludes it structurally.
        assert episode.origin is TriggerOrigin.CURIOSITY
        assert episode.evidence_request is not None
        assert [i.question for i in jarvis.open_questions()] == [_TRIGGER]

    def test_a_grounded_statement_writes_nothing(self) -> None:
        jarvis = Jarvis()
        episode = jarvis.think(_TRIGGER, evidence=_grounded_evidence())
        assert episode.evidence_request is None
        assert jarvis.open_questions() == ()

    def test_a_grounded_question_shaped_episode_writes_nothing(self) -> None:
        # Grounding excludes even a question-shaped trigger.
        jarvis = Jarvis()
        episode = jarvis.think(_TRIGGER, evidence=_grounded_evidence())
        assert episode.evidence_request is None
        assert jarvis.open_questions() == ()

    def test_a_cheap_ungrounded_completion_writes_nothing(self) -> None:
        # A CHEAP completion routes BRIEF (probe, not investigation) even when it
        # still attaches a request for evidence -- attention excludes it.
        jarvis = Jarvis()
        episode = jarvis.think(_TRIGGER, value=DeliberationValue.CHEAP)
        assert episode.attention is not None
        assert episode.evidence_request is not None
        assert jarvis.open_questions() == ()


class TestInvestigationEchoDoesNotRecurse:
    def test_investigating_an_item_never_creates_a_new_one(self) -> None:
        jarvis = Jarvis()
        jarvis.note_open_question(_TRIGGER)
        jarvis.pursue(jarvis.feel_curious())  # type: ignore[arg-type]
        questions = [i.question for i in jarvis.open_questions()]
        assert questions == [_TRIGGER]
        assert not any("Investigate" in question for question in questions)

    def test_a_think_written_item_is_investigable_once(self) -> None:
        jarvis = Jarvis()
        jarvis.think(_TRIGGER)
        questions = [i.question for i in jarvis.open_questions()]
        assert questions == [_TRIGGER]
        # No "Investigate the open question: X" item can ever appear.
        assert not any("Investigate" in question for question in questions)


class TestWriterPersistence:
    def test_item_survives_a_restart_on_json(self, tmp_path: Path) -> None:
        first = Jarvis.persistent(tmp_path)
        first.think(_TRIGGER)
        assert [i.question for i in first.open_questions()] == [_TRIGGER]

        second = Jarvis.persistent(tmp_path)
        assert [i.question for i in second.open_questions()] == [_TRIGGER]

    def test_item_survives_a_restart_on_sqlite(self, tmp_path: Path) -> None:
        first = Jarvis.database(tmp_path)
        first.think(_TRIGGER)
        assert [i.question for i in first.open_questions()] == [_TRIGGER]

        second = Jarvis.database(tmp_path)
        assert [i.question for i in second.open_questions()] == [_TRIGGER]


class TestWriterEpistemicIsolation:
    def test_the_written_conclusion_keeps_its_epistemic_standing(self) -> None:
        jarvis = Jarvis()
        episode = jarvis.think(_TRIGGER)
        belief = episode.working_belief
        assert belief is not None
        # The write invented no evidence and therefore no confidence (U2/U3).
        assert belief.evidence == ()
        assert belief.confidence.value == 0.0

    def test_the_unresolved_write_is_inert_over_cognitive_surfaces(
        self, tmp_path: Path
    ) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        beliefs_before = {
            b.statement: tuple(piece.content for piece in b.evidence)
            for b in jarvis.beliefs.all_beliefs()
        }
        memories = jarvis.semantic_memories
        assert memories is not None
        memories_before = memories.all_memories()
        episodes_before = jarvis.episodes.history()
        span_before = jarvis.reasoning_span()

        jarvis.note_open_question(_TRIGGER)

        # U1/U2/U3 -- no belief or evidence mutation, confidence stays derived.
        after = {
            b.statement: tuple(piece.content for piece in b.evidence)
            for b in jarvis.beliefs.all_beliefs()
        }
        assert after == beliefs_before
        # U4 -- no semantic memory written by the unresolved item.
        assert memories.all_memories() == memories_before
        # U5 -- no episode history (no topic identity input) is added.
        assert jarvis.episodes.history() == episodes_before
        # U6 -- no reasoning-span write.
        assert jarvis.reasoning_span() == span_before