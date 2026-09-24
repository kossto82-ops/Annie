"""CalDavSync: one-way CalDAV/ICS pull into a local CalendarStore (roadmap F6a).

A small, deterministic ICS reader plus a network-backed ``CalDavSync`` adapter
implementing the domain :class:`CalendarSyncer` seam: it fetches an upstream
CalDAV collection / ICS feed over HTTP(S), parses its ``VEVENT`` blocks, and
upserts them into any ``CalendarStore`` under their stable remote ``UID``.

Honest one-way pull (F6/F8): the adapter only ever *creates or updates* local
events from the upstream feed. It never pushes back and never deletes local
events, so a truncated feed, a calendar shuffle, or a flaky upstream can never
destroy the local agenda; the counts returned
(:class:`~jarvis.domain.retrieval.calendar_sync.CalendarSyncResult`) are what
the surface narrates truthfully.

Network stays at the edge (Vision §38, D8): the HTTP fetch is a ``transport``
callable, injectable so offline tests never touch the network and run
deterministically -- exactly the shape :mod:`google_calendar` uses. Credentials
come from the environment (``JARVIS_CALDAV_*``), never from source control.

Recurring events (``RRULE``) are mapped as their single master ``VEVENT``; no
recurrence expansion happens (an honest limitation of the first deepening, and
the adapter never pretends otherwise).
"""

from __future__ import annotations

import base64
import os
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from jarvis.domain.retrieval.calendar_store import CalendarStore
from jarvis.domain.retrieval.calendar_sync import CalendarSyncResult
from jarvis.domain.value_objects.calendar_event import CalendarEvent

# Env vars, namespaced like every other secret in the project (never in source control).
ENV_CALDAV_URL = "JARVIS_CALDAV_URL"
ENV_CALDAV_USERNAME = "JARVIS_CALDAV_USERNAME"
ENV_CALDAV_PASSWORD = "JARVIS_CALDAV_PASSWORD"

Transport = Callable[[str, Mapping[str, str], bytes, float], bytes]


class CalDavSyncError(RuntimeError):
    """The upstream feed could not be fetched or parsed."""


