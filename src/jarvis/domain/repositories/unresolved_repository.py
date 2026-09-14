"""UnresolvedRepository: persistence behind open-question continuity.

The domain owns the contract; JSON and SQLite adapters implement it.
History is preserved: resolving keeps the item (marked resolved) instead
of deleting it.
"""

from __future__ import annotations

from typing import Protocol

from jarvis.domain.value_objects.unresolved_item import UnresolvedItem


class UnresolvedRepository(Protocol):
    """Durable storage for open and resolved questions."""

    def save(self, item: UnresolvedItem) -> None:
        """Persist (insert or update) an item."""
        ...

    def get(self, item_id: str) -> UnresolvedItem | None:
        """Return the item with this id, or None."""
        ...

    def open_items(self) -> tuple[UnresolvedItem, ...]:
        """Every still-open question, oldest first."""
        ...

    def all_items(self) -> tuple[UnresolvedItem, ...]:
        """Every item including resolved history, oldest first."""
        ...
