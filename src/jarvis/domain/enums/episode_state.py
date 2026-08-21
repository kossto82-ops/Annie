"""The lifecycle states a cognitive episode can occupy.

Only the states exercised by the current vertical slice are defined. The full
conceptual lifecycle (OBSERVING, INTERPRETING, FOCUSING, RETRIEVING_MEMORY,
LEARNING, ...) is deliberately not implemented yet -- states are added when a
cognitive operation actually needs them.
"""

from __future__ import annotations

from enum import Enum


class EpisodeState(Enum):
    """States of a :class:`CognitiveEpisode`."""

    CREATED = "created"
    REASONING = "reasoning"
    REFLECTING = "reflecting"
    DECIDING = "deciding"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (EpisodeState.COMPLETED, EpisodeState.FAILED)
