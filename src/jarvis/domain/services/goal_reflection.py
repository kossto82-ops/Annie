"""Jarvis noticing what it keeps returning to (Vision §26, §31).

Once goals live in episodic memory (they are recorded on ``EpisodeRecord``),
Jarvis can look back over its own purposes and notice the ones it returns to.
This is deliberately *not* a belief and *not* a plan: it is a plain count over
memory. It names what Jarvis has come back to -- nothing about whether that is
good, wise, or worth pursuing. Judgement, if any, is a later and separate step.

Matching is exact-string on the goal statement (the same deliberate
simplification as trigger identity, D17); semantic clustering of related goals
is a future concern.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.value_objects.episode_record import EpisodeRecord

# Fewer recurrences than this is a one-off, not something Jarvis "keeps returning
# to". Mirrors the self-observation floor (_MINIMUM_HISTORY) so both read-models
# demand comparable evidence before naming a pattern.
_MINIMUM_RECURRENCE = 3


def recurring_goals(
    history: Sequence[EpisodeRecord], *, minimum: int = _MINIMUM_RECURRENCE
) -> tuple[tuple[str, int], ...]:
    """Count goal statements Jarvis has repeatedly pursued.

    Considers only companion-directed episodes that carried a goal; self-directed
    (curiosity) episodes and goal-less ones are skipped. Returns ``(goal, count)``
    pairs ordered by descending count (ties keep first-seen order), limited to
    goals seen at least ``minimum`` times. Empty when nothing recurs enough.
    """
    counts: Counter[str] = Counter()
    for record in history:
        if record.origin is not TriggerOrigin.COMPANION:
            continue
        if record.goal is None:
            continue
        counts[record.goal] += 1
    return tuple((goal, count) for goal, count in counts.most_common() if count >= minimum)
