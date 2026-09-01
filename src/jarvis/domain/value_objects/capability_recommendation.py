"""CapabilityRecommendation: a stance toward acquiring a capability (Odysseus).

Mirrors :class:`ActionRecommendation` (Vision §28): the recommendation is derived
from the confidence of the *need* belief -- how strongly Jarvis's evidence says it
needs this capability -- plus whether it is already available. It only recommends;
acquiring remains a deliberate, separate step.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.enums.capability_stance import CapabilityStance
from jarvis.domain.value_objects.confidence import Confidence


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityRecommendation:
    """What Jarvis recommends about acquiring a capability, and why."""

    stance: CapabilityStance
    confidence: Confidence  # derived confidence of the need behind the capability
    rationale: str
