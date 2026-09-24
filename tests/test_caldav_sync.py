"""Offline tests for the CalDAV/ICS one-way sync (roadmap F6a).

Covers the deterministic ICS reader (``parse_ics``), the ``CalDavSync`` adapter
against a fake HTTP ``transport`` (nothing touches the network, D8), the opt-in
``build_caldav_sync`` factory, the ``calendar sync`` command surface, and the
honest ``sync`` snapshot field.

One-way is asserted directly: a live sync never deletes local-only events and
never pushes anything upstream.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast

import pytest

from jarvis.domain.retrieval.calendar_sync import CalendarSyncer, CalendarSyncResult
from jarvis.infrastructure import caldav_sync as cs
from jarvis.infrastructure.calendar_store import LocalCalendarStore
from jarvis.interface.command_center import handle, snapshot
from jarvis.jarvis import Jarvis

_ICS_TWO_EVENTS = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "PRODID:-//Test//EN\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:meeting-1\r\n"
    "DTSTAMP:20260901T000000Z\r\n"
    "DTSTART:20260910T100000Z\r\n"
    "DTEND:20260910T110000Z\r\n"
    "SUMMARY:Standup\r\n"
    "DESCRIPTION:Daily sync\r\n"
    "LOCATION:Room 1\r\n"
    "END:VEVENT\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:lunch-2\r\n"
    "DTSTART;VALUE=DATE:20260912\r\n"
    "DTEND;VALUE=DATE:20260913\r\n"
    "SUMMARY:Team lunch\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


def _feed(*events: str) -> str:
    head = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\n"
    tail = "END:VCALENDAR\r\n"
    return head + "".join(events) + tail


class _FakeFeed:
    """A scripted transport serving one ICS document (or a transport error)."""

    def __init__(self, body: str | None = None, error: Exception | None = None) -> None:
        self.body = body
        self.error = error
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(
        self, url: str, headers: Mapping[str, str], body: bytes, timeout: float
    ) -> bytes:
        self.calls.append((url, dict(headers)))
        if self.error is not None:
            raise self.error
        assert self.body is not None
        return self.body.encode("utf-8")


class _MemoryIO:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def __call__(self, operation: str, path: str, content: str) -> str:
        if operation == "read":
            return self.files.get(path, "")
        if operation == "delete":
            self.files.pop(path, None)
            return ""
        self.files[path] = content
        return ""


def _local_store() -> LocalCalendarStore:
    return LocalCalendarStore("cal", io=_MemoryIO())


class TestParseIcs:
    def test_parses_a_multi_event_feed(self) -> None:
        events = cs.parse_ics(_ICS_TWO_EVENTS)
        assert len(events) == 2
        first, second = events
        assert first.uid == "meeting-1"
        assert first.summary == "Standup"
        assert first.start == datetime(2026, 9, 10, 10, 0, tzinfo=UTC)
        assert first.end == datetime(2026, 9, 10, 11, 0, tzinfo=UTC)
        assert first.all_day is False
        assert second.uid == "lunch-2"
        assert second.start == datetime(2026, 9, 12)
        assert second.end == datetime(2026, 9, 13)
        assert second.all_day is True

    def test_unfolds_continuation_lines(self) -> None:
        content = _feed(
            "BEGIN:VEVENT\r\n"
            "UID:f-1\r\n"
            "DTSTART:20260910T100000Z\r\n"
            "DTEND:20260910T110000Z\r\n"
            "DESCRIPTION:line one\r\n"
            " line two\r\n"
            "SUMMARY:S\r\n"
            "END:VEVENT\r\n"
        )
        (event,) = cs.parse_ics(content)
        assert event.description == "line oneline two"

    def test_duration_instead_of_dtend(self) -> None:
        content = _feed(
            "BEGIN:VEVENT\r\n"
            "UID:d-1\r\n"
            "DTSTART:20260915T090000Z\r\n"
            "DURATION:PT1H30M\r\n"
            "SUMMARY:Deep work\r\n"
            "END:VEVENT\r\n"
        )
        (event,) = cs.parse_ics(content)
        assert event.end == datetime(2026, 9, 15, 10, 30, tzinfo=UTC)

    def test_drops_events_without_uid_or_dtstart(self) -> None:
        content = _feed(
            "BEGIN:VEVENT\r\n"
            "UID:keep-1\r\n"
            "DTSTART:20260910T100000Z\r\n"
            "DTEND:20260910T110000Z\r\n"
            "SUMMARY:Keep\r\n"
            "END:VEVENT\r\n"
            "BEGIN:VEVENT\r\n"
            "DTSTART:20260910T100000Z\r\n"
            "DTEND:20260910T110000Z\r\n"
            "SUMMARY:No uid\r\n"
            "END:VEVENT\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:dropline-2\r\n"
            "SUMMARY:No start\r\n"
            "END:VEVENT\r\n"
        )
        events = cs.parse_ics(content)
        assert [e.uid for e in events] == ["keep-1"]

    def test_raises_on_non_ics(self) -> None:
        with pytest.raises(cs.CalDavSyncError, match="no VEVENT"):
            cs.parse_ics("<html>not a calendar</html>")


class TestSyncIntoLocalStore:
    def test_adds_events_under_remote_uids(self) -> None:
        store = _local_store()
        feed = _FakeFeed(_ICS_TWO_EVENTS)
        result = cs.CalDavSync("https://cal.example/feed.ics", transport=feed).sync_into(store)
        assert isinstance(result, CalendarSyncResult)
        assert result == CalendarSyncResult(added=2, updated=0, unchanged=0)
        meeting = store.get_event("meeting-1")
        assert meeting.title == "Standup"
        lunch = store.get_event("lunch-2")
        assert lunch.all_day is True
        assert feed.calls[0][0] == "https://cal.example/feed.ics"

    def test_second_sync_is_unchanged(self) -> None:
        store = _local_store()
        syncer = cs.CalDavSync(
            "https://cal.example/feed.ics", transport=_FakeFeed(_ICS_TWO_EVENTS)
        )
        syncer.sync_into(store)
        result = syncer.sync_into(store)
        assert result == CalendarSyncResult(added=0, updated=0, unchanged=2)

    def test_remote_change_updates_only_the_changed_event(self) -> None:
        store = _local_store()
        syncer = cs.CalDavSync(
            "https://cal.example/feed.ics", transport=_FakeFeed(_ICS_TWO_EVENTS)
        )
        syncer.sync_into(store)
        changed = _ICS_TWO_EVENTS.replace("SUMMARY:Standup", "SUMMARY:Moved standup")
        changed_syncer = cs.CalDavSync(
            "https://cal.example/feed.ics", transport=_FakeFeed(changed)
        )
        result = changed_syncer.sync_into(store)
        assert result == CalendarSyncResult(added=0, updated=1, unchanged=1)
        assert store.get_event("meeting-1").title == "Moved standup"

    def test_never_deletes_local_only_events(self) -> None:
        store = _local_store()
        created = store.create_event(
            title="Local only", start=datetime(2026, 9, 1), end=datetime(2026, 9, 1, 1)
        )
        syncer = cs.CalDavSync(
            "https://cal.example/feed.ics", transport=_FakeFeed(_ICS_TWO_EVENTS)
        )
        result = syncer.sync_into(store)
        assert result.added == 2
        assert store.get_event(created.id).title == "Local only"

    def test_limit_bounds_the_pull(self) -> None:
        store = _local_store()
        syncer = cs.CalDavSync(
            "https://cal.example/feed.ics", transport=_FakeFeed(_ICS_TWO_EVENTS)
        )
        result = syncer.sync_into(store, limit=1)
        assert result == CalendarSyncResult(added=1, updated=0, unchanged=0)
        assert [e.id for e in store.list_events()] == ["meeting-1"]

    def test_fetch_failure_is_a_caldav_error(self) -> None:
        syncer = cs.CalDavSync(
            "https://cal.example/feed.ics",
            transport=_FakeFeed(error=ConnectionError("boom")),
        )
        with pytest.raises(cs.CalDavSyncError, match="could not fetch"):
            syncer.sync_into(_local_store())


class TestBuilderIsOptIn:
    def test_none_without_url(self) -> None:
        assert cs.build_caldav_sync({}) is None
        assert (
            cs.build_caldav_sync({cs.ENV_CALDAV_USERNAME: "u", cs.ENV_CALDAV_PASSWORD: "p"})
            is None
        )

    def test_builds_with_url(self) -> None:
        built = cs.build_caldav_sync({cs.ENV_CALDAV_URL: "https://cal.example/feed.ics"})
        assert isinstance(built, CalendarSyncer)

    def test_basic_auth_header_when_credentials_configured(self) -> None:
        feed = _FakeFeed(_ICS_TWO_EVENTS)
        syncer = cs.CalDavSync(
            "https://cal.example/feed.ics",
            username="user",
            password="secret",
            transport=feed,
        )
        syncer.fetch_text()
        authorization = feed.calls[0][1].get("Authorization", "")
        expected = base64.b64encode(b"user:secret").decode("ascii")
        assert authorization == f"Basic {expected}"

    def test_no_auth_header_for_public_feeds(self) -> None:
        feed = _FakeFeed(_ICS_TWO_EVENTS)
        syncer = cs.CalDavSync("https://cal.example/public.ics", transport=feed)
        syncer.fetch_text()
        assert "Authorization" not in feed.calls[0][1]


def _event_feed_event() -> str:
    return (
        "BEGIN:VEVENT\r\n"
        "UID:standup-9\r\n"
        "DTSTART:20260920T100000Z\r\n"
        "DTEND:20260920T110000Z\r\n"
        "SUMMARY:Standup\r\n"
        "END:VEVENT\r\n"
    )


def _jarvis_with_store_and_sync() -> tuple[Jarvis, LocalCalendarStore]:
    from jarvis.domain.enums.capability_status import CapabilityStatus
    from jarvis.domain.value_objects.capability import Capability

    store = _local_store()
    jarvis = Jarvis()
    jarvis.set_calendar_store(store)
    jarvis.remember_capability(
        Capability(
            name="manage calendar",
            description="see and schedule events",
            requirement="a connected calendar store at the edge (CalendarStore)",
            provenance="test",
            status=CapabilityStatus.ACQUIRED,
        )
    )
    jarvis.set_calendar_sync(
        cs.CalDavSync(
            "https://cal.example/feed.ics",
            transport=_FakeFeed(_feed(_event_feed_event())),
        )
    )
    return jarvis, store


class TestCalendarSyncCommand:
    def test_no_action_hint_includes_sync(self) -> None:
        result = handle(Jarvis(), "calendar", {})
        assert "sync" in str(result["reply"])

    def test_honest_when_no_sync_configured(self) -> None:
        from jarvis.domain.enums.capability_status import CapabilityStatus
        from jarvis.domain.value_objects.capability import Capability

        store = _local_store()
        jarvis = Jarvis()
        jarvis.set_calendar_store(store)
        jarvis.remember_capability(
            Capability(
                name="manage calendar",
                description="see and schedule events",
                requirement="a connected calendar store at the edge (CalendarStore)",
                provenance="test",
                status=CapabilityStatus.ACQUIRED,
            )
        )
        result = handle(jarvis, "calendar", {"action": "sync"})
        assert "No calendar sync" in str(result["reply"])
        assert "JARVIS_CALDAV_URL" in str(result["reply"])

    def test_honest_with_no_calendar_capability(self) -> None:
        result = handle(Jarvis(), "calendar", {"action": "sync"})
        assert "No calendar capability" in str(result["reply"])

    def test_sync_runs_and_reports_counts(self) -> None:
        jarvis, _store = _jarvis_with_store_and_sync()
        result = handle(jarvis, "calendar", {"action": "sync"})
        assert "1 added, 0 updated, 0 unchanged" in str(result["reply"])
        assert result["count"] == 1
        assert jarvis.list_calendar_events()[0].id == "standup-9"

    def test_sync_again_reports_unchanged(self) -> None:
        jarvis, _store = _jarvis_with_store_and_sync()
        handle(jarvis, "calendar", {"action": "sync"})
        result = handle(jarvis, "calendar", {"action": "sync"})
        assert "0 added, 0 updated, 1 unchanged" in str(result["reply"])

    def test_jarvis_surface_raises_without_sync(self) -> None:
        jarvis = Jarvis()
        with pytest.raises(RuntimeError, match="no calendar sync"):
            jarvis.sync_calendar()

    def test_snapshot_reports_the_sync_flag_honestly(self) -> None:
        assert snapshot(Jarvis())["calendar"] == {
            "source": "none",
            "connected": False,
            "sync": False,
        }
        jarvis, _store = _jarvis_with_store_and_sync()
        cal = cast(dict[str, object], snapshot(jarvis)["calendar"])
        assert cal == {"source": "local", "connected": True, "sync": True}