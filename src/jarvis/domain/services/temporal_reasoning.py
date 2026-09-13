"""Temporal reasoning: belief evolution, change detection, and pattern recognition.

Phase 3A — Jarvis must distinguish:
- What was believed then?
- What is believed now?
- What evidence changed it?

Phase 8 — Temporal pattern detection:
- Stable preference: confidence stays similar across episodes
- Changing preference: confidence consistently increases or decreases
- Recurring contradiction: episodes alternate between outcomes
- Repeated outcome: same outcome (COMPLETED/FAILED) repeatedly

Functions here are pure computations over episode records — they do not
mutate state or depend on repository implementations.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.temporal_stability import TemporalStability


@dataclass(frozen=True, slots=True)
class BeliefSnapshot:
    """A belief's state at a single point in time."""

    recorded_at: datetime
    confidence: Confidence
    stability: TemporalStability
    decision: str
    outcome: str
    episode_id: str


@dataclass(frozen=True, slots=True)
class BeliefChange:
    """A change in belief between two points in time."""

    subject: str
    earlier: BeliefSnapshot
    later: BeliefSnapshot
    confidence_delta: float  # positive = strengthened, negative = weakened
    stability_delta: float


class TemporalPattern(Enum):
    """Detected patterns in belief evolution."""

    STABLE = "stable"  # confidence stays similar (±0.1)
    STRENGTHENING = "strengthening"  # confidence consistently increases
    WEAKENING = "weakening"  # confidence consistently decreases
    OSCILLATING = "oscillating"  # confidence alternates up and down
    RECURRING_CONTRADICTION = "recurring_contradiction"  # outcomes alternate


@dataclass(frozen=True, slots=True)
class TemporalPatternResult:
    """A detected pattern in a belief's evolution."""

    subject: str
    pattern: TemporalPattern
    confidence: float  # pattern strength [0, 1]
    episode_count: int
    description: str


def belief_timeline(
    subject: str,
    history: Sequence[EpisodeRecord],
) -> tuple[BeliefSnapshot, ...]:
    """Return the time-ordered trajectory of a belief about a subject.

    Each snapshot shows the belief's confidence and stability at the time
    of a completed episode. The trajectory reveals whether the belief is
    strengthening, weakening, or oscillating.

    Args:
        subject: substring to match against episode triggers (case-insensitive)
        history: full episode history (typically from repository.history())

    Returns:
        Time-ordered snapshots, oldest first. Empty if no episodes match.
    """
    relevant = [
        r
        for r in history
        if subject.lower() in r.trigger.lower()
        and r.origin is TriggerOrigin.COMPANION
        and r.kind is EpisodeKind.CONCLUSION
    ]
    relevant.sort(key=lambda r: r.recorded_at)

    return tuple(
        BeliefSnapshot(
            recorded_at=r.recorded_at,
            confidence=r.conclusion_confidence,
            stability=r.conclusion_stability,
            decision=r.decision,
            outcome=r.outcome.value,
            episode_id=r.episode_id,
        )
        for r in relevant
    )


def what_changed(
    subject: str,
    start: datetime,
    end: datetime,
    history: Sequence[EpisodeRecord],
) -> tuple[BeliefChange, ...]:
    """Detect belief changes within a time window.

    Returns consecutive pairs of episodes about the subject where the
    belief's confidence or stability changed meaningfully. A "meaningful
    change" is a confidence shift of at least 0.1.

    Args:
        subject: substring to match against episode triggers (case-insensitive)
        start: start of the time window (inclusive)
        end: end of the time window (inclusive)
        history: full episode history

    Returns:
        Changes ordered by time, showing the earlier and later snapshots.
    """
    _MEANINGFUL_CONFIDENCE_DELTA = 0.1

    timeline = belief_timeline(subject, history)
    # Filter to the time window
    window = [s for s in timeline if start <= s.recorded_at <= end]

    changes: list[BeliefChange] = []
    for i in range(1, len(window)):
        earlier = window[i - 1]
        later = window[i]
        conf_delta = later.confidence.value - earlier.confidence.value
        stab_delta = later.stability.value - earlier.stability.value
        if abs(conf_delta) >= _MEANINGFUL_CONFIDENCE_DELTA:
            changes.append(
                BeliefChange(
                    subject=subject,
                    earlier=earlier,
                    later=later,
                    confidence_delta=conf_delta,
                    stability_delta=stab_delta,
                )
            )

    return tuple(changes)


