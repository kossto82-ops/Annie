"""Capability: a candidate or acquired ability of Jarvis (Odysseus).

A capability is an extension of Jarvis's ability to *act* (Vision §34): a skill
or tool it could add. It carries what it is (``name``), what it does
(``description``), what adopting it requires (``requirement`` -- the tool,
provider, or input it depends on), and where the idea came from (``provenance``,
typically a matched need). It also names its lifecycle ``status``.

Important boundary: a candidate capability must not itself contain cognition.
It is a capability *provider* -- the core stays the judge of whether to pursue
it and what to make of its results (Vision §32, §38). Acquisition is a separate,
deliberate step from proposing (Vision §28).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from jarvis.domain.enums.capability_status import CapabilityStatus


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class Capability:
    """A possible ability of Jarvis, with what adopting it requires."""

    name: str  # a short label, e.g. "search the web"
    description: str  # what it lets Jarvis do
    requirement: str  # what adopting it depends on (tool/provider/input)
    provenance: str  # where the idea came from, e.g. the need that prompted it
    status: CapabilityStatus = CapabilityStatus.PROPOSED
    id: str = field(default_factory=_new_id)
    proposed_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("A capability requires a non-empty name")
        if not self.description or not self.description.strip():
            raise ValueError("A capability requires a description")
        if not self.requirement or not self.requirement.strip():
            raise ValueError("A capability requires a requirement")
        if not self.provenance or not self.provenance.strip():
            raise ValueError("A capability requires provenance")

    def mark_acquired(self) -> Capability:
        """Return this capability labelled as acquired (Odysseus, Vision §28).

        Replaces the candidate with an acquired one; the original is unchanged
        (capabilities are immutable value objects).
        """
        return Capability(
            name=self.name,
            description=self.description,
            requirement=self.requirement,
            provenance=self.provenance,
            status=CapabilityStatus.ACQUIRED,
            id=self.id,
            proposed_at=self.proposed_at,
        )

    def mark_rejected(self) -> Capability:
        """Return this capability labelled as rejected, keeping its provenance."""
        return Capability(
            name=self.name,
            description=self.description,
            requirement=self.requirement,
            provenance=self.provenance,
            status=CapabilityStatus.REJECTED,
            id=self.id,
            proposed_at=self.proposed_at,
        )
