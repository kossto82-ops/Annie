"""ActionRecommendation: a stance toward an action, with its reasoning (Vision §28)."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.enums.action_stance import ActionStance
from jarvis.domain.value_objects.confidence import Confidence


@dataclass(frozen=True, slots=True, kw_only=True)
class ActionRecommendation:
    """What Jarvis recommends doing about a proposed action, and why."""

    stance: ActionStance
    confidence: Confidence  # confidence in the learned belief about this action kind
    rationale: str
