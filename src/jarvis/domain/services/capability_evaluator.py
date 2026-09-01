"""capability_evaluator: derive a stance toward acquiring a capability (Odysseus).

The *evaluation* stage of capability acquisition, after the scout proposes. It
turns a need into a grounds for action by asking one honest question: is Jarvis's
evidence confident that it needs this capability, and does it already have it?
The stance is always *derived* from the need belief's confidence -- never set --
mirroring how :mod:`jarvis.domain.services.action_advisor` derives action stances
(Vision §28): autonomy is earned, and it only recommends; it acquires nothing.
"""

from __future__ import annotations

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.capability_stance import CapabilityStance
from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.value_objects.capability import Capability
from jarvis.domain.value_objects.capability_recommendation import CapabilityRecommendation
from jarvis.domain.value_objects.confidence import Confidence

# A need must be at least this confident before acquiring its capability is suggested.
_SUGGEST_NEED_CONFIDENCE = 0.5


def recommend(
    need: Belief | None, capability: Capability | None
) -> CapabilityRecommendation:
    """Recommend a stance toward acquiring ``capability`` given its ``need``.

    ``need`` is the belief Jarvis holds about whether it needs this capability
    (derived confidence); ``capability`` is the candidate, or None when the scout
    produced nothing.
    """
    if need is None:
        return CapabilityRecommendation(
            stance=CapabilityStance.ASK_FIRST,
            confidence=Confidence.none(),
            rationale="I have no evidence yet that I need this, so I would ask first.",
        )

    confidence = need.confidence
    acquired = (
        capability is not None and capability.status is CapabilityStatus.ACQUIRED
    )

    if acquired:
        return CapabilityRecommendation(
            stance=CapabilityStance.ASK_FIRST,
            confidence=confidence,
            rationale=(
                f"I already have this capability (need confidence "
                f"{confidence.value:.2f}), so there is nothing to acquire."
            ),
        )

    if confidence.value >= _SUGGEST_NEED_CONFIDENCE:
        return CapabilityRecommendation(
            stance=CapabilityStance.SUGGEST,
            confidence=confidence,
            rationale=(
                f"My evidence says I need this (need confidence "
                f"{confidence.value:.2f}) and I do not have it yet, so I would "
                "acquire it."
            ),
        )

    if bool(need.explain().contradicting):
        return CapabilityRecommendation(
            stance=CapabilityStance.WITHHOLD,
            confidence=confidence,
            rationale=(
                f"My evidence for needing this is contradicted (need confidence "
                f"{confidence.value:.2f}), so I would not pursue it."
            ),
        )

    return CapabilityRecommendation(
        stance=CapabilityStance.ASK_FIRST,
        confidence=confidence,
        rationale=(
            f"I am not confident enough that I need this yet (need confidence "
            f"{confidence.value:.2f}), so I would ask first."
        ),
    )