def _parse_duration(value: str) -> timedelta:
    """Parse an ICS ``DURATION`` value such as ``PT1H30M`` or ``P1W``."""
    text = value.strip()
    if not text.startswith("P") or len(text) < 2:
        raise ValueError(f"invalid ICS duration {value!r}")
    body = text[1:]
    days_text, time_text = "0", ""
    if "T" in body:
        days_text, _, time_text = body.partition("T")
    else:
        days_text = body
    days = 0
    if days_text:
        if days_text.endswith("W"):
            days = int(days_text[:-1]) * 7
        elif days_text.endswith("D"):
            days = int(days_text[:-1])
        else:
            raise ValueError(f"invalid ICS duration {value!r}")
    hours = minutes = seconds = 0
    if time_text:
        buf = ""
        for char in time_text:
            if char in "HMS":
                number = int(buf) if buf else 0
                if char == "H":
                    hours = number
                elif char == "M":
                    minutes = number
                else:
                    seconds = number
                buf = ""
            else:
                buf += char
        if buf:
            raise ValueError(f"invalid ICS duration {value!r}")
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def _parse_datetime(raw: str, value_date: bool) -> datetime:
    """Map an ICS ``DTSTART``/``DTEND`` value to a datetime.

    * ``VALUE=DATE`` (all-day): ``20260924`` -> naive midnight.
    * Trailing ``Z``: UTC, aware.
    * Otherwise a floating local time: treated as UTC (ICS carries no zone
      without a ``VTIMEZONE`` block, so this is the deterministic reading).
    """
    text = raw.strip()
    if value_date:
        return datetime.strptime(text[:8], "%Y%m%d")
    if text.endswith("Z"):
        return datetime.strptime(text[:15], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    return datetime.strptime(text, "%Y%m%dT%H%M%S")


def _folded_lines(content: str) -> list[list[str]]:
    """Split ICS text into unfolded ``[name, params, value]`` rows.

    Handles CRLF/CR/LF line endings and RFC 5545 continuation lines (a line
    beginning with a space or tab appends to the previous one).
    """
    physical = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    unfolded: list[str] = []
    for line in physical:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    rows: list[list[str]] = []
    for line in unfolded:
        if not line or line.startswith("#"):
            continue
        first, sep, value = line.partition(":")
        if not sep:
            continue
        segmented = first.split(";", 1)
        name = segmented[0].strip().upper()
        params = segmented[1] if len(segmented) > 1 else ""
        rows.append([name, params, value.strip()])
    return rows


class IcsEvent:
    """One parsed ``VEVENT`` block, ready to become a ``CalendarEvent``."""

    __slots__ = ("uid", "summary", "description", "location", "start", "end", "all_day")

    def __init__(
        self,
        *,
        uid: str,
        summary: str,
        description: str,
        location: str,
        start: datetime,
        end: datetime,
        all_day: bool,
    ) -> None:
        self.uid = uid
        self.summary = summary
        self.description = description
        self.location = location
        self.start = start
        self.end = end
        self.all_day = all_day

    def to_calendar_event(self) -> CalendarEvent:
        """The plain local mapping, identity bound to the remote ``UID``."""
        return CalendarEvent(
            id=self.uid,
            title=self.summary or "(untitled)",
            start=self.start,
            end=self.end,
            description=self.description,
            location=self.location,
            all_day=self.all_day,
        )


def parse_ics(content: str) -> tuple[IcsEvent, ...]:
    """Parse ICS text into its ``VEVENT`` blocks (in feed order).

    Raises :class:`CalDavSyncError` on content that is not ICS at all; events
    that lack a ``UID`` or a usable ``DTSTART``/end are dropped (a feed may
    freely mix cancelled or malformed components).
    """
    rows = _folded_lines(content)
    if not rows or not any(row[0] == "BEGIN" and row[2] == "VEVENT" for row in rows):
        raise CalDavSyncError("no VEVENT components found in the calendar feed")
    events: list[IcsEvent] = []
    block: list[list[str]] = []
    in_event = False
    for row in rows:
        name, _params, value = row
        if name == "BEGIN":
            in_event = value == "VEVENT"
            block = []
            continue
        if name == "END":
            if in_event:
                parsed = _parse_vevent(block)
                if parsed is not None:
                    events.append(parsed)
                in_event = False
            continue
        if in_event:
            block.append(row)
    return tuple(events)


def _params_have(params: str, key: str) -> bool:
    if not params:
        return False
    return any(
        segment.strip().upper() == key for segment in params.split(";") if segment.strip()
    )


def _vevent_value(block: list[list[str]], name: str) -> tuple[str | None, bool]:
    for row_name, params, value in block:
        if row_name == name:
            return value, _params_have(params, "VALUE=DATE")
    return None, False


def _parse_vevent(block: list[list[str]]) -> IcsEvent | None:
    props = {row[0]: row for row in block}
    uid_row = props.get("UID")
    if uid_row is None:
        return None
    uid = uid_row[2]
    if not uid:
        return None
    start_raw, start_value_date = _vevent_value(block, "DTSTART")
    if start_raw is None:
        return None
    try:
        start = _parse_datetime(start_raw, start_value_date)
        end_raw, end_value_date = _vevent_value(block, "DTEND")
        if end_raw is not None:
            end_dt = _parse_datetime(end_raw, end_value_date)
        else:
            duration_raw, _ = _vevent_value(block, "DURATION")
            if duration_raw is None:
                return None
            delta = _parse_duration(duration_raw)
            if delta.total_seconds() <= 0:
                return None
            end_dt = start + delta
        if end_dt <= start:
            return None
    except ValueError:
        return None
    _, _, summary = props.get("SUMMARY", ["", "", ""])
    _, _, description = props.get("DESCRIPTION", ["", "", ""])
    _, _, location = props.get("LOCATION", ["", "", ""])
    return IcsEvent(
        uid=uid,
        summary=summary,
        description=description,
        location=location,
        start=start,
        end=end_dt,
        all_day=start_value_date,
    )


def _urllib_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> bytes:
    request = urllib.request.Request(url, data=body or None, headers=dict(headers))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


class CalDavSync:
    """A :class:`CalendarSyncer` that pulls one upstream CalDAV/ICS feed.

    The ``transport`` is injectable so offline tests never touch the network
    (D8); basic-auth credentials are optional (public ICS feeds need none) and
    only ever come from the environment.
    """

    def __init__(
        self,
        url: str,
        *,
        username: str = "",
        password: str = "",
        timeout: float = 30.0,
        transport: Transport | None = None,
    ) -> None:
        self._url = url
        self._username = username
        self._password = password
        self._timeout = timeout
        self._transport: Transport = transport or _urllib_transport

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "text/calendar, text/plain"}
        if self._username:
            token = base64.b64encode(
                f"{self._username}:{self._password}".encode()
            ).decode("ascii")
            headers["Authorization"] = f"Basic {token}"
        return headers

    def fetch_text(self) -> str:
        """Fetch the upstream feed and return its raw text (offline-injectable)."""
        try:
            raw = self._transport(self._url, self._headers(), b"", self._timeout)
        except Exception as exc:  # noqa: BLE001 - the transport boundary
            raise CalDavSyncError(
                f"could not fetch the calendar feed {self._url!r}: {type(exc).__name__}"
            ) from exc
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CalDavSyncError("the calendar feed is not valid UTF-8 text.") from exc

    def fetch_events(self, *, limit: int | None = None) -> tuple[IcsEvent, ...]:
        """Fetch and parse the upstream ``VEVENT``s, bounded by ``limit``."""
        events = parse_ics(self.fetch_text())
        if limit is not None:
            events = events[: int(limit)]
        return events

    def sync_into(
        self, store: CalendarStore, *, limit: int | None = None
    ) -> CalendarSyncResult:
        """Upsert the upstream events into ``store`` (one-way; never deletes)."""
        events = self.fetch_events(limit=limit)
        added = updated = unchanged = skipped = 0
        for event in events:
            candidate = event.to_calendar_event()
            try:
                current = store.get_event(candidate.id)
            except KeyError:
                store.create_event(
                    title=candidate.title,
                    start=candidate.start,
                    end=candidate.end,
                    description=candidate.description,
                    location=candidate.location,
                    all_day=candidate.all_day,
                    event_id=candidate.id,
                )
                added += 1
                continue
            if (
                current.title == candidate.title
                and current.start == candidate.start
                and current.end == candidate.end
                and current.description == candidate.description
                and current.location == candidate.location
                and current.all_day == candidate.all_day
            ):
                unchanged += 1
                continue
            store.update_event(
                candidate.id,
                title=candidate.title,
                start=candidate.start,
                end=candidate.end,
                description=candidate.description,
                location=candidate.location,
                all_day=candidate.all_day,
            )
            updated += 1
        return CalendarSyncResult(
            added=added, updated=updated, unchanged=unchanged, skipped=skipped
        )


