"""CalendarSyncer: the seam for one-way CalDAV/ICS pulls (roadmap F6a).

A ``CalendarSyncer`` deepens the calendar edge behind the existing
``CalendarStore`` Protocol (D7): it *consumes* a store and an upstream feed,
then upserts remote events into the store under their stable remote UID. One-way
by design -- it never pushes local events upstream and never deletes local
events on its own, so a live sync cannot destroy the local agenda (D8).

Sync is a material, reversible, *on request* action: the surface runs it only
when the companion asks (the ``calendar sync`` command), the transport is an
injectable callable so tests stay offline and deterministic, and the adapter
never reasons about the events it writes (D6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from jarvis.domain.retrieval.calendar_store import CalendarStore


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarSyncResult:
    """The outcome of one pull: how remote events became local events."""

    added: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0

    @property
    def total(self) -> int:
        """Every upstream event the pull saw, count-wise."""
        return self.added + self.updated + self.unchanged + self.skipped


@runtime_checkable
class CalendarSyncer(Protocol):
    """Pulls an upstream CalDAV/ICS feed into a CalendarStore on request."""

    def sync_into(
        self, store: CalendarStore, *, limit: int | None = None
    ) -> CalendarSyncResult:
        """Upsert upstream events into ``store`` and report what changed.

        New UIDs are created; existing UIDs whose mapped fields differ are
        updated; identical events are left untouched. Local-only events are
        never deleted (one-way pull).
        """
        ...