def belief_snapshot_at(
    subject: str,
    at_time: datetime,
    history: Sequence[EpisodeRecord],
) -> BeliefSnapshot | None:
    """Reconstruct what was believed about a subject at a specific time.

    Returns the most recent episode snapshot before (or at) the given time.
    This answers "what did I believe then?" by replaying episode history.

    Args:
        subject: substring to match against episode triggers (case-insensitive)
        at_time: the point in time to reconstruct
        history: full episode history

    Returns:
        The most recent snapshot, or None if no episodes match before that time.
    """
    timeline = belief_timeline(subject, history)
    # Find the most recent snapshot at or before at_time
    candidates = [s for s in timeline if s.recorded_at <= at_time]
    if not candidates:
        return None
    return candidates[-1]


def detect_pattern(
    subject: str,
    history: Sequence[EpisodeRecord],
) -> TemporalPatternResult | None:
    """Detect the dominant temporal pattern for a belief about a subject.

    Analyzes the trajectory of confidence values to identify whether the
    belief is stable, strengthening, weakening, oscillating, or shows
    recurring contradictions.

    Args:
        subject: substring to match against episode triggers (case-insensitive)
        history: full episode history

    Returns:
        The detected pattern with strength and description, or None if
        insufficient data (< 3 episodes).
    """
    _MIN_EPISODES = 3
    _STABLE_THRESHOLD = 0.1  # max confidence variation for "stable"
    _CONSISTENT_THRESHOLD = 0.05  # min average step for "consistent" change

    timeline = belief_timeline(subject, history)
    if len(timeline) < _MIN_EPISODES:
        return None

    confidences = [s.confidence.value for s in timeline]
    n = len(confidences)

    # Compute step-by-step changes
    steps = [confidences[i] - confidences[i - 1] for i in range(1, n)]
    avg_step = sum(steps) / len(steps)
    max_variation = max(confidences) - min(confidences)

    # Check for recurring contradictions (outcomes alternate)
    outcomes = [s.outcome for s in timeline]
    if n >= 4:
        alternations = sum(
            1 for i in range(1, n) if outcomes[i] != outcomes[i - 1]
        )
        if alternations >= n - 2:  # mostly alternating
            return TemporalPatternResult(
                subject=subject,
                pattern=TemporalPattern.RECURRING_CONTRADICTION,
                confidence=min(1.0, alternations / (n - 1)),
                episode_count=n,
                description=(
                    f"episodes about '{subject}' alternate between "
                    f"outcomes ({alternations} alternations in {n} episodes)"
                ),
            )

    # Check for stable preference
    if max_variation <= _STABLE_THRESHOLD:
        return TemporalPatternResult(
            subject=subject,
            pattern=TemporalPattern.STABLE,
            confidence=1.0 - max_variation,  # more stable = higher confidence
            episode_count=n,
            description=(
                f"belief about '{subject}' is stable "
                f"(confidence range: {min(confidences):.2f}-{max(confidences):.2f})"
            ),
        )

    # Check for consistent strengthening
    if avg_step >= _CONSISTENT_THRESHOLD and all(s >= 0 for s in steps):
        return TemporalPatternResult(
            subject=subject,
            pattern=TemporalPattern.STRENGTHENING,
            confidence=min(1.0, avg_step * 5),  # stronger trend = higher confidence
            episode_count=n,
            description=(
                f"belief about '{subject}' is strengthening "
                f"(avg step: +{avg_step:.3f}, from {confidences[0]:.2f} to {confidences[-1]:.2f})"
            ),
        )

    # Check for consistent weakening
    if avg_step <= -_CONSISTENT_THRESHOLD and all(s <= 0 for s in steps):
        return TemporalPatternResult(
            subject=subject,
            pattern=TemporalPattern.WEAKENING,
            confidence=min(1.0, abs(avg_step) * 5),
            episode_count=n,
            description=(
                f"belief about '{subject}' is weakening "
                f"(avg step: {avg_step:.3f}, from {confidences[0]:.2f} to {confidences[-1]:.2f})"
            ),
        )

    # Check for oscillation (alternating up/down steps)
    if n >= 4:
        sign_changes = sum(
            1 for i in range(1, len(steps))
            if (steps[i] > 0) != (steps[i - 1] > 0)
        )
        if sign_changes >= len(steps) - 1:  # mostly alternating
            return TemporalPatternResult(
                subject=subject,
                pattern=TemporalPattern.OSCILLATING,
                confidence=min(1.0, sign_changes / len(steps)),
                episode_count=n,
                description=(
                    f"belief about '{subject}' is oscillating "
                    f"({sign_changes} sign changes in {len(steps)} steps)"
                ),
            )

    return None
