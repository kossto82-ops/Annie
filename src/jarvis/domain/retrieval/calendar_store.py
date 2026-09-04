"""CalendarStore: the seam between Jarvis and a calendar (Odysseus #6).

A calendar is a *material*, low-risk, reversible capability Jarvis may gain
(Vision §34, and the revised D1: delegating actions is allowed, delegating
cognition is not). Like ``NotesStore``/``MailBox``/``TaskAgent``, this is a
domain Protocol behind which a concrete store adapter lives in
``infrastructure`` (D7): the storage back-end and its transport stay at the
edge, the transport is injectable, and tests stay deterministic and offline
(D8).

A ``CalendarStore`` *stores* and *returns* plain calendar events with
provenance. It never reasons about the events (D6) and never writes to
Jarvis's beliefs or memory on its own. Creating/updating/deleting are
reversible material actions the caller must have gated; reading is retrieval
that becomes candidate evidence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from jarvis.domain.value_objects.calendar_event import CalendarEvent


@runtime_checkable
class CalendarStore(Protocol):
    """Gives Jarvis read and write access to a calendar on request."""

    def list_events(self, *, limit: int = 100) -> tuple[CalendarEvent, ...]:
        """Return up to ``limit`` events, soonest first, as retrieval artifacts.

        An empty tuple is an honest "no events here", not an error. Each event
        carries provenance; Jarvis weighs them as candidate evidence (D6).
        """
        ...

    def get_event(self, event_id: str) -> CalendarEvent:
        """Return one event by its id, or raise when it cannot be retrieved.

        Raises only on a real failure of the underlying store; an unknown id is
        a clear error, never a fabricated event.
        """
        ...

    def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        description: str = "",
        location: str = "",
        all_day: bool = False,
    ) -> CalendarEvent:
        """Create and return an event; a reversible material action on request."""
        ...

    def update_event(
        self,
        event_id: str,
        *,
        title: str,
        start: datetime,
        end: datetime,
        description: str,
        location: str,
        all_day: bool,
    ) -> CalendarEvent:
        """Update an event's fields and return the refreshed event."""
        ...

    def delete_event(self, event_id: str) -> None:
        """Delete an event by its id; a reversible material action on request."""
        ...

    def events_in_range(
        self, start: datetime, end: datetime, *, limit: int = 100
    ) -> tuple[CalendarEvent, ...]:
        """Return events whose time overlaps ``[start, end]``, or () when none match.

        An empty tuple is an honest "nothing in range", not an error.
        """
        ...
