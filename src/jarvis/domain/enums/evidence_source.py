"""Where a piece of evidence came from.

Provenance matters (Vision §8): the same claim carries different weight
depending on whether it was directly observed, explicitly stated by the
companion, seen repeatedly, or produced by an action's outcome. This enum names
the origins; policy that maps a source to a default weight is a later increment.
"""

from __future__ import annotations

from enum import Enum


class EvidenceSource(Enum):
    """The origin of a piece of evidence (Vision §8)."""

    DIRECT_OBSERVATION = "direct_observation"
    USER_STATEMENT = "user_statement"
    REPEATED_BEHAVIOR = "repeated_behavior"
    EXTERNAL_SOURCE = "external_source"
    ACTION_OUTCOME = "action_outcome"
    SYSTEM_OBSERVATION = "system_observation"
