"""Deciding how autonomously to treat an action, from experience (Vision §28).

The recommendation is derived from Jarvis's *learned* belief about actions of a
kind (its track record) and the action's reversibility -- never from a one-off
guess. Autonomy is earned: only a confidently-learned, reversible action is
suggested; an unproven or irreversible one asks first; one the record contradicts
is withheld. This decides a stance only; it performs nothing.
"""

from __future__ import annotations

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.action_stance import ActionStance
from jarvis.domain.value_objects.action_recommendation import ActionRecommendation
from jarvis.domain.value_objects.confidence import Confidence

# A learned belief must be at least this confident before an action is suggested.
_SUGGEST_CONFIDENCE = 0.5


def recommend(belief: Belief | None, *, reversible: bool) -> ActionRecommendation:
    """Recommend a stance toward an action given what Jarvis has learned about it."""
    if belief is None:
        return ActionRecommendation(
            stance=ActionStance.ASK_FIRST,
            confidence=Confidence.none(),
            rationale="I have no experience with this action yet, so I would ask first.",
        )

    confidence = belief.confidence
    contradicted = bool(belief.explain().contradicting)

    if confidence.value >= _SUGGEST_CONFIDENCE:
        if reversible:
            return ActionRecommendation(
                stance=ActionStance.SUGGEST,
                confidence=confidence,
                rationale=(
                    f"I have learned this tends to work (confidence "
                    f"{confidence.value:.2f}) and it is reversible."
                ),
            )
        return ActionRecommendation(
            stance=ActionStance.ASK_FIRST,
            confidence=confidence,
            rationale=(
                f"I have learned this tends to work (confidence {confidence.value:.2f}), "
                "but it is irreversible, so I would ask first."
            ),
        )

    if contradicted:
        return ActionRecommendation(
            stance=ActionStance.WITHHOLD,
            confidence=confidence,
            rationale=(
                f"Past outcomes contradict this working out (confidence "
                f"{confidence.value:.2f}); I would advise against it."
            ),
        )

    return ActionRecommendation(
        stance=ActionStance.ASK_FIRST,
        confidence=confidence,
        rationale=(
            f"I am not confident enough about this yet (confidence "
            f"{confidence.value:.2f}), so I would ask first."
        ),
    )
