"""Jarvis observing its own cognition (Vision §6, §31).

This is the first fragment of a model of *itself*. It must not be fake
personality text -- it emerges from measurable history. It reuses the ordinary
epistemology: each past episode is a piece of *evidence about Jarvis*, and the
self-observation is just a `Belief` whose confidence is derived from that
evidence. So "I tend to X" is provisional and revisable, exactly like any other
belief.

The single tendency measured here: does Jarvis habitually conclude without
enough evidence? Each episode that ended ungrounded supports that belief; each
grounded episode contradicts it. More tendencies can be added the same way.
"""

from __future__ import annotations

from collections.abc import Sequence

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence

# Below this conclusion confidence an episode counts as "ungrounded". Mirrors the
# executive's GROUNDED_CONFIDENCE_THRESHOLD (D14); kept here to avoid the domain
# depending on the application layer.
_GROUNDED_CONFIDENCE = 0.5

# Too few episodes to judge a tendency honestly.
_MINIMUM_HISTORY = 3

_OBSERVATION_WEIGHT = Confidence(1.0)

INSUFFICIENT_EVIDENCE_HABIT = "I tend to conclude without sufficient evidence"


def observe_evidence_habit(history: Sequence[EpisodeRecord]) -> Belief | None:
    """Form a belief about whether Jarvis concludes without enough evidence.

    Returns None when there is too little history to judge. Otherwise returns a
    belief about Jarvis, grounded in one piece of evidence per past episode, so
    its confidence reflects how often conclusions were actually ungrounded.
    """
    # Judge only how Jarvis handled the companion's questions. Self-triggered
    # (curiosity) episodes must not inflate the very habit they respond to.
    relevant = [r for r in history if r.origin is TriggerOrigin.COMPANION]
    if len(relevant) < _MINIMUM_HISTORY:
        return None

    belief = Belief(statement=INSUFFICIENT_EVIDENCE_HABIT)
    for record in relevant:
        ungrounded = record.conclusion_confidence.value < _GROUNDED_CONFIDENCE
        belief.add_evidence(
            Evidence(
                content=(
                    f"episode about '{record.trigger}' concluded at confidence "
                    f"{record.conclusion_confidence.value:.2f}"
                ),
                source=EvidenceSource.SYSTEM_OBSERVATION,
                weight=_OBSERVATION_WEIGHT,
                supports=ungrounded,
                observed_at=record.recorded_at,
            )
        )
    return belief
