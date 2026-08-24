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
    rationale: str  # why -- the belief or pattern that prompted it
    # The self/companion belief that prompted this, when there is one. Some
    # impulses arise from a pattern in memory (e.g. a recurring goal) rather than
    # a single belief, so this is optional -- the rationale still explains the why.
    prompted_by_belief_id: str | None = None
    # The goal this impulse concerns, when it was raised from a recurring goal, so
    # pursuing it can be recorded *toward* that goal in episodic memory. None for
    # impulses about a self-tendency or the companion.
    goal: str | None = None
    # The load-bearing observation this impulse wants to reflect on (Increment 80),
    # when it was raised from an un-mined pattern in the belief web. When set,
    # pursuing the impulse runs the reflective cycle. None for other impulses.
    reflect_on: str | None = None
