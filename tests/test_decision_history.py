"""Tests for Phase 5: decision history with reasoning context.

Proves that EpisodeRecord now captures:
1. Reflection note (what the reflect stage observed)
2. Evidence snapshot (the belief's evidence at episode end)
3. The full decision history is reconstructable
"""

from __future__ import annotations

from datetime import UTC, datetime

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord, EvidenceSnapshot
from jarvis.domain.value_objects.temporal_stability import TemporalStability


class TestEvidenceSnapshot:
    def test_stores_evidence_fields(self):
        snap = EvidenceSnapshot(
            content="observed rain",
            source="companion_observation",
            supports=True,
            weight=0.8,
        )

        assert snap.content == "observed rain"
        assert snap.source == "companion_observation"
        assert snap.supports is True
        assert snap.weight == 0.8

    def test_is_frozen(self):
        snap = EvidenceSnapshot(
            content="test",
            source="test",
            supports=True,
            weight=0.5,
        )

        import pytest

        with pytest.raises(AttributeError):
            snap.content = "changed"  # type: ignore[misc]


class TestEpisodeRecordReflection:
    def test_reflection_note_defaults_to_none(self):
        record = EpisodeRecord(
            episode_id="ep-1",
            trigger="weather",
            decision="concluded",
            working_belief_id="bel-1",
            outcome=EpisodeState.COMPLETED,
            conclusion_confidence=Confidence(0.7),
            conclusion_stability=TemporalStability(0.6),
            origin=TriggerOrigin.COMPANION,
            kind=EpisodeKind.CONCLUSION,
        )

        assert record.reflection_note is None

    def test_reflection_note_can_be_set(self):
        record = EpisodeRecord(
            episode_id="ep-1",
            trigger="weather",
            decision="concluded",
            working_belief_id="bel-1",
            outcome=EpisodeState.COMPLETED,
            conclusion_confidence=Confidence(0.7),
            conclusion_stability=TemporalStability(0.6),
            origin=TriggerOrigin.COMPANION,
            kind=EpisodeKind.CONCLUSION,
            reflection_note="the conclusion is well grounded in its evidence",
        )

        assert record.reflection_note == "the conclusion is well grounded in its evidence"

    def test_evidence_snapshot_defaults_to_empty(self):
        record = EpisodeRecord(
            episode_id="ep-1",
            trigger="weather",
            decision="concluded",
            working_belief_id="bel-1",
            outcome=EpisodeState.COMPLETED,
            conclusion_confidence=Confidence(0.7),
            conclusion_stability=TemporalStability(0.6),
            origin=TriggerOrigin.COMPANION,
            kind=EpisodeKind.CONCLUSION,
        )

        assert record.evidence_snapshot == ()

    def test_evidence_snapshot_can_be_set(self):
        snapshots = (
            EvidenceSnapshot(
                content="rain observed", source="companion",
                supports=True, weight=0.8,
            ),
            EvidenceSnapshot(
                content="sun observed", source="companion",
                supports=False, weight=0.6,
            ),
        )
        record = EpisodeRecord(
            episode_id="ep-1",
            trigger="weather",
            decision="concluded",
            working_belief_id="bel-1",
            outcome=EpisodeState.COMPLETED,
            conclusion_confidence=Confidence(0.7),
            conclusion_stability=TemporalStability(0.6),
            origin=TriggerOrigin.COMPANION,
            kind=EpisodeKind.CONCLUSION,
            evidence_snapshot=snapshots,
        )

        assert len(record.evidence_snapshot) == 2
        assert record.evidence_snapshot[0].content == "rain observed"
        assert record.evidence_snapshot[1].supports is False


class TestDecisionHistoryReconstruction:
    """Prove that a complete decision history can be reconstructed from EpisodeRecords."""

    def test_full_decision_context(self):
        """A record with all fields captures the complete decision context."""
        now = datetime(2026, 9, 13, tzinfo=UTC)
        record = EpisodeRecord(
            episode_id="ep-weather-1",
            trigger="Will it rain tomorrow?",
            decision=(
                "Concluded about: Will it rain tomorrow? "
                "(confidence 0.75, stability 0.60), "
                "grounded in 3 piece(s) of evidence."
            ),
            working_belief_id="bel-weather",
            outcome=EpisodeState.COMPLETED,
            conclusion_confidence=Confidence(0.75),
            conclusion_stability=TemporalStability(0.60),
            origin=TriggerOrigin.COMPANION,
            kind=EpisodeKind.CONCLUSION,
            goal="prepare for outdoor activity",
            reflection_note="the conclusion is well grounded in its evidence",
            evidence_snapshot=(
                EvidenceSnapshot(
                    content="dark clouds observed",
                    source="companion", supports=True, weight=0.8,
                ),
                EvidenceSnapshot(
                    content="weather forecast says rain",
                    source="inference", supports=True, weight=0.7,
                ),
                EvidenceSnapshot(
                    content="but it was sunny yesterday",
                    source="companion", supports=False, weight=0.5,
                ),
            ),
            recorded_at=now,
        )

        # Reconstruct the decision context
        assert record.trigger == "Will it rain tomorrow?"
        assert "confidence 0.75" in record.decision
        assert record.reflection_note == "the conclusion is well grounded in its evidence"
        assert len(record.evidence_snapshot) == 3
        assert record.evidence_snapshot[0].supports is True
        assert record.evidence_snapshot[2].supports is False
        assert record.goal == "prepare for outdoor activity"

    def test_belief_evolution_with_reasoning(self):
        """Multiple records about the same subject show how the belief evolved."""
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        t2 = datetime(2026, 6, 1, tzinfo=UTC)

        record_1 = EpisodeRecord(
            episode_id="ep-1",
            trigger="Is coffee healthy?",
            decision="Tentative view",
            working_belief_id="bel-coffee",
            outcome=EpisodeState.COMPLETED,
            conclusion_confidence=Confidence(0.3),
            conclusion_stability=TemporalStability(0.2),
            origin=TriggerOrigin.COMPANION,
            kind=EpisodeKind.CONCLUSION,
            reflection_note="thinly grounded",
            evidence_snapshot=(
                EvidenceSnapshot(
                    content="some studies say yes",
                    source="inference", supports=True, weight=0.6,
                ),
            ),
            recorded_at=t1,
        )

        record_2 = EpisodeRecord(
            episode_id="ep-2",
            trigger="Is coffee healthy?",
            decision="Grounded conclusion",
            working_belief_id="bel-coffee",
            outcome=EpisodeState.COMPLETED,
            conclusion_confidence=Confidence(0.8),
            conclusion_stability=TemporalStability(0.7),
            origin=TriggerOrigin.COMPANION,
            kind=EpisodeKind.CONCLUSION,
            reflection_note=(
                "the conclusion is well grounded in its evidence"
            ),
            evidence_snapshot=(
                EvidenceSnapshot(
                    content="some studies say yes",
                    source="inference", supports=True, weight=0.6,
                ),
                EvidenceSnapshot(
                    content="meta-analysis confirms",
                    source="inference", supports=True, weight=0.9,
                ),
                EvidenceSnapshot(
                    content="long-term study shows benefit",
                    source="inference", supports=True, weight=0.8,
                ),
            ),
            recorded_at=t2,
        )

        # Verify evolution is traceable
        assert record_1.conclusion_confidence.value == 0.3
        assert record_2.conclusion_confidence.value == 0.8
        assert record_1.reflection_note == "thinly grounded"
        assert record_2.reflection_note == "the conclusion is well grounded in its evidence"
        assert len(record_1.evidence_snapshot) == 1
        assert len(record_2.evidence_snapshot) == 3
