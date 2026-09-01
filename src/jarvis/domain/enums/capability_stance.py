"""How strongly Jarvis should pursue acquiring a capability (Odysseus, Vision §34, §28).

Capability acquisition is earned, not automatic: only a capability whose *need* is
confidently supported by evidence is suggested; an uncertain need asks first; one whose
need is contradicted is withheld (e.g. it has been tried and failed, or the gap is no
longer real). None of these acquires anything.
"""

from __future__ import annotations

from enum import Enum


class CapabilityStance(Enum):
    """The recommended stance toward acquiring a capability."""

    SUGGEST = "suggest"  # confidently-needed, not yet acquired -- offer to add it
    ASK_FIRST = "ask_first"  # need uncertain, or already available -- get the go-ahead
    WITHHOLD = "withhold"  # need is contradicted -- advise against pursuing it
