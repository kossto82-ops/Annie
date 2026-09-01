"""Where a candidate capability stands in the acquisition journey.

Odysseus (capability acquisition) treats a capability as something Jarvis can
*propose*, *acquire*, or *reject*. This names the phase -- a candidate is not
acquired truth; it is a proposal that must earn its way in through evaluation
(Vision §28: autonomy is earned). Only the phases used today are defined; more
are added when a phase actually exists.
"""

from __future__ import annotations

from enum import Enum


class CapabilityStatus(Enum):
    """The lifecycle phase of a candidate capability (Odysseus)."""

    PROPOSED = "proposed"  # surfaced by the scout as a candidate, not yet evaluated
    ACQUIRED = "acquired"  # Jarvis integrated it as an available capability
    REJECTED = "rejected"  # evaluated and declined (e.g. not worth it, out of scope)