def _auth_from_environ(
    environ: Mapping[str, str],
) -> tuple[str, str]:
    return environ.get(ENV_CALDAV_USERNAME, ""), environ.get(ENV_CALDAV_PASSWORD, "")


def build_caldav_sync(
    environ: Mapping[str, str] | None = None,
    *,
    transport: Transport | None = None,
) -> CalDavSync | None:
    """Build the CalDAV/ICS sync adapter, or ``None`` when not configured.

    Opts-in on ``JARVIS_CALDAV_URL`` (a public ICS feed or a CalDAV collection
    URL; basic auth is optional via ``JARVIS_CALDAV_USERNAME``/``JARVIS_CALDAV_PASSWORD``).
    Without the URL a Jarvis built from this factory has no sync configured and
    `calendar sync` replies honestly (D7/D8).
    """
    env = environ if environ is not None else os.environ
    url = (env.get(ENV_CALDAV_URL) or "").strip()
    if not url:
        return None
    username, password = _auth_from_environ(env)
    return CalDavSync(url, username=username, password=password, transport=transport)


__all__ = [
    "CalDavSync",
    "CalDavSyncError",
    "ENV_CALDAV_PASSWORD",
    "ENV_CALDAV_URL",
    "ENV_CALDAV_USERNAME",
    "IcsEvent",
    "parse_ics",
]