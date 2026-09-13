"""Phase 2B: Prove that self-observation produces genuine behavioral change.

The audit identified that self-observation mainly affects narration text, not
cognitive mechanics. This test file proves that the adaptation bridge
(Phase 2A) closes the learning loop:

1. Before learning: same evidence → conclusion at default threshold
2. After repeated failure: same situation → higher threshold → different behavior
3. After behavior improves: threshold drifts back toward baseline
"""

from __future__ import annotations

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.self_observation import (
    adapt_knobs_from_self_observation,
)
from jarvis.domain.value_objects.cognitive_knobs import CognitiveKnobs
from jarvis.domain.value_objects.episode_record import EpisodeRecord


def _make_record(
    trigger: str,
    confidence: float,
    stability: float = 0.8,
    *,
    origin: TriggerOrigin = TriggerOrigin.COMPANION,
    kind: EpisodeKind = EpisodeKind.CONCLUSION,
) -> EpisodeRecord:
    """Create a minimal EpisodeRecord for testing."""
    from jarvis.domain.value_objects.confidence import Confidence
    from jarvis.domain.value_objects.temporal_stability import TemporalStability

    return EpisodeRecord(
        episode_id=f"ep-{trigger}",
        trigger=trigger,
        decision=f"decided about {trigger}",
        working_belief_id="bel-1",
        outcome=None,
        conclusion_confidence=Confidence(confidence),
        conclusion_stability=TemporalStability(stability),
        origin=origin,
        kind=kind,
    )


class TestAdaptationProvesBehavioralChange:
    """Prove that self-observation → adaptation → changed behavior."""

    def test_before_learning_threshold_is_default(self):
        """With no habit history, knobs stay at default."""
        knobs = CognitiveKnobs()
        history = [_make_record(f"q{i}", 0.6) for i in range(5)]

        adapted, reason = adapt_knobs_from_self_observation(knobs, history)

        assert adapted.grounded_confidence == knobs.grounded_confidence
        assert reason is None

    def test_after_repeated_ungrounded_conclusions_threshold_rises(self):
        """When Jarvis repeatedly concludes without evidence, the threshold rises."""
        knobs = CognitiveKnobs()
        # Create 5 episodes all with confidence 0.2 (well below 0.5 threshold)
        history = [_make_record(f"q{i}", 0.2) for i in range(5)]

        adapted, reason = adapt_knobs_from_self_observation(knobs, history)

        assert adapted.grounded_confidence > knobs.grounded_confidence
        assert reason is not None
        assert "raised" in reason
        assert "evidence habit" in reason

    def test_threshold_is_bounded(self):
        """The threshold never exceeds 0.9."""
        knobs = CognitiveKnobs(grounded_confidence=0.85)
        # Create many ungrounded episodes to trigger adaptation
        history = [_make_record(f"q{i}", 0.2) for i in range(10)]

        adapted, _ = adapt_knobs_from_self_observation(knobs, history)

        assert adapted.grounded_confidence <= 0.9

    def test_threshold_is_bounded_below(self):
        """The threshold never drops below 0.1."""
        knobs = CognitiveKnobs(grounded_confidence=0.15)
        # Create well-grounded episodes (no habit) → drift toward baseline
        history = [_make_record(f"q{i}", 0.8) for i in range(10)]

        adapted, _ = adapt_knobs_from_self_observation(knobs, history)

        assert adapted.grounded_confidence >= 0.1

    def test_reversibility_when_habit_stops(self):
        """When the habit stops, threshold drifts back toward baseline."""
        # Start with a raised threshold (simulating past learning)
        knobs = CognitiveKnobs(grounded_confidence=0.6)
        # All episodes are now well-grounded (habit stopped)
        history = [_make_record(f"q{i}", 0.8) for i in range(5)]

        adapted, reason = adapt_knobs_from_self_observation(knobs, history)

        assert adapted.grounded_confidence < knobs.grounded_confidence
        assert reason is not None
        assert "lowered" in reason
        assert "baseline" in reason

    def test_adaptation_is_step_bounded(self):
        """Each adaptation call moves the threshold by at most 0.05."""
        knobs = CognitiveKnobs()
        history = [_make_record(f"q{i}", 0.2) for i in range(5)]

        adapted, _ = adapt_knobs_from_self_observation(knobs, history)

        delta = abs(adapted.grounded_confidence - knobs.grounded_confidence)
        assert delta <= 0.06  # 0.05 + float tolerance

    def test_multiple_calls_accumulate(self):
        """Multiple adaptation calls accumulate the effect."""
        knobs = CognitiveKnobs()
        history = [_make_record(f"q{i}", 0.2) for i in range(5)]

        # Run adaptation 3 times
        current = knobs
        for _ in range(3):
            current, _ = adapt_knobs_from_self_observation(current, history)

        assert current.grounded_confidence > knobs.grounded_confidence
        # Should be roughly 3 * 0.05 = 0.15 higher
        assert abs(current.grounded_confidence - 0.65) < 0.01
