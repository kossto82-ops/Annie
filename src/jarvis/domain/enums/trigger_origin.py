"""What set a cognitive episode in motion (Vision §12).

Only the two origins the system uses today are defined. The vision lists more
(scheduled, contradiction, memory review, ...); they are added when an episode
is actually triggered that way.
"""

from __future__ import annotations

from enum import Enum


class TriggerOrigin(Enum):
    """The source of an episode's trigger."""

    COMPANION = "companion"  # the companion asked something
    CURIOSITY = "curiosity"  # Jarvis initiated it to reduce its own uncertainty
