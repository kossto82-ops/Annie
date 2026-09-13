"""Epistemic integrity: duplicate evidence must never inflate confidence (P0).

The invariant: a belief must never become stronger merely because the exact
same evidence was injected repeatedly. The shared identity policy
(:func:`same_observation`) distinguishes *the same observation re-injected*
(same id, or same claim fingerprint on the same UTC day -- skipped) from
*the same claim independently confirmed* (different source, provenance, or
day -- counted).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis.domain.entities.belief import Belief
from jarvis.domain.entities.semantic_memory import SemanticMemory
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.evidence_identity import same_observation
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _ev(
    content: str = "the sky is blue",
    source: EvidenceSource = EvidenceSource.DIRECT_OBSERVATION,
    weight: float = 1.0,
    supports: bool = True,
    observed_at: datetime | None = None,
    context: str | None = None,
) -> Evidence:
    return Evidence(
        content=content,
        source=source,
        weight=Confidence(weight),
        supports=supports,
        context=context,
        observed_at=observed_at if observed_at is not None else datetime.now(UTC),
    )


class TestSameObservation:
    def test_same_id_is_the_same_observation(self) -> None:
        piece = _ev()
        assert same_observation(piece, piece) is True

    def test_same_fingerprint_same_day_is_a_rerecording(self) -> None:
        instant = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
        assert same_observation(_ev(observed_at=instant), _ev(observed_at=instant)) is True

    def test_different_source_is_independent(self) -> None:
        assert (
            same_observation(_ev(), _ev(source=EvidenceSource.USER_STATEMENT)) is False
        )

    def test_different_day_is_independent(self) -> None:
        day_one = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
        day_two = day_one + timedelta(days=2)
        assert same_observation(_ev(observed_at=day_one), _ev(observed_at=day_two)) is False

    def test_different_provenance_is_independent(self) -> None:
        assert same_observation(_ev(), _ev(context="second sensor")) is False

    def test_contradiction_is_never_identical_to_support(self) -> None:
        assert same_observation(_ev(), _ev(supports=False)) is False


class TestDuplicateEvidenceDoesNotEscalate:
    def test_single_evidence_baseline(self) -> None:
        belief = Belief(statement="X")
        belief.add_evidence(_ev(source=EvidenceSource.USER_STATEMENT))
        assert belief.confidence.value == 0.5

    def test_same_evidence_50x_does_not_escalate(self) -> None:
        belief = Belief(statement="X")
        piece = _ev()
        belief.add_evidence(piece)
        baseline = belief.confidence.value
        for _ in range(50):
            belief.add_evidence(piece)
        assert belief.confidence.value == baseline
        assert len(belief.evidence) == 1

    def test_fresh_rebuilds_same_day_do_not_escalate(self) -> None:
        """The flood variant: 50 freshly built, content-identical pieces."""
        belief = Belief(statement="X")
        belief.add_evidence(_ev())
        baseline = belief.confidence.value
        for _ in range(50):
            belief.add_evidence(_ev())
        assert belief.confidence.value == baseline

    def test_reingest_after_restart_dedups(self) -> None:
        from jarvis.domain.services.evidence_weighting import DEFAULT_WEIGHTING
        from jarvis.infrastructure.json_belief_store import (
            deserialise_belief,
            serialise_belief,
        )

        belief = Belief(statement="X")
        piece = _ev()
        belief.add_evidence(piece)
        baseline = belief.confidence.value
        # Restart: rehydrate from storage (ids and instants survive).
        revived = deserialise_belief(serialise_belief(belief), DEFAULT_WEIGHTING)
        revived.add_evidence(piece)
        assert revived.confidence.value == baseline
        assert len(revived.evidence) == 1

    def test_independent_source_counts(self) -> None:
        belief = Belief(statement="X")
        belief.add_evidence(_ev())
        baseline = belief.confidence.value
        belief.add_evidence(_ev(source=EvidenceSource.USER_STATEMENT))
        assert belief.confidence.value > baseline

    def test_independent_observations_across_days_count(self) -> None:
        belief = Belief(statement="X")
        day_one = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
        belief.add_evidence(_ev(observed_at=day_one))
        baseline = belief.confidence.value
        assert belief.stability.value == 0.0
        belief.add_evidence(_ev(observed_at=day_one + timedelta(days=1)))
        belief.add_evidence(_ev(observed_at=day_one + timedelta(days=2)))
        assert belief.confidence.value > baseline
        # Genuine replication also spreads support over time.
        assert belief.stability.value > 0.0

    def test_similar_but_nonidentical_counts(self) -> None:
        belief = Belief(statement="X")
        belief.add_evidence(_ev("the sky is blue"))
        baseline = belief.confidence.value
        belief.add_evidence(_ev("the sky is azure"))
        assert belief.confidence.value > baseline

    def test_contradiction_lowers(self) -> None:
        belief = Belief(statement="X")
        belief.add_evidence(_ev())
        baseline = belief.confidence.value
        belief.add_evidence(_ev(supports=False))
        assert belief.confidence.value < baseline

    def test_repeated_contradiction_does_not_compound(self) -> None:
        belief = Belief(statement="X")
        belief.add_evidence(_ev())
        against = _ev(supports=False)
        belief.add_evidence(against)
        weakened = belief.confidence.value
        for _ in range(10):
            belief.add_evidence(against)
        assert belief.confidence.value == weakened


class TestParityAcrossEntities:
    def test_hypothesis_dedups_replays(self) -> None:
        from jarvis.domain.aggregates.hypothesis_set import HypothesisSet

        owned = HypothesisSet(observation="Q")
        candidate = owned.propose("H")
        piece = _ev()
        owned.add_evidence(candidate.id, piece)
        baseline = candidate.confidence.value
        for _ in range(5):
            owned.add_evidence(candidate.id, piece)
        assert candidate.confidence.value == baseline

    def test_semantic_memory_dedups_replays(self) -> None:
        memory = SemanticMemory(pattern="P")
        piece = _ev()
        memory.add_evidence(piece)
        baseline = memory.confidence.value
        for _ in range(3):
            memory.add_evidence(piece)
        assert memory.confidence.value == baseline
