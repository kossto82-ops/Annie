"""GoogleCalendarStore: a network-backed CalendarStore via Google Calendar API v3.

This is the *live* half of the "manage calendar" capability (Odysseus #6), served
by Google's Calendar API instead of a local JSON file. Like every edge seam in the
codebase, it is a provider-agnostic adapter behind the domain :class:`CalendarStore`
Protocol: the domain never sees Google, and the adapter never reasons (D6).

Network stays at the edge (Vision §38, D8): the actual HTTP fetch is a ``transport``
callable, injectable so offline tests never touch the network and run
deterministically. OAuth 2.0 tokens and client credentials come from the environment
(``JARVIS_GOOGLE_*``), never from source control, mirroring how the LLM keys and the
mail password are stored.

Availability is opt-in: :func:`build_google_calendar_store` returns ``None`` without
a client id, client secret, and a saved refresh token, so a Jarvis built from it stays
offline to Google by default (D7/D8). While the OAuth flow is ``None`` / unconfigured,
the ordinary (local) calendar store can still serve the capability.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from jarvis.domain.value_objects.calendar_event import CalendarEvent

# OAuth 2.0 / Google Calendar API endpoints.
_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_CALENDAR_API = "https://www.googleapis.com/calendar/v3"

# The scope we ask for: read/write on the primary calendar.
_SCOPE = "https://www.googleapis.com/auth/calendar"

# Env vars, namespaced like every other secret in the project (never in source control).
ENV_CLIENT_ID = "JARVIS_GOOGLE_CALENDAR_CLIENT_ID"
ENV_CLIENT_SECRET = "JARVIS_GOOGLE_CALENDAR_CLIENT_SECRET"
ENV_REFRESH_TOKEN = "JARVIS_GOOGLE_CALENDAR_REFRESH_TOKEN"

Transport = Callable[[str, Mapping[str, str], bytes, float], bytes]


def _urllib_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> bytes:
    request = urllib.request.Request(url, data=body or None, headers=dict(headers))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _ts(dt: datetime) -> str:
    """RFC 3339 timestamp without fractional seconds, as the Calendar API expects."""
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class GoogleCalendarAuthError(RuntimeError):
    """Google refused to authorise/refresh a token, or the flow is misused."""


class GoogleCalendarStore:
    """A :class:`CalendarStore` whose events live in Google Calendar (primary calendar).

    Implements the same Protocol as :class:`LocalCalendarStore`, so the Command Center
    and the domain treat a Google-backed calendar exactly like a local one -- only the
    edge differs. OAuth credentials and the refresh token come from the environment; the
    HTTP transport is injectable for offline, deterministic tests (D8).
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        *,
        access_token: str | None = None,
        timeout: float = 30.0,
        transport: Transport | None = None,
        calendar_id: str = "primary",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._timeout = timeout
        self._transport: Transport = transport or _urllib_transport
        self._calendar_id = calendar_id
        # A freshly exchanged access token may be supplied at construction; otherwise we
        # lazily refresh on first use.
        self._access_token: str | None = access_token
        self._access_expiry: datetime | None = (
            datetime.now(UTC) + timedelta(hours=1) if access_token else None
        )

    # -- OAuth: token machinery -------------------------------------------------

    def _refresh(self) -> None:
        """Exchange the refresh token for a fresh access token."""
        body = urllib.parse.urlencode(
            {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        raw = self._transport(_TOKEN_ENDPOINT, headers, body, self._timeout)
        try:
            data: dict[str, Any] = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise GoogleCalendarAuthError(
                "Google returned a non-JSON token response (check your credentials)."
            ) from exc
        if "access_token" not in data:
            raise GoogleCalendarAuthError(
                f"Google token refresh failed: {data.get('error', 'unknown error')}"
            )
        self._access_token = str(data["access_token"])
        expires = data.get("expires_in")
        self._access_expiry = datetime.now(UTC) + timedelta(
            seconds=int(expires) if isinstance(expires, int) else 3600
        )

    def _bearer(self) -> str:
        """A usable access token, refreshing when it has expired or is absent."""
        if self._access_token is None or (
            self._access_expiry is not None and datetime.now(UTC) >= self._access_expiry
        ):
            self._refresh()
        assert self._access_token is not None
        return self._access_token

    # -- HTTP helpers -----------------------------------------------------------

    def _request(
        self, method: str, path: str, *, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Perform an authenticated JSON request against the Calendar API."""
        url = _CALENDAR_API + path
        headers = {
            "Authorization": f"Bearer {self._bearer()}",
            "Accept": "application/json",
        }
        payload: bytes | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body).encode("utf-8")
        raw = self._transport(url, headers, payload or b"", self._timeout)
        if not raw:
            return {}
        try:
            data: dict[str, Any] = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError(
                f"Google Calendar returned a non-JSON response for {method} {path}."
            ) from exc
        if "error" in data:
            description = data["error"].get("message", "unknown error")
            raise RuntimeError(f"Google Calendar API error: {description}")
        return data

    # -- mapping: CalendarEvent <-> Google event record -------------------------

    @staticmethod
    def _event_to_google(event: CalendarEvent) -> dict[str, Any]:
        rec: dict[str, Any] = {"summary": event.title}
        if event.description:
            rec["description"] = event.description
        if event.location:
            rec["location"] = event.location
        if event.all_day:
            rec["start"] = {"date": event.start.date().isoformat()}
            rec["end"] = {"date": event.end.date().isoformat()}
        else:
            rec["start"] = {"dateTime": _ts(event.start)}
            rec["end"] = {"dateTime": _ts(event.end)}
        return rec

    @staticmethod
    def _event_from_google(event_id: str, rec: dict[str, Any]) -> CalendarEvent:
        start: dict[str, Any] = rec.get("start") or {}
        end: dict[str, Any] = rec.get("end") or {}
        all_day = "date" in start
        start_dt = (
            datetime.fromisoformat(str(start["date"])) if "date" in start
            else datetime.fromisoformat(str(start["dateTime"]).replace("Z", "+00:00"))
        )
        end_dt = (
            datetime.fromisoformat(str(end["date"])) if "date" in end
            else datetime.fromisoformat(str(end["dateTime"]).replace("Z", "+00:00"))
        )
        now = datetime.now(UTC)
        return CalendarEvent(
            id=event_id,
            title=rec.get("summary") or "(untitled)",
            start=start_dt,
            end=end_dt,
            description=rec.get("description") or "",
            location=rec.get("location") or "",
            all_day=all_day,
            created_at=now,
            updated_at=now,
        )

    # -- CalendarStore Protocol -------------------------------------------------

    def list_events(self, *, limit: int = 100) -> tuple[CalendarEvent, ...]:
        query = urllib.parse.urlencode(
            {
                "orderBy": "startTime",
                "singleEvents": "true",
                "maxResults": int(limit),
            }
        )
        data = self._request("GET", f"/calendars/{self._calendar_id}/events?{query}")
        events = [self._event_from_google(i["id"], i) for i in data.get("items", [])]
        events.sort(key=lambda e: e.start)
        return tuple(events[:limit])

    def get_event(self, event_id: str) -> CalendarEvent:
        data = self._request(
            "GET", f"/calendars/{self._calendar_id}/events/{urllib.parse.quote(event_id)}"
        )
        return self._event_from_google(str(data.get("id", event_id)), data)

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
        body = self._event_to_google(
            CalendarEvent(
                id="", title=title, start=start, end=end,
                description=description, location=location, all_day=all_day,
            )
        )
        data = self._request(
            "POST", f"/calendars/{self._calendar_id}/events", body=body
        )
        event_id = str(data.get("id", ""))
        return self.get_event(event_id)

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
        body = self._event_to_google(
            CalendarEvent(
                id=event_id, title=title, start=start, end=end,
                description=description, location=location, all_day=all_day,
            )
        )
        self._request(
            "PUT",
            f"/calendars/{self._calendar_id}/events/{urllib.parse.quote(event_id)}",
            body=body,
        )
        return self.get_event(event_id)

    def delete_event(self, event_id: str) -> None:
        self._request(
            "DELETE",
            f"/calendars/{self._calendar_id}/events/{urllib.parse.quote(event_id)}",
        )

    def events_in_range(
        self, start: datetime, end: datetime, *, limit: int = 100
    ) -> tuple[CalendarEvent, ...]:
        query = urllib.parse.urlencode(
            {
                "timeMin": _ts(start),
                "timeMax": _ts(end),
                "orderBy": "startTime",
                "singleEvents": "true",
                "maxResults": int(limit),
            }
        )
        data = self._request("GET", f"/calendars/{self._calendar_id}/events?{query}")
        events = [self._event_from_google(i["id"], i) for i in data.get("items", [])]
        events.sort(key=lambda e: e.start)
        return tuple(events[:limit])


# -- OAuth flow (the interactive half) ----------------------------------------


def authorize_url(
    client_id: str, *, redirect_uri: str, state: str | None = None
) -> str:
    """Build the Google consent URL the user opens in a browser."""
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    if state:
        params["state"] = state
    return f"{_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    *,
    transport: Transport | None = None,
    timeout: float = 30.0,
) -> tuple[str, str | None]:
    """Exchange an authorisation ``code`` for ``(refresh_token, access_token)``.

    Google returns a refresh token only the first time consent is granted; a subsequent
    exchange yields one already stored. The caller persists the refresh token to the
    environment (following ``llm_config_store``) so a later :class:`GoogleCalendarStore`
    can refresh without re-consent.
    """
    body = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    fn = transport or _urllib_transport
    raw = fn(_TOKEN_ENDPOINT, headers, body, timeout)
    try:
        data: dict[str, Any] = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GoogleCalendarAuthError(
            "Google returned a non-JSON token response (check your client credentials)."
        ) from exc
    if "error" in data:
        raise GoogleCalendarAuthError(
            f"Google rejected the authorisation code: {data.get('error')}"
        )
    refresh = data.get("refresh_token")
    access = data.get("access_token")
    return (str(refresh) if refresh else "", str(access) if access else None)


def build_google_calendar_store(
    environ: Mapping[str, str] | None = None,
    *,
    transport: Transport | None = None,
) -> GoogleCalendarStore | None:
    """Build the Google-backed calendar store, or ``None`` when not fully configured.

    Optics-in: requires a client id, client secret, and a saved refresh token in the
    environment. Without any of the three a Jarvis built from this factory stays offline
    to Google (D7/D8); the local calendar store can still serve the capability.
    """
    env = environ if environ is not None else os.environ
    client_id = env.get(ENV_CLIENT_ID) or ""
    client_secret = env.get(ENV_CLIENT_SECRET) or ""
    refresh_token = env.get(ENV_REFRESH_TOKEN) or ""
    if not client_id or not client_secret or not refresh_token:
        return None
    return GoogleCalendarStore(
        client_id, client_secret, refresh_token, transport=transport
    )


def client_id_from_environ(
    environ: Mapping[str, str] | None = None,
) -> str:
    """The configured Google client id, or ``""`` when not set.

    Read-only lookup used to build the consent URL; never a secret read-back into a
    reply (the client id is not secret, but keeping it out of replies follows the
    project's write-only-secret discipline everywhere).
    """
    env = environ if environ is not None else os.environ
    return env.get(ENV_CLIENT_ID) or ""
