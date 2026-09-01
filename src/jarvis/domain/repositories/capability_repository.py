"""The contract for persisting candidate and acquired capabilities (Odysseus).

Capability acquisition is part of Jarvis's continuity: a capability proposed in
one session should be rememberable and evolvable in a later one, so the scout
can tell a repeated need from a fresh one and acquisition can actually persist.
This is a domain-level *interface* (a Protocol); concrete storage lives in
``jarvis.infrastructure`` behind it (D10).
"""

from __future__ import annotations

from typing import Protocol

from jarvis.domain.value_objects.capability import Capability


class CapabilityRepository(Protocol):
    """Persists capabilities and retrieves them by name."""

    def get_by_name(self, name: str) -> Capability | None:
        """Return the capability with this name, or None if unknown."""
        ...

    def save(self, capability: Capability) -> None:
        """Persist (insert or update) a capability."""
        ...

    def all_capabilities(self) -> tuple[Capability, ...]:
        """Every capability currently stored."""
        ...
