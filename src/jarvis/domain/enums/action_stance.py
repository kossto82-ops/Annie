"""How autonomously Jarvis should treat a proposed action (Vision §28).

Autonomy is earned through reliability, so Jarvis distinguishes several stances
rather than a bare act/don't-act. Only a small, well-learned, reversible action
is ever *suggested*; anything unproven or irreversible asks first; an action its
experience contradicts is withheld. None of these performs anything.
"""

from __future__ import annotations

from enum import Enum


class ActionStance(Enum):
    """The recommended stance toward taking an action."""

    SUGGEST = "suggest"  # confidently learned and reversible -- offer to do it
    ASK_FIRST = "ask_first"  # unproven, or irreversible -- get permission
    WITHHOLD = "withhold"  # experience contradicts success -- advise against it
