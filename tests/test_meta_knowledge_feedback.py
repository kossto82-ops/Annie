"""Tests for Phase 7: meta-knowledge feedback.

Proves that second-order reflection feeds back to cognitive adjustments:
1. Reasoning effectiveness → preference for deliberation
2. Attention allocation → grounded_confidence adjustment
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.value_objects.cognitive_knobs import CognitiveKnobs
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.executive.executive_controller import ExecutiveController
from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore
from jarvis.infrastructure.in_memory_episode_store import InMemoryEpisodeStore
from jarvis.nervous_system.nervous_system import NervousSystem


def _make_controller() -> ExecutiveController:
    """Create a minimal controller for testing."""
    return ExecutiveController(
        nervous_system=NervousSystem(),
        beliefs=InMemoryBeliefStore(),
        episodes=InMemoryEpisodeStore(),
        companion=CompanionModel(InMemoryBeliefStore()),
        knobs=CognitiveKnobs(),
    )


def _make_record(
    trigger: str,
    confidence: float,
    kind: EpisodeKind,
    recorded_at: datetime,
) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id=f"ep-{trigger}-{recorded_at.timestamp()}",
        trigger=trigger,
        decision="concluded",
        working_belief_id="bel-1",
        outcome=EpisodeState.COMPLETED,
        conclusion_confidence=Confidence(confidence),
        conclusion_stability=TemporalStability(0.5),
        origin=TriggerOrigin.COMPANION,
        kind=kind,
        recorded_at=recorded_at,
    )


class TestMetaKnowledgeFeedback:
    def test_detects_deliberations_outperform_conclusions(self):
        """When deliberations consistently outperform conclusions, return feedback."""
        controller = _make_controller()
        now = datetime(2026, 9, 13, tzinfo=UTC)

        # Create 7 conclusion episodes with low confidence
        for i in range(7):
            record = _make_record(
                f"conclusion-{i}", 0.3, EpisodeKind.CONCLUSION,
                now - timedelta(hours=7 - i),
            )
            controller.episodes.record(record)

        # Create 7 deliberation episodes with high confidence
        for i in range(7):
            record = _make_record(
                f"deliberation-{i}", 0.8, EpisodeKind.DELIBERATION,
                now - timedelta(hours=7 - i),
            )
            controller.episodes.record(record)

        result = controller.adapt_from_meta_observation()

        assert result is not None
        assert "deliberations" in result
        assert "better" in result

    def test_no_feedback_when_conclusions_outperform(self):
        """When conclusions outperform deliberations, no feedback needed."""
        controller = _make_controller()
        now = datetime(2026, 9, 13, tzinfo=UTC)

        # Create 7 conclusion episodes with high confidence
        for i in range(7):
            record = _make_record(
                f"conclusion-{i}", 0.8, EpisodeKind.CONCLUSION,
                now - timedelta(hours=7 - i),
            )
            controller.episodes.record(record)

        # Create 7 deliberation episodes with low confidence
        for i in range(7):
            record = _make_record(
                f"deliberation-{i}", 0.3, EpisodeKind.DELIBERATION,
                now - timedelta(hours=7 - i),
            )
            controller.episodes.record(record)

        result = controller.adapt_from_meta_observation()

        # Should not return reasoning effectiveness feedback
        # (might return attention feedback if applicable)
        if result is not None:
            assert "deliberations" not in result or "better" not in result

    def test_no_feedback_with_insufficient_history(self):
        """With insufficient history, no feedback is returned."""
        controller = _make_controller()

        # Only 3 episodes (need 6 in each category)
        for i in range(3):
            record = _make_record(f"test-{i}", 0.5, EpisodeKind.CONCLUSION,
                                  datetime(2026, 9, 13, tzinfo=UTC))
            controller.episodes.record(record)

        result = controller.adapt_from_meta_observation()

        assert result is None

    def test_insufficient_attention_raises_threshold(self):
        """When most episodes are ungrounded, raise grounded_confidence."""
        controller = _make_controller()
        now = datetime(2026, 9, 13, tzinfo=UTC)
        initial_threshold = controller.knobs.grounded_confidence

        # Create 8 episodes with low confidence (ungrounded)
        for i in range(8):
            record = _make_record(
                f"test-{i}", 0.2, EpisodeKind.CONCLUSION,
                now - timedelta(hours=8 - i),
            )
            controller.episodes.record(record)

        result = controller.adapt_from_meta_observation()

        assert result is not None
        assert "insufficient" in result
        assert controller.knobs.grounded_confidence > initial_threshold

    def test_threshold_stays_bounded(self):
        """Grounded_confidence never exceeds 0.9."""
        controller = _make_controller(
        )
        # Set threshold near ceiling
        controller.set_knobs(CognitiveKnobs(grounded_confidence=0.88))
        now = datetime(2026, 9, 13, tzinfo=UTC)

        # Create many ungrounded episodes
        for i in range(10):
            record = _make_record(
                f"test-{i}", 0.2, EpisodeKind.CONCLUSION,
                now - timedelta(hours=10 - i),
            )
            controller.episodes.record(record)

        controller.adapt_from_meta_observation()

        assert controller.knobs.grounded_confidence <= 0.9
