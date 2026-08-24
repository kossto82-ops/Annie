"""StateSummary: a compact, immutable snapshot of everything Jarvis holds.

A single read-model over the existing surfaces -- for logging, debugging, or a
UI -- so callers don't have to stitch together `episodes.history()`,
`self_beliefs()`, `companion.beliefs()` and the action store by hand. Every field
traces to real state; a fresh Jarvis produces an all-empty summary.

Each ``(statement, confidence)`` pair carries the belief's statement and its
current derived confidence -- never a stored "truth" (Vision §22).
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.enums.action_stance import ActionStance

Scored = tuple[str, float]


@dataclass(frozen=True, slots=True, kw_only=True)
class LearnedAction:
    """What Jarvis has learned about a kind of action, and how it would treat it."""

    description: str
    confidence: float  # derived confidence that its predictions about this action hold
    stance: ActionStance  # the recommended stance from that learning + reversibility


@dataclass(frozen=True, slots=True, kw_only=True)
class StateSummary:
    """What Jarvis currently holds, at a glance."""

    episode_count: int
    self_tendencies: tuple[Scored, ...]  # recognised biases about its own cognition
    companion_traits: tuple[Scored, ...]  # beliefs about the companion
    learned_actions: tuple[LearnedAction, ...]  # action learning + its stance
    recurring_goals: tuple[tuple[str, int], ...]  # goals kept returning to, with counts
