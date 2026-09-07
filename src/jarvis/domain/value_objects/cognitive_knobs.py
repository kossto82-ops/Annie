"""CognitiveKnobs: the runtime-tunable thresholds that shape cognition.

These are the numbers a command center tunes to steer how Jarvis judges: how
confident a conclusion must look to count as *grounded* (D14), what a reflective
hypothesis must clear to be adopted as a belief, and how many times a stuck goal
is turned over before Jarvis stops wondering about it *for now* (Vision §16, §28).

They were module constants living in the executive and the Jarvis composition
root; making them a single, validated, injectable value object keeps every
consumer agreeing on one source of truth (the mirrors in the domain services
that existed to avoid importing the executive disappear) while leaving them
live-tunable via ``dataclasses.replace``. Values are validated here so a bad
threshold is rejected at the value level, like ``Confidence`` (D7).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class CognitiveKnobs:
    """Cognition thresholds with the historical defaults preserved."""

    # Below this evidence-derived confidence a conclusion is not asserted as
    # grounded (D14). A defensible midpoint of [0, 1].
    grounded_confidence: float = 0.5
    # A reflective hypothesis is adopted as a belief only once it leads this
    # confidently (mirrors the grounded threshold, D14) and has survived challenge.
    insight_confidence: float = 0.5
    # Once Jarvis has turned an unreached goal over this many times without its
    # reachability improving, it stops wondering about it *for now*: an honest
    # companion knows when to stop banging on a stuck door. "Not right now",
    # not "never" — reaching the goal or a fresh recurrence resurfaces it.
    max_goal_reflections: int = 3

    def __post_init__(self) -> None:
        for name in ("grounded_confidence", "insight_confidence"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {value}")
        if self.max_goal_reflections < 1:
            raise ValueError(
                f"max_goal_reflections must be at least 1, got {self.max_goal_reflections}"
            )