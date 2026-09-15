"""Derived attention priorities from episode history (Vision §16, audit §2.1).

Attention development means priorities that come from accumulated experience:
topics Jarvis keeps returning to, keeps failing to settle, or keeps revising
deserve more of its attention than a topic touched once and closed.

Everything here is *derived* per read from a bounded window of the episode
history -- no second authoritative learning state, no persisted scores, no
unbounded accumulation.  Recomputing over the same history always yields the
same ranking (reversible); calling it never mutates anything.
"""

from __future__ import annotations

from collections.abc import Iterable

from jarvis.domain.value_objects.attention_priority import AttentionPriority
from jarvis.domain.value_objects.episode_record import EpisodeRecord

# Below this confidence an episode's conclusion is not grounded: the topic is
# still "open" for Jarvis.
_UNGROUNDED_CONFIDENCE = 0.5
# Only the most recent episodes shape attention.  Bounded by construction, so no
# amount of living can inflate a priority without limit.
_DEFAULT_WINDOW = 50
# A topic must clear this saliency before wake() proposes attending to it.
# One-off episodes sit around 0.31; two repeats ~0.37; three repeats ~0.42.
# A threshold of 0.40 requires at least three touches (or fewer with unresolved
# endings) before a topic claims attention -- enough for the recurrence to be
# a real pattern, not a random mention.
ATTEND_THRESHOLD = 0.40


def _recency(window: int, last_index: int) -> float:
    if window <= 1:
        return 0.0
    return (window - 1 - last_index) / (window - 1)


def _score(recurrence: int, unresolved: int, revised: bool, recency: float) -> float:
    """Bounded saliency in ``[0, 1]`` from the four raw signals.

    Each term saturates, so the sum is capped by construction.
    """
    total = (
        0.30 * min(1.0, recurrence / 5.0)
        + 0.25 * min(1.0, unresolved / 3.0)
        + 0.20 * (1.0 if revised else 0.0)
        + 0.25 * recency
    )
    return min(1.0, total)


def derive_attention_priorities(
    episodes: Iterable[EpisodeRecord],
    *,
    window: int = _DEFAULT_WINDOW,
) -> tuple[AttentionPriority, ...]:
    """Rank topics by saliency learned from the recent episode history.

    A topic's priority grows with how often it recurs, how often Jarvis failed
    to settle it on the last attempt, whether its belief kept changing, and how
    recently Jarvis last touched it.  Returns an empty tuple for a Jarvis with
    nothing on record.
    """
    records = tuple(episodes)[-window:]
    if not records:
        return ()

    # (count, unresolved, revised, last_index) per topic.
    counts: dict[str, int] = {}
    unresolved: dict[str, int] = {}
    confidence_ends: dict[str, set[float]] = {}
    last_index: dict[str, int] = {}

    for index, record in enumerate(records):
        topic = record.trigger
        counts[topic] = counts.get(topic, 0) + 1
        end = record.belief_confidence_at_end
        if end is not None:
            confidence_ends.setdefault(topic, set()).add(round(end.value, 6))
        concluded = record.conclusion_confidence
        if concluded is None or concluded.value < _UNGROUNDED_CONFIDENCE:
            unresolved[topic] = unresolved.get(topic, 0) + 1
        last_index[topic] = index

    priorities: list[AttentionPriority] = []
    for topic, count in counts.items():
        ends = confidence_ends.get(topic, set())
        revised = len(ends) > 1
        recen = _recency(window, last_index[topic])
        priorities.append(
            AttentionPriority(
                topic=topic,
                priority=_score(count, unresolved.get(topic, 0), revised, recen),
                episodes_on_topic=count,
                unresolved=unresolved.get(topic, 0),
                revised=revised,
                last_episode_recency=recen,
            )
        )

    priorities.sort(
        key=lambda p: (-p.priority, -p.episodes_on_topic, -p.last_episode_recency, p.topic)
    )
    return tuple(priorities)