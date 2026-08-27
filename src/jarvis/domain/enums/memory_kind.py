"""What kind of remembered thing a recalled memory is (Vision §3, §21, §22).

Retrieval spans several stores that already exist -- world beliefs, episodic
records, the companion model, goal reachability. A recalled item names which one
it came from so the caller can treat a remembered *conclusion* differently from a
remembered *fact about the companion* without re-deriving that from the text.

This is memory, not truth (Vision §22): the kind describes provenance, not
correctness. Only the kinds retrieval covers today are defined; more are added
when a store actually becomes recallable.
"""

from __future__ import annotations

from enum import Enum


class MemoryKind(Enum):
    """The store a recalled memory was drawn from."""

    WORLD_BELIEF = "world_belief"  # a conclusion Jarvis reasoned to (beliefs)
    EPISODE = "episode"  # a completed cognitive episode (episodic memory)
    COMPANION_TRAIT = "companion_trait"  # something believed about the companion
    GOAL = "goal"  # a goal's learned reachability
