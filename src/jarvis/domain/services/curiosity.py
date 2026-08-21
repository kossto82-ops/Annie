"""Curiosity: deciding a known uncertainty is worth reducing (Vision §16, §31).

Given a belief Jarvis holds *about itself* (e.g. "I tend to conclude without
sufficient evidence"), curiosity asks whether it is confident enough to be worth
acting on. If so it produces a :class:`CuriosityImpulse` -- the intent to pursue
a corrective, self-triggered episode. It stops at the recommendation; pursuing it
is a separate, deliberate step (Vision §28).
"""

from __future__ import annotations

from jarvis.domain.entities.belief import Belief
from jarvis.domain.value_objects.curiosity_impulse import CuriosityImpulse

# A self-belief must be at least moderately confident before it is worth acting
# on -- weak self-suspicion should not drive Jarvis around (Vision §16).
CURIOSITY_THRESHOLD = 0.5


def wonder(self_belief: Belief, threshold: float = CURIOSITY_THRESHOLD) -> CuriosityImpulse | None:
    """Return an impulse to reduce ``self_belief``'s uncertainty, or None.

    None when the self-belief is not confident enough to warrant investigation.
    """
    if self_belief.confidence.value < threshold:
        return None
    return CuriosityImpulse(
        trigger=f"Reduce the uncertainty behind: {self_belief.statement}",
        rationale=self_belief.statement,
        prompted_by_belief_id=self_belief.id,
    )
