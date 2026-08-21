"""How much reasoning a trigger warrants (Vision §14, §15).

Attention is a limited resource: not every question deserves the full lifecycle.
When Jarvis already holds a confident belief about a trigger and is given nothing
new, it can answer *briefly* from what it understands; a novel or unsettled
trigger warrants *full* reasoning. This is a real routing decision derived from
what Jarvis knows -- not a simulated "energy".
"""

from __future__ import annotations

from enum import Enum


class Attention(Enum):
    """The depth of reasoning an episode was given."""

    FULL = "full"  # a novel or unsettled trigger -- run the whole lifecycle
    BRIEF = "brief"  # already confidently known, nothing new -- answer from it
