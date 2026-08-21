"""Tests for graded-autonomy action recommendations (Vision §28)."""

from __future__ import annotations

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.action_stance import ActionStance
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.action_advisor import recommend
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _belief_with(*, successes: int, failures: int) -> Belief:
    belief = Belief(statement="predictions about the action hold")
    for _ in range(successes):
        belief.add_evidence(_outcome(met=True))
    for _ in range(failures):
        belief.add_evidence(_outcome(met=False))
    return belief


def _outcome(*, met: bool) -> Evidence:
    return Evidence(
        content="an outcome",
        source=EvidenceSource.ACTION_OUTCOME,
        weight=Confidence(1.0),
        supports=met,
    )


class TestRecommend:
    def test_an_unproven_action_asks_first(self) -> None:
        rec = recommend(None, reversible=True)
        assert rec.stance is ActionStance.ASK_FIRST

    def test_a_learned_reversible_action_is_suggested(self) -> None:
        belief = _belief_with(successes=3, failures=0)
        assert recommend(belief, reversible=True).stance is ActionStance.SUGGEST

    def test_a_learned_but_irreversible_action_asks_first(self) -> None:
        belief = _belief_with(successes=3, failures=0)
        assert recommend(belief, reversible=False).stance is ActionStance.ASK_FIRST

    def test_a_contradicted_action_is_withheld(self) -> None:
        belief = _belief_with(successes=1, failures=3)  # low confidence + contradicted
        assert recommend(belief, reversible=True).stance is ActionStance.WITHHOLD

    def test_a_thin_but_uncontradicted_action_asks_first(self) -> None:
        belief = _belief_with(successes=1, failures=0)  # not confident, no failures
        assert recommend(belief, reversible=True).stance is ActionStance.ASK_FIRST
