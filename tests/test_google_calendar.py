"""Offline tests for the live Google Calendar edge (Odysseus #6).

Covers the ``GoogleCalendarStore`` adapter (against a fake HTTP ``transport``, so
nothing touches the network), the OAuth helpers (``authorize_url`` and
``exchange_code``), the opt-in ``build_google_calendar_store`` factory, and the
``google_calendar`` command surface in the command center.

Network stays at the edge (D8): every test injects a fake ``transport``; a Jarvis
with no Google environment configured stays offline.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from jarvis.domain.retrieval.calendar_store import CalendarStore
from jarvis.infrastructure import google_calendar as gc
from jarvis.interface import command_center as cc
from jarvis.interface.command_center import handle, route
from jarvis.jarvis import Jarvis

_CLIENT_ID = "client-123.apps.googleusercontent.com"
_CLIENT_SECRET = "secret"
_REDIRECT = "http://127.0.0.1:8765/api/auth/google/callback"


@dataclass
class _Call:
    url: str
    headers: dict[str, str]
    body: bytes


class _FakeTransport:
    """A scripted HTTP transport returning canned JSON per call."""

    def __init__(self, responses: list[tuple[str, Any]]) -> None:
        self._responses = responses
        self.calls: list[_Call] = []

    def __call__(
        self, url: str, headers: Mapping[str, str], body: bytes, timeout: float
    ) -> bytes:
        self.calls.append(_Call(url, dict(headers), body))
        kind, payload = self._responses[len(self.calls) - 1]
        if kind == "error":
            raise RuntimeError(payload)
        return json.dumps(payload).encode("utf-8")


def _token_payload() -> dict[str, Any]:
    return {
        "access_token": "fresh-access",
        "expires_in": 3600,
        "token_type": "Bearer",
    }


def _event_payload(event_id: str = "e1") -> dict[str, Any]:
    return {
        "id": event_id,
        "summary": "standup",
        "description": "morning check-in",
        "location": "Room A",
        "start": {"dateTime": "2026-09-01T10:00:00Z"},
        "end": {"dateTime": "2026-09-01T10:30:00Z"},
    }


def _at(offset_hours: int = 0) -> datetime:
    return datetime(2026, 9, 1, 10, 0, tzinfo=UTC) + timedelta(hours=offset_hours)


def _fake_exchange(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    *,
    transport: Any = None,
    timeout: float = 30.0,
) -> tuple[str, str | None]:
    return ("refreshed", "access")


def _bad_exchange(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    *,
    transport: Any = None,
    timeout: float = 30.0,
) -> tuple[str, str | None]:
    raise gc.GoogleCalendarAuthError("rejected")


def _noop_persist(_env: dict[str, str]) -> None:
    return None


class TestGoogleCalendarStoreIsACalendarStore:
    def test_it_conforms_to_the_protocol(self) -> None:
        store = gc.GoogleCalendarStore(_CLIENT_ID, _CLIENT_SECRET, "rt")
        assert isinstance(store, CalendarStore)

    def test_list_events_maps_and_sorts(self) -> None:
        transport = _FakeTransport(
            [("json", {"items": [dict(_event_payload("b"), summary="b")]})]
        )
        store = gc.GoogleCalendarStore(
            _CLIENT_ID, _CLIENT_SECRET, "rt",
            access_token="tok", transport=transport,
        )
        events = store.list_events()
        assert len(events) == 1
        assert events[0].title == "b"
        assert events[0].location == "Room A"
        assert events[0].description == "morning check-in"
        assert events[0].all_day is False
        assert "Bearer tok" in transport.calls[0].headers["Authorization"]
        assert "maxResults=100" in transport.calls[0].url

    def test_list_events_obeys_limit(self) -> None:
        transport = _FakeTransport([("json", {"items": []})])
        store = gc.GoogleCalendarStore(
            _CLIENT_ID, _CLIENT_SECRET, "rt",
            access_token="tok", transport=transport,
        )
        store.list_events(limit=25)
        assert "maxResults=25" in transport.calls[0].url

    def test_get_event(self) -> None:
        transport = _FakeTransport([("json", _event_payload("e9"))])
        store = gc.GoogleCalendarStore(
            _CLIENT_ID, _CLIENT_SECRET, "rt",
            access_token="tok", transport=transport,
        )
        event = store.get_event("e9")
        assert event.id == "e9"
        assert "/calendars/primary/events/e9" in transport.calls[0].url

    def test_create_event_posts_mapped_body(self) -> None:
        transport = _FakeTransport(
            [
                ("json", _event_payload("new1")),
                ("json", _event_payload("new1")),
            ]
        )
        store = gc.GoogleCalendarStore(
            _CLIENT_ID, _CLIENT_SECRET, "rt",
            access_token="tok", transport=transport,
        )
        event = store.create_event(
            title="planning", start=_at(), end=_at(1), location="Zoom"
        )
        assert event.id == "new1"
        created = json.loads(transport.calls[0].body.decode("utf-8"))
        assert created["summary"] == "planning"
        assert created["location"] == "Zoom"
        assert "start" in created

    def test_update_event_puts_mapped_body(self) -> None:
        transport = _FakeTransport(
            [
                ("json", _event_payload("e1")),
                ("json", _event_payload("e1")),
            ]
        )
        store = gc.GoogleCalendarStore(
            _CLIENT_ID, _CLIENT_SECRET, "rt",
            access_token="tok", transport=transport,
        )
        event = store.update_event(
            "e1", title="retitled", start=_at(), end=_at(1),
            description="", location="", all_day=False,
        )
        assert event.title == "standup"
        assert transport.calls[0].url.startswith(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events/e1"
        )
        assert transport.calls[0].headers.get("Content-Type") == "application/json"

    def test_delete_event_issues_delete(self) -> None:
        transport = _FakeTransport([("json", {})])
        store = gc.GoogleCalendarStore(
            _CLIENT_ID, _CLIENT_SECRET, "rt",
            access_token="tok", transport=transport,
        )
        store.delete_event("e1")
        assert "/calendars/primary/events/e1" in transport.calls[0].url

    def test_events_in_range_sends_time_bounds(self) -> None:
        transport = _FakeTransport([("json", {"items": [_event_payload("x")]})])
        store = gc.GoogleCalendarStore(
            _CLIENT_ID, _CLIENT_SECRET, "rt",
            access_token="tok", transport=transport,
        )
        events = store.events_in_range(_at(-1), _at(2))
        assert len(events) == 1
        assert "timeMin=" in transport.calls[0].url
        assert "timeMax=" in transport.calls[0].url

    def test_all_day_events_use_date_fields(self) -> None:
        all_day_rec = {
            "id": "ad1",
            "summary": "holiday",
            "start": {"date": "2026-09-01"},
            "end": {"date": "2026-09-02"},
        }
        transport = _FakeTransport([("json", {}), ("json", all_day_rec)])
        store = gc.GoogleCalendarStore(
            _CLIENT_ID, _CLIENT_SECRET, "rt",
            access_token="tok", transport=transport,
        )
        store.create_event(
            title="holiday", start=_at(), end=_at(24), all_day=True
        )
        created = json.loads(transport.calls[0].body.decode("utf-8"))
        assert "date" in created["start"]
        assert "dateTime" not in created["start"]

    def test_refreshes_token_when_absent(self) -> None:
        transport = _FakeTransport(
            [
                ("json", _token_payload()),
                ("json", {"items": []}),
            ]
        )
        store = gc.GoogleCalendarStore(
            _CLIENT_ID, _CLIENT_SECRET, "rt", transport=transport
        )
        store.list_events()
        assert transport.calls[0].url.startswith("https://oauth2.googleapis.com/token")
        assert "grant_type=refresh_token" in transport.calls[0].body.decode("utf-8")
        # The second call (to the API) used the refreshed token.
        assert "Bearer fresh-access" in transport.calls[1].headers["Authorization"]

    def test_auth_failure_is_a_clear_error(self) -> None:
        transport = _FakeTransport(
            [("json", {"error": "invalid_grant"}), ("json", {"items": []})]
        )
        store = gc.GoogleCalendarStore(
            _CLIENT_ID, _CLIENT_SECRET, "rt", transport=transport
        )
        with pytest.raises(gc.GoogleCalendarAuthError):
            store.list_events()

    def test_api_error_is_raised_not_crashed(self) -> None:
        transport = _FakeTransport(
            [("json", _token_payload()), ("json", {"error": {"message": "rate limited"}})]
        )
        store = gc.GoogleCalendarStore(
            _CLIENT_ID, _CLIENT_SECRET, "rt", transport=transport
        )
        with pytest.raises(RuntimeError, match="rate limited"):
            store.list_events()


class TestOAuthHelpers:
    def test_authorize_url_contains_offline_consent(self) -> None:
        url = gc.authorize_url(_CLIENT_ID, redirect_uri=_REDIRECT)
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth")
        assert "access_type=offline" in url
        assert "response_type=code" in url
        assert "prompt=consent" in url
        assert "scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcalendar" in url
        assert _CLIENT_ID in url

    def test_authorize_url_includes_state_when_given(self) -> None:
        url = gc.authorize_url(_CLIENT_ID, redirect_uri=_REDIRECT, state="abc")
        assert "state=abc" in url

    def test_exchange_code_returns_refresh_and_access(self) -> None:
        transport = _FakeTransport(
            [
                (
                    "json",
                    {
                        "access_token": "acc",
                        "refresh_token": "reftok",
                        "expires_in": 3600,
                    },
                )
            ]
        )
        refresh, access = gc.exchange_code(
            _CLIENT_ID, _CLIENT_SECRET, "the-code", _REDIRECT, transport=transport
        )
        assert refresh == "reftok"
        assert access == "acc"
        body = transport.calls[0].body.decode("utf-8")
        assert "grant_type=authorization_code" in body
        assert "code=the-code" in body

    def test_exchange_rejection_is_a_clear_error(self) -> None:
        transport = _FakeTransport([("json", {"error": "invalid_grant"})])
        with pytest.raises(gc.GoogleCalendarAuthError, match="invalid_grant"):
            gc.exchange_code(
                _CLIENT_ID, _CLIENT_SECRET, "bad", _REDIRECT, transport=transport
            )

    def test_exchange_non_json_is_a_clear_error(self) -> None:
        def garbage(
            url: str, headers: Mapping[str, str], body: bytes, timeout: float
        ) -> bytes:
            return b"<html>oops</html>"

        with pytest.raises(gc.GoogleCalendarAuthError):
            gc.exchange_code(
                _CLIENT_ID, _CLIENT_SECRET, "x", _REDIRECT, transport=garbage
            )


class TestBuilderIsOptIn:
    def test_returns_none_without_credentials(self) -> None:
        assert gc.build_google_calendar_store({}) is None
        assert (
            gc.build_google_calendar_store(
                {gc.ENV_CLIENT_ID: _CLIENT_ID, gc.ENV_CLIENT_SECRET: _CLIENT_SECRET}
            )
            is None
        )

    def test_returns_store_with_all_three(self) -> None:
        store = gc.build_google_calendar_store(
            {
                gc.ENV_CLIENT_ID: _CLIENT_ID,
                gc.ENV_CLIENT_SECRET: _CLIENT_SECRET,
                gc.ENV_REFRESH_TOKEN: "rt",
            }
        )
        assert isinstance(store, CalendarStore)

    def test_client_id_lookup(self) -> None:
        assert gc.client_id_from_environ({}) == ""
        assert gc.client_id_from_environ({gc.ENV_CLIENT_ID: "cid"}) == "cid"


def _google_env_jarvis() -> Jarvis:
    return Jarvis()


class TestServerWiring:
    def test_google_wired_when_configured(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(gc.ENV_CLIENT_ID, _CLIENT_ID)
        monkeypatch.setenv(gc.ENV_CLIENT_SECRET, _CLIENT_SECRET)
        monkeypatch.setenv(gc.ENV_REFRESH_TOKEN, "rt")
        from jarvis.interface.server import create_jarvis

        jarvis = create_jarvis()
        assert isinstance(jarvis.calendar_store, gc.GoogleCalendarStore)

    def test_offline_by_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv(gc.ENV_CLIENT_ID, raising=False)
        monkeypatch.delenv(gc.ENV_CLIENT_SECRET, raising=False)
        monkeypatch.delenv(gc.ENV_REFRESH_TOKEN, raising=False)
        monkeypatch.delenv("JARVIS_CALENDAR_ROOT", raising=False)
        monkeypatch.delenv("JARVIS_TASKS_ROOT", raising=False)
        from jarvis.interface.server import create_jarvis

        jarvis = create_jarvis()
        assert jarvis.calendar_store is None
        assert jarvis.task_scheduler is None

    def test_local_stores_wired_when_roots_configured(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv(gc.ENV_CLIENT_ID, raising=False)
        monkeypatch.setenv("JARVIS_CALENDAR_ROOT", str(tmp_path / "cal"))
        monkeypatch.setenv("JARVIS_TASKS_ROOT", str(tmp_path / "tasks"))
        from jarvis.infrastructure.calendar_store import LocalCalendarStore
        from jarvis.infrastructure.task_scheduler import LocalTaskScheduler
        from jarvis.interface.server import create_jarvis

        jarvis = create_jarvis()
        assert isinstance(jarvis.calendar_store, LocalCalendarStore)
        assert isinstance(jarvis.task_scheduler, LocalTaskScheduler)

    def test_google_takes_precedence_over_local(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(gc.ENV_CLIENT_ID, _CLIENT_ID)
        monkeypatch.setenv(gc.ENV_CLIENT_SECRET, _CLIENT_SECRET)
        monkeypatch.setenv(gc.ENV_REFRESH_TOKEN, "rt")
        monkeypatch.setenv("JARVIS_CALENDAR_ROOT", str(tmp_path / "cal"))
        from jarvis.interface.server import create_jarvis

        jarvis = create_jarvis()
        assert isinstance(jarvis.calendar_store, gc.GoogleCalendarStore)


class TestGoogleCalendarCommand:
    def test_no_action_guides(self) -> None:
        result = handle(_google_env_jarvis(), "google_calendar", {})
        assert "auth" in str(result["reply"])

    def test_status_not_connected_when_unconfigured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(gc.ENV_CLIENT_ID, raising=False)
        monkeypatch.delenv(gc.ENV_CLIENT_SECRET, raising=False)
        monkeypatch.delenv(gc.ENV_REFRESH_TOKEN, raising=False)
        result = handle(_google_env_jarvis(), "google_calendar", {"action": "status"})
        assert result["connected"] is False

    def test_auth_without_client_id_is_a_clear_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(gc.ENV_CLIENT_ID, raising=False)
        result = handle(_google_env_jarvis(), "google_calendar", {"action": "auth"})
        assert "isn't configured" in str(result["reply"])

    def test_auth_returns_consent_url_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(gc.ENV_CLIENT_ID, _CLIENT_ID)
        monkeypatch.setenv(gc.ENV_CLIENT_SECRET, _CLIENT_SECRET)
        result = handle(_google_env_jarvis(), "google_calendar", {"action": "auth"})
        assert "https://accounts.google.com" in str(result["reply"])
        assert "authorize_url" in result

    def test_complete_without_code_is_guided(self) -> None:
        result = handle(_google_env_jarvis(), "google_calendar", {"action": "complete"})
        assert "code" in str(result["reply"])

    def test_complete_wires_store_and_capability(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(gc.ENV_CLIENT_ID, _CLIENT_ID)
        monkeypatch.setenv(gc.ENV_CLIENT_SECRET, _CLIENT_SECRET)
        monkeypatch.setattr(cc.llm_config_store, "persist", _noop_persist)
        monkeypatch.setattr(gc, "exchange_code", _fake_exchange)
        jarvis = _google_env_jarvis()
        result = handle(
            jarvis, "google_calendar", {"action": "complete", "code": "c1"}
        )
        assert "wired" in str(result["reply"])
        assert jarvis.calendar_store is not None
        assert jarvis.can_do("manage calendar")

    def test_complete_is_a_clear_error_on_auth_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(gc.ENV_CLIENT_ID, _CLIENT_ID)
        monkeypatch.setenv(gc.ENV_CLIENT_SECRET, _CLIENT_SECRET)
        monkeypatch.setattr(cc.llm_config_store, "persist", _noop_persist)
        monkeypatch.setattr(gc, "exchange_code", _bad_exchange)
        result = handle(
            _google_env_jarvis(), "google_calendar", {"action": "complete", "code": "x"}
        )
        assert "Couldn't connect" in str(result["reply"])

    def test_disconnect_clears_the_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(gc.ENV_CLIENT_ID, _CLIENT_ID)
        monkeypatch.setenv(gc.ENV_CLIENT_SECRET, _CLIENT_SECRET)
        monkeypatch.setattr(cc.llm_config_store, "persist", _noop_persist)
        monkeypatch.setattr(gc, "exchange_code", _fake_exchange)
        jarvis = _google_env_jarvis()
        handle(jarvis, "google_calendar", {"action": "complete", "code": "c1"})
        result = handle(jarvis, "google_calendar", {"action": "disconnect"})
        assert "disconnected" in str(result["reply"])
        assert jarvis.calendar_store is None


class TestGoogleOauthCallbackRoute:
    def test_callback_without_code_is_an_html_page(self) -> None:
        jarvis = Jarvis()
        response = route(jarvis, "GET", "/api/auth/google/callback", b"")
        assert response.status == 200
        assert response.content_type == "text/html; charset=utf-8"
        assert b"<html" in response.body

    def test_callback_with_error_shows_message(self) -> None:
        jarvis = Jarvis()
        response = route(
            jarvis, "GET", "/api/auth/google/callback?error=access_denied", b""
        )
        assert b"access_denied" in response.body

    def test_callback_codes_are_completed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(gc.ENV_CLIENT_ID, _CLIENT_ID)
        monkeypatch.setenv(gc.ENV_CLIENT_SECRET, _CLIENT_SECRET)
        monkeypatch.setattr(cc.llm_config_store, "persist", _noop_persist)
        monkeypatch.setattr(gc, "exchange_code", _fake_exchange)
        jarvis = Jarvis()
        response = route(
            jarvis, "GET", "/api/auth/google/callback?code=the-code", b""
        )
        assert response.status == 200
        assert b"wired" in response.body
        assert jarvis.can_do("manage calendar")
