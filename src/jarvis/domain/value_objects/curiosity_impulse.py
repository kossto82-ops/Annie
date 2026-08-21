"""CuriosityImpulse: a self-generated urge to reduce a known uncertainty.

Curiosity (Vision §16) turns a recognised weakness or unknown into the intent to
investigate it. An impulse is a *recommendation* -- it names an internal trigger
Jarvis could pursue and why -- not an action taken. Whether it is pursued is a
separate, deliberate step (Vision §28: autonomy is earned).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class CuriosityImpulse:
    """A proposed self-triggered investigation."""

    trigger: str  # what Jarvis would look into
    rationale: str  # why -- the self-belief that prompted it
    prompted_by_belief_id: str
