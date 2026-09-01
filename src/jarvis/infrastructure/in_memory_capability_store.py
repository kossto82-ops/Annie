"""In-memory implementation of :class:`CapabilityRepository` (Odysseus).

The simplest storage giving capability continuity within a running process:
capabilities are kept by name, and retrieval returns the *same* object so a
later update (e.g. promoting a proposal to acquired) evolves it. A durable store
can replace this behind the same interface (D10).
"""

from __future__ import annotations

from jarvis.domain.value_objects.capability import Capability


class InMemoryCapabilityStore:
    """A process-lifetime capability store keyed by name."""

    def __init__(self) -> None:
        self._by_name: dict[str, Capability] = {}

    def get_by_name(self, name: str) -> Capability | None:
        return self._by_name.get(name)

    def save(self, capability: Capability) -> None:
        self._by_name[capability.name] = capability

    def all_capabilities(self) -> tuple[Capability, ...]:
        return tuple(self._by_name.values())
