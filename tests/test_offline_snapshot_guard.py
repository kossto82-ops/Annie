"""Offline regression guard: the suite never touches real networks (P0-B).

Proves the TestGoogleCalendarCommand hang stays fixed:
1. The command-center snapshot never performs a live read, even with a remote
   (Google) calendar wired -- the timeline stays empty and honest instead of
   stalling on network I/O. Events load on demand through ``calendar list``.
2. Builders stay opt-in: no store without configuration.
3. Explicit on-demand reads still consult the wired store (fake transport).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from jarvis.infrastructure import google_calendar as gc
from jarvis.interface.command_center import handle, snapshot
from jarvis.jarvis import Jarvis


def _hostile_transport(
    url: str, headers: Mapping[str, str], body: bytes, timeout: float
) -> bytes:
    raise AssertionError(f"snapshot must never read the network (got {url})")


def _event_list_transport(
    url: str, headers: Mapping[str, str], body: bytes, timeout: float
) -> bytes:
    return json.dumps(
        {
            "items": [
                {
                    "id": "e1",
                    "summary": "standup",
                    "description": "morning check-in",
                    "location": "Room A",
                    "start": {"dateTime": "2026-09-01T10:00:00Z"},
                    "end": {"dateTime": "2026-09-01T10:30:00Z"},
                }
            ]
        }
    ).encode("utf-8")


def _google_store(transport: Any) -> gc.GoogleCalendarStore:
    return gc.GoogleCalendarStore(
        "cid",
        "csecret",
        "rt",
        access_token="fresh-access",
        transport=transport,
    )


def _calendar_capable_jarvis(store: gc.GoogleCalendarStore) -> Jarvis:
    jarvis = Jarvis()
    jarvis.set_calendar_store(store)
    from jarvis.domain.enums.capability_status import CapabilityStatus
    from jarvis.domain.value_objects.capability import Capability

    jarvis.remember_capability(
        Capability(
            name="manage calendar",
            description="see and schedule events on a live Google Calendar",
            requirement="a connected calendar store at the edge (CalendarStore)",
            provenance="google calendar",
            status=CapabilityStatus.ACQUIRED,
        )
    )
    return jarvis


class TestSnapshotNeverReadsRemoteCalendars:
    def test_snapshot_with_remote_calendar_wired_is_honest_and_offline(self) -> None:
        jarvis = _calendar_capable_jarvis(_google_store(_hostile_transport))
        state = snapshot(jarvis)
        assert state["calendar"] == {"source": "google", "connected": True}
        assert state["calendar_events"] == []

    def test_handle_with_remote_calendar_wired_returns_promptly(self) -> None:
        from typing import cast

        jarvis = _calendar_capable_jarvis(_google_store(_hostile_transport))
        result = handle(jarvis, "state", {})
        state = cast(dict[str, object], result["state"])
        assert state["calendar"] == {"source": "google", "connected": True}
        assert state["calendar_events"] == []

    def test_calendar_list_still_reads_on_demand(self) -> None:
        jarvis = _calendar_capable_jarvis(_google_store(_event_list_transport))
        result = handle(jarvis, "calendar", {"action": "list"})
        assert result["count"] == 1
        assert "standup" in str(result["reply"])


class TestBuildersStayOptIn:
    def test_no_calendar_store_without_configuration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from jarvis.infrastructure.calendar_store import build_calendar_store

        monkeypatch.delenv("JARVIS_CALENDAR_ROOT", raising=False)
        assert build_calendar_store() is None

    def test_no_google_store_without_credentials(self) -> None:
        assert gc.build_google_calendar_store({}) is None
        assert (
            gc.build_google_calendar_store(
                {
                    gc.ENV_CLIENT_ID: "cid",
                    gc.ENV_CLIENT_SECRET: "csecret",
                }
            )
            is None
        )
