"""Tests for the calendar capability seam (Odysseus #6).

Covers the ``CalendarEvent`` value object, the ``CalendarStore`` Protocol
surface, the ``CalendarCapability`` provider, and Jarvis's integration:
``can_do`` reflects a wired store, the calendar methods hand read/write to the
store edge, and an unwired Jarvis stays offline with clear errors.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jarvis.domain.retrieval.calendar_store import CalendarStore
from jarvis.domain.value_objects.calendar_event import CalendarEvent
from jarvis.domain.value_objects.capability import Capability
from jarvis.infrastructure.capability_registry import (
    CalendarCapability,
    build_default_registry,
)
from jarvis.jarvis import Jarvis


class _FakeCalendarStore:
    """An in-memory calendar store recording calls for deterministic assertions."""

    def __init__(self) -> None:
        self._events: dict[str, CalendarEvent] = {}
        self.created: list[str] = []
        self.deleted: list[str] = []

    def list_events(self, *, limit: int = 100) -> tuple[CalendarEvent, ...]:
        events = sorted(self._events.values(), key=lambda e: e.start)
        return tuple(events[:limit])

    def get_event(self, event_id: str) -> CalendarEvent:
        return self._events[event_id]

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
        n = len(self._events) + 1
        event = CalendarEvent(
            id=f"e{n}", title=title, start=start, end=end,
            description=description, location=location, all_day=all_day,
        )
        self._events[event.id] = event
        self.created.append(event.id)
        return event

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
        event = CalendarEvent(
            id=event_id, title=title, start=start, end=end,
            description=description, location=location, all_day=all_day,
        )
        self._events[event_id] = event
        return event

    def delete_event(self, event_id: str) -> None:
        self.deleted.append(event_id)
        self._events.pop(event_id, None)

    def events_in_range(
        self, start: datetime, end: datetime, *, limit: int = 100
    ) -> tuple[CalendarEvent, ...]:
        return tuple(
            e for e in self._events.values()
            if e.start <= end and e.end >= start
        )[:limit]


def _event_start(offset_hours: int = 1) -> datetime:
    return datetime(2026, 9, 1, 10, 0, tzinfo=UTC) + timedelta(hours=offset_hours)


def _event_end(offset_hours: int = 2) -> datetime:
    return datetime(2026, 9, 1, 10, 0, tzinfo=UTC) + timedelta(hours=offset_hours)


class TestCalendarEvent:
    def test_requires_title(self) -> None:
        with pytest.raises(ValueError, match="title"):
            CalendarEvent(
                id="1", title="", start=_event_start(), end=_event_end(),
            )

    def test_end_must_not_precede_start(self) -> None:
        with pytest.raises(ValueError, match="end must not precede start"):
            CalendarEvent(
                id="1", title="meeting", start=_event_end(), end=_event_start(),
            )

    def test_records_provenance(self) -> None:
        event = CalendarEvent(
            id="42", title="standup", start=_event_start(), end=_event_end(),
        )
        assert event.provenance == "calendar event 42 'standup'"


class TestCalendarStoreProtocol:
    def test_fake_store_satisfies_the_protocol(self) -> None:
        assert isinstance(_FakeCalendarStore(), CalendarStore)


class TestCalendarCapability:
    def test_calendar_capability_backs_the_calendar_name(self) -> None:
        provider = CalendarCapability(_FakeCalendarStore())  # type: ignore[arg-type]
        assert provider.capability == "manage calendar"
        assert provider.is_available()

    def test_default_registry_backs_calendar_when_a_store_is_wired(self) -> None:
        store = _FakeCalendarStore()
        registry = build_default_registry(None, calendar_store=store)  # type: ignore[arg-type]
        assert registry.provider_for("manage calendar") is not None

    def test_default_registry_without_a_store_has_no_calendar(self) -> None:
        registry = build_default_registry(None)
        assert registry.provider_for("manage calendar") is None


class TestJarvisCalendar:
    @staticmethod
    def _acquire(jarvis: Jarvis) -> None:
        capability = Capability(
            name="manage calendar",
            description="see and schedule calendar events",
            requirement="a wired calendar store at the edge (CalendarStore)",
            provenance="test",
        )
        jarvis.remember_capability(capability)
        jarvis.acquire_capability("manage calendar")

    def test_can_do_reflects_a_wired_store(self) -> None:
        jarvis = Jarvis(calendar_store=_FakeCalendarStore())  # type: ignore[arg-type]
        self._acquire(jarvis)
        assert jarvis.can_do("manage calendar")

    def test_unwired_jarvis_is_offline_to_calendar(self) -> None:
        jarvis = Jarvis()
        self._acquire(jarvis)
        assert not jarvis.can_do("manage calendar")

    def test_create_and_read_round_trips(self) -> None:
        jarvis = Jarvis(calendar_store=_FakeCalendarStore())  # type: ignore[arg-type]
        event = jarvis.create_calendar_event(
            title="standup", start=_event_start(), end=_event_end(),
        )
        assert event.id
        assert jarvis.get_calendar_event(event.id).title == "standup"
        titles = [e.title for e in jarvis.list_calendar_events()]
        assert titles[-1] == "standup"

    def test_update_and_delete(self) -> None:
        store = _FakeCalendarStore()
        jarvis = Jarvis(calendar_store=store)  # type: ignore[arg-type]
        event = jarvis.create_calendar_event(
            title="a", start=_event_start(), end=_event_end(),
        )
        jarvis.update_calendar_event(
            event.id, title="a2", start=_event_start(3), end=_event_end(4),
            description="d", location="l", all_day=True,
        )
        assert jarvis.get_calendar_event(event.id).title == "a2"
        jarvis.delete_calendar_event(event.id)
        assert store.deleted == [event.id]

    def test_events_in_range(self) -> None:
        jarvis = Jarvis(calendar_store=_FakeCalendarStore())  # type: ignore[arg-type]
        jarvis.create_calendar_event(
            title="morning", start=_event_start(0), end=_event_end(0),
        )
        jarvis.create_calendar_event(
            title="afternoon", start=_event_start(5), end=_event_end(5),
        )
        # Query overlapping only the morning slot
        day_start = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
        noon = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
        events = jarvis.calendar_events_in_range(day_start, noon)
        titles = [e.title for e in events]
        assert "morning" in titles
        assert "afternoon" not in titles

    def test_wiring_a_store_at_runtime_updates_can_do(self) -> None:
        jarvis = Jarvis()
        self._acquire(jarvis)
        assert not jarvis.can_do("manage calendar")
        jarvis.set_calendar_store(_FakeCalendarStore())  # type: ignore[arg-type]
        assert jarvis.can_do("manage calendar")
        jarvis.set_calendar_store(None)
        assert not jarvis.can_do("manage calendar")

    def test_methods_raise_clearly_when_offline(self) -> None:
        jarvis = Jarvis()
        with pytest.raises(RuntimeError, match="calendar capability"):
            jarvis.list_calendar_events()
