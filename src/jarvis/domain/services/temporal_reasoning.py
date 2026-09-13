"""Temporal reasoning: belief evolution and change detection.

Phase 3A — Jarvis must distinguish:
- What was believed then?
- What is believed now?
- What evidence changed it?

This module provides functions to reconstruct belief trajectories from
episode history. Each episode records the working belief's confidence and
stability at completion time, so episodes about a subject form a
time-ordered trajectory of how that belief evolved.

Functions here are pure computations over episode records — they do not
mutate state or depend on repository implementations.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

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
