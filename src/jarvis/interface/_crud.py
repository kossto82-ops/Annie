"""CRUD handlers for stores — calendar, tasks, notes, mail, documents."""

from __future__ import annotations

import base64
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from jarvis.domain.enums.document_owner import DocumentOwner
from jarvis.domain.value_objects.capability import Capability
from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.infrastructure import google_calendar, llm_config_store
from jarvis.jarvis import Jarvis

from jarvis.interface._shared import _capability_not_ready

if TYPE_CHECKING:
    pass

# A reply the UI can render and (optionally) speak; some commands add extra fields.
Reply = dict[str, object]


def _format_calendar_event(event: object) -> str:
    """A readable summary of one calendar event."""
    from jarvis.domain.value_objects.calendar_event import CalendarEvent

    if not isinstance(event, CalendarEvent):
        return str(event)
    lines = [f"Title: {event.title}", f"When: {event.start} → {event.end}"]
    if event.location:
        lines.append(f"Location: {event.location}")
    if event.description:
        lines.append(f"Description: {event.description}")
    lines.append(f"ID: {event.id}")
    return "\n".join(lines)


def _format_scheduled_task(task: object) -> str:
    """A readable summary of one scheduled task."""
    from jarvis.domain.value_objects.scheduled_task import ScheduledTask

    if not isinstance(task, ScheduledTask):
        return str(task)
    lines = [
        f"Name: {task.name}",
        f"Command: {task.command}",
    ]
    if task.cron:
        lines.append(f"Schedule: {task.cron}")
    lines.append(f"Enabled: {'yes' if task.enabled else 'no'}")
    if task.next_run is not None:
        lines.append(f"Next run: {task.next_run}")
    if task.last_run is not None:
        lines.append(f"Last run: {task.last_run} ({task.last_status or 'unknown'})")
        if task.last_output:
            lines.append(f"Last output: {task.last_output[:500]}")
    if task.description:
        lines.append(f"Description: {task.description}")
    lines.append(f"ID: {task.id}")
    return "\n".join(lines)


_GOOGLE_REDIRECT_URI = "http://127.0.0.1:8765/api/auth/google/callback"


def _gain_calendar_capability(jarvis: Jarvis) -> None:
    """Propose and acquire the "manage calendar" capability, if not held yet.

    Used after wiring a live Google store so ``can_do`` reflects the new backing; this
    is the deliberate, earned acquisition (Odysseus, Vision §28). Matches the capability
    the CalendarCapability provider reports, so `can_do` and `calendar list` agree.
    """
    known = [c.name for c in jarvis.capabilities()]
    if "manage calendar" in known:
        return
    jarvis.remember_capability(
        Capability(
            name="manage calendar",
            description="see and schedule events on a live Google Calendar",
            requirement="a connected calendar store at the edge (CalendarStore)",
            provenance="google calendar",
            status=CapabilityStatus.ACQUIRED,
        )
    )


def _google_calendar(jarvis: Jarvis, payload: Reply) -> Reply:
    """Connect Jarvis to a real Google Calendar (Odysseus #6, live edge).

    Actions: ``status`` (is Google wired + connected), ``auth`` (returns the consent
    URL to open in a browser), ``complete`` (hands back the authorisation code to
    exchange for a refresh token and wire the store), and ``disconnect`` (clear the
    saved token and go offline to Google).

    ``auth`` also accepts ``client_id``/``client_secret``: when given they are
    applied to the live process and saved to ``.env`` (write-only, never echoed
    back), so the panel itself asks for the credentials instead of sending the
    companion to edit a file.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use google_calendar with action 'status', 'auth', 'complete', "
            "or 'disconnect'.",
            "speak": False,
        }
    if action == "status":
        store = google_calendar.build_google_calendar_store()
        if store is None:
            return {
                "reply": "Google Calendar is not connected. Run `google_calendar "
                "auth` to link it.",
                "speak": False,
                "connected": False,
            }
        return {
            "reply": "Google Calendar is configured; it serves the calendar capability "
            "when that capability is also earned.",
            "speak": False,
            "connected": True,
        }
    if action == "auth":
        # Credentials from the panel are write-only: staged into the live
        # process and persisted to .env, never echoed back anywhere.
        given_id = str(payload.get("client_id", "")).strip()
        given_secret = str(payload.get("client_secret", "")).strip()
        saved = False
        if given_id or given_secret:
            updates: dict[str, str] = {}
            if given_id:
                os.environ[google_calendar.ENV_CLIENT_ID] = given_id
                updates[google_calendar.ENV_CLIENT_ID] = given_id
            if given_secret:
                os.environ[google_calendar.ENV_CLIENT_SECRET] = given_secret
                updates[google_calendar.ENV_CLIENT_SECRET] = given_secret
            llm_config_store.persist(updates)
            saved = True
        client_id = given_id or google_calendar.client_id_from_environ()
        if not client_id:
            return {
                "reply": "Google Calendar needs its OAuth credentials first: paste the "
                "client ID and secret (Google Cloud Console → OAuth client ID), then "
                "connect again. They are saved to the server's .env and never shown back.",
                "speak": False,
                "redirect_uri": _GOOGLE_REDIRECT_URI,
            }
        url = google_calendar.authorize_url(
            client_id, redirect_uri=_GOOGLE_REDIRECT_URI
        )
        return {
            "reply": ("Credentials saved to .env. " if saved else "")
            + "Open this URL in your browser to authorise: " + url,
            "speak": False,
            "authorize_url": url,
            "redirect_uri": _GOOGLE_REDIRECT_URI,
            "saved": saved,
        }
    if action == "complete":
        code = str(payload.get("code", "")).strip()
        if not code:
            return {
                "reply": "Provide the authorisation code from the redirect.",
                "speak": False,
            }
        client_id = google_calendar.client_id_from_environ()
        client_secret = os.environ.get(google_calendar.ENV_CLIENT_SECRET, "")
        if not client_id or not client_secret:
            return {
                "reply": "Google Calendar needs its OAuth credentials first: run "
                "`google_calendar auth` with the client ID and secret.",
                "speak": False,
            }
        try:
            refresh, access = google_calendar.exchange_code(
                client_id, client_secret, code, redirect_uri=_GOOGLE_REDIRECT_URI
            )
        except google_calendar.GoogleCalendarAuthError as error:
            return {"reply": f"Couldn't connect Google Calendar: {error}", "speak": False}
        if refresh:
            llm_config_store.persist({google_calendar.ENV_REFRESH_TOKEN: refresh})
        # Wire the store directly from the freshly exchanged token — env may not yet hold
        # the refresh token in this process, so a factory read of the environment would
        # (correctly) conclude Google is unconfigured for this run.
        jarvis.set_calendar_store(
            google_calendar.GoogleCalendarStore(
                client_id,
                client_secret,
                refresh,
                access_token=access,
            )
        )
        _gain_calendar_capability(jarvis)
        return {
            "reply": "Google Calendar is now wired as the live calendar store. "
            "Use `calendar list` to see your events.",
            "speak": False,
        }
    if action == "disconnect":
        llm_config_store.persist({google_calendar.ENV_REFRESH_TOKEN: ""})
        jarvis.set_calendar_store(None)
        return {"reply": "Google Calendar disconnected.", "speak": False}
    return {"reply": "Unknown google_calendar action.", "speak": False}


def _calendar(jarvis: Jarvis, payload: Reply) -> Reply:
    """Manage calendar events through the calendar capability (Odysseus #6).

    Actions: ``list``, ``get``, ``create``, ``update``, ``delete``, ``range``.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use calendar with action 'list', 'get', 'create', "
            "'update', 'delete', or 'range'.",
            "speak": False,
        }
    if jarvis.calendar_store is None:
        return {
            "reply": "No calendar capability is wired up right now.",
            "speak": False,
        }
    if not jarvis.can_do("manage calendar"):
        return _capability_not_ready(jarvis, "manage calendar")
    try:
        if action == "list":
            limit_raw = payload.get("limit", 20)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 20
            events = jarvis.list_calendar_events(limit=limit)
            if not events:
                return {"reply": "No calendar events found.", "speak": False}
            lines = [_format_calendar_event(e) for e in events]
            return {
                "reply": "Calendar events:\n\n" + "\n\n".join(lines),
                "speak": False,
                "count": len(events),
            }
        if action == "get":
            event_id = str(payload.get("id", "")).strip()
            if not event_id:
                return {"reply": "Provide an event id.", "speak": False}
            event = jarvis.get_calendar_event(event_id)
            return {"reply": _format_calendar_event(event), "speak": False}
        if action == "create":
            title = str(payload.get("title", "")).strip()
            if not title:
                return {"reply": "Provide a title for the event.", "speak": False}
            start_raw = str(payload.get("start", "")).strip()
            end_raw = str(payload.get("end", "")).strip()
            if not start_raw or not end_raw:
                return {"reply": "Provide start and end datetimes (ISO format).", "speak": False}
            start = datetime.fromisoformat(start_raw)
            end = datetime.fromisoformat(end_raw)
            description = str(payload.get("description", "")).strip()
            location = str(payload.get("location", "")).strip()
            all_day_raw = payload.get("all_day", False)
            all_day = bool(all_day_raw)
            event = jarvis.create_calendar_event(
                title=title, start=start, end=end,
                description=description, location=location, all_day=all_day,
            )
            return {
                "reply": f"Created event: {event.title} (ID: {event.id})",
                "speak": False,
            }
        if action == "update":
            event_id = str(payload.get("id", "")).strip()
            if not event_id:
                return {"reply": "Provide the event id to update.", "speak": False}
            title = str(payload.get("title", "")).strip()
            if not title:
                return {"reply": "Provide a title.", "speak": False}
            start_raw = str(payload.get("start", "")).strip()
            end_raw = str(payload.get("end", "")).strip()
            if not start_raw or not end_raw:
                return {"reply": "Provide start and end datetimes (ISO format).", "speak": False}
            start = datetime.fromisoformat(start_raw)
            end = datetime.fromisoformat(end_raw)
            description = str(payload.get("description", "")).strip()
            location = str(payload.get("location", "")).strip()
            all_day_raw = payload.get("all_day", False)
            all_day = bool(all_day_raw)
            event = jarvis.update_calendar_event(
                event_id, title=title, start=start, end=end,
                description=description, location=location, all_day=all_day,
            )
            return {
                "reply": f"Updated event: {event.title} (ID: {event.id})",
                "speak": False,
            }
        if action == "delete":
            event_id = str(payload.get("id", "")).strip()
            if not event_id:
                return {"reply": "Provide the event id to delete.", "speak": False}
            jarvis.delete_calendar_event(event_id)
            return {"reply": f"Deleted event {event_id}.", "speak": False}
        if action == "range":
            start_raw = str(payload.get("start", "")).strip()
            end_raw = str(payload.get("end", "")).strip()
            if not start_raw or not end_raw:
                return {"reply": "Provide start and end datetimes (ISO format).", "speak": False}
            start = datetime.fromisoformat(start_raw)
            end = datetime.fromisoformat(end_raw)
            limit_raw = payload.get("limit", 20)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 20
            events = jarvis.calendar_events_in_range(start, end, limit=limit)
            if not events:
                return {"reply": "No events in that range.", "speak": False}
            lines = [_format_calendar_event(e) for e in events]
            return {
                "reply": "Events in range:\n\n" + "\n\n".join(lines),
                "speak": False,
                "count": len(events),
            }
    except Exception as error:  # noqa: BLE001 - the store boundary
        return {"reply": f"I couldn't do that ({type(error).__name__}).", "speak": False}
    return {"reply": "Unknown calendar action.", "speak": False}


def _tasks(jarvis: Jarvis, payload: Reply) -> Reply:
    """Manage scheduled tasks through the task-scheduler capability (Odysseus #7).

    Actions: ``list``, ``get``, ``create``, ``update``, ``delete``,
    ``enable``, ``disable``, ``due``, ``run``. ``run`` executes the task's
    command right now through the earned-agency executor and records the
    outcome on the task (last run, status, output); it needs an enabled task
    and a wired executor, else it declines honestly and records nothing.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use tasks with action 'list', 'get', 'create', 'update', "
            "'delete', 'enable', 'disable', 'due', or 'run'.",
            "speak": False,
        }
    if jarvis.task_scheduler is None:
        return {
            "reply": "No task-scheduler capability is wired up right now.",
            "speak": False,
        }
    if not jarvis.can_do("manage tasks"):
        return _capability_not_ready(jarvis, "manage tasks")
    try:
        if action == "list":
            limit_raw = payload.get("limit", 20)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 20
            tasks = jarvis.list_scheduled_tasks(limit=limit)
            if not tasks:
                return {"reply": "No scheduled tasks found.", "speak": False}
            lines = [_format_scheduled_task(t) for t in tasks]
            return {
                "reply": "Scheduled tasks:\n\n" + "\n\n".join(lines),
                "speak": False,
                "count": len(tasks),
            }
        if action == "get":
            task_id = str(payload.get("id", "")).strip()
            if not task_id:
                return {"reply": "Provide a task id.", "speak": False}
            task = jarvis.get_scheduled_task(task_id)
            return {"reply": _format_scheduled_task(task), "speak": False}
        if action == "create":
            name = str(payload.get("name", "")).strip()
            if not name:
                return {"reply": "Provide a name for the task.", "speak": False}
            command = str(payload.get("command", "")).strip()
            if not command:
                return {"reply": "Provide a command for the task.", "speak": False}
            cron = str(payload.get("cron", "")).strip()
            description = str(payload.get("description", "")).strip()
            enabled_raw = payload.get("enabled", True)
            enabled = bool(enabled_raw)
            task = jarvis.create_scheduled_task(
                name=name, command=command, cron=cron,
                description=description, enabled=enabled,
            )
            return {
                "reply": f"Created task: {task.name} (ID: {task.id})",
                "speak": False,
            }
        if action == "update":
            task_id = str(payload.get("id", "")).strip()
            if not task_id:
                return {"reply": "Provide the task id to update.", "speak": False}
            name = str(payload.get("name", "")).strip()
            if not name:
                return {"reply": "Provide a name.", "speak": False}
            command = str(payload.get("command", "")).strip()
            if not command:
                return {"reply": "Provide a command.", "speak": False}
            cron = str(payload.get("cron", "")).strip()
            description = str(payload.get("description", "")).strip()
            enabled_raw = payload.get("enabled", True)
            enabled = bool(enabled_raw)
            task = jarvis.update_scheduled_task(
                task_id, name=name, command=command, cron=cron,
                description=description, enabled=enabled,
            )
            return {
                "reply": f"Updated task: {task.name} (ID: {task.id})",
                "speak": False,
            }
        if action == "delete":
            task_id = str(payload.get("id", "")).strip()
            if not task_id:
                return {"reply": "Provide the task id to delete.", "speak": False}
            jarvis.delete_scheduled_task(task_id)
            return {"reply": f"Deleted task {task_id}.", "speak": False}
        if action == "enable":
            task_id = str(payload.get("id", "")).strip()
            if not task_id:
                return {"reply": "Provide the task id to enable.", "speak": False}
            task = jarvis.enable_scheduled_task(task_id)
            return {
                "reply": f"Enabled task: {task.name} (ID: {task.id})",
                "speak": False,
            }
        if action == "disable":
            task_id = str(payload.get("id", "")).strip()
            if not task_id:
                return {"reply": "Provide the task id to disable.", "speak": False}
            task = jarvis.disable_scheduled_task(task_id)
            return {
                "reply": f"Disabled task: {task.name} (ID: {task.id})",
                "speak": False,
            }
        if action == "due":
            tasks = jarvis.due_scheduled_tasks()
            if not tasks:
                return {"reply": "No tasks are currently due.", "speak": False}
            lines = [_format_scheduled_task(t) for t in tasks]
            return {
                "reply": "Due tasks:\n\n" + "\n\n".join(lines),
                "speak": False,
                "count": len(tasks),
            }
        if action == "run":
            task_id = str(payload.get("id", "")).strip()
            if not task_id:
                return {"reply": "Provide the task id to run.", "speak": False}
            try:
                outcome = jarvis.run_scheduled_task(task_id)
            except RuntimeError as error:
                return {"reply": f"I couldn't run it: {error}", "speak": False}
            if outcome.success:
                return {
                    "reply": f"Ran it — {outcome.summary} (recorded on the task).",
                    "speak": False,
                    "ok": True,
                }
            return {
                "reply": f"It ran but failed honestly: {outcome.summary} (recorded on the task).",
                "speak": False,
                "ok": False,
            }
    except ValueError as error:  # noqa: BLE001 - a bad cron/schedule is guidance, not a crash
        return {"reply": f"No pude hacerlo: {error}", "speak": False}
    except Exception as error:  # noqa: BLE001 - the store boundary
        return {"reply": f"I couldn't do that ({type(error).__name__}).", "speak": False}
    return {"reply": "Unknown tasks action.", "speak": False}


def _format_note(note: object) -> str:
    """A readable summary of one stored note."""
    from jarvis.domain.value_objects.note import Note

    if not isinstance(note, Note):
        return str(note)
    lines = [f"Title: {note.title}"]
    if note.tags:
        lines.append(f"Tags: {', '.join(note.tags)}")
    if note.body:
        body = note.body if len(note.body) <= 500 else note.body[:500].rstrip() + "…"
        lines.append(body)
    lines.append(f"ID: {note.id}")
    return "\n".join(lines)


def _note_tags(raw: object) -> tuple[str, ...]:
    """Tags from a comma string or a list, cleaned and de-duplicated."""
    if isinstance(raw, list):
        items = [str(v).strip() for v in cast("list[object]", raw)]
    else:
        items = [item.strip() for item in str(raw or "").split(",")]
    seen: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.append(item)
    return tuple(seen)


def _notes(jarvis: Jarvis, payload: Reply) -> Reply:
    """Keep plain-text notes through the notes capability (Odysseus #8).

    Actions: ``list``, ``get``, ``create``, ``update``, ``delete``, ``search``.
    Notes are unvetted material the companion asked to keep -- reading one is
    retrieval, never a verdict; writing one is reversible and gated in the
    caller, never a decision Jarvis makes on its own.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use notes with action 'list', 'get', 'create', "
            "'update', 'delete', or 'search'.",
            "speak": False,
        }
    if jarvis.notes_store is None:
        return {
            "reply": "No notes capability is wired up right now.",
            "speak": False,
        }
    if not jarvis.can_do("manage notes"):
        return _capability_not_ready(jarvis, "manage notes")
    try:
        if action == "list":
            limit_raw = payload.get("limit", 20)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 20
            found = jarvis.list_notes(limit=limit)
            if not found:
                return {"reply": "No notes yet — jot one down.", "speak": False}
            lines = [_format_note(n) for n in found]
            return {
                "reply": "Notes:\n\n" + "\n\n".join(lines),
                "speak": False,
                "count": len(found),
                "notes": [
                    {"id": n.id, "title": n.title, "tags": list(n.tags)}
                    for n in found
                ],
            }
        if action == "get":
            note_id = str(payload.get("id", "")).strip()
            if not note_id:
                return {"reply": "Provide a note id.", "speak": False}
            note = jarvis.get_note(note_id)
            return {
                "reply": _format_note(note),
                "speak": False,
                "note": {
                    "id": note.id,
                    "title": note.title,
                    "body": note.body,
                    "tags": list(note.tags),
                },
            }
        if action == "create":
            title = str(payload.get("title", "")).strip()
            body = str(payload.get("body", "")).strip()
            if not title and not body:
                return {"reply": "Provide a title and/or a body.", "speak": False}
            note = jarvis.create_note(
                title=title, body=body, tags=_note_tags(payload.get("tags"))
            )
            return {
                "reply": f"Kept note: {note.title} (ID: {note.id})",
                "speak": False,
            }
        if action == "update":
            note_id = str(payload.get("id", "")).strip()
            if not note_id:
                return {"reply": "Provide the note id to update.", "speak": False}
            current = jarvis.get_note(note_id)
            title = str(payload.get("title", "")).strip() or current.title
            body = str(payload.get("body", "")).strip() or current.body
            tags = (
                _note_tags(payload.get("tags"))
                if "tags" in payload
                else current.tags
            )
            note = jarvis.update_note(note_id, title=title, body=body, tags=tags)
            return {
                "reply": f"Updated note: {note.title} (ID: {note.id})",
                "speak": False,
            }
        if action == "delete":
            note_id = str(payload.get("id", "")).strip()
            if not note_id:
                return {"reply": "Provide the note id to delete.", "speak": False}
            jarvis.delete_note(note_id)
            return {"reply": f"Deleted note {note_id}.", "speak": False}
        if action == "search":
            query = str(payload.get("query", "")).strip()
            if not query:
                return {"reply": "Provide a query to search notes.", "speak": False}
            limit_raw = payload.get("limit", 10)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 10
            found = jarvis.search_notes(query, limit=limit)
            if not found:
                return {
                    "reply": f"Nothing in notes matches {query!r}.",
                    "speak": False,
                    "count": 0,
                }
            lines = [_format_note(n) for n in found]
            return {
                "reply": f"Notes matching {query!r}:\n\n" + "\n\n".join(lines),
                "speak": False,
                "count": len(found),
                "notes": [
                    {"id": n.id, "title": n.title, "tags": list(n.tags)}
                    for n in found
                ],
            }
    except Exception as error:  # noqa: BLE001 - the store boundary
        return {"reply": f"I couldn't do that ({type(error).__name__}).", "speak": False}
    return {"reply": "Unknown notes action.", "speak": False}


def _format_email(message: object) -> str:
    """A readable summary of one email, body truncated for the surface."""
    from jarvis.domain.value_objects.email_message import EmailMessage

    if not isinstance(message, EmailMessage):
        return str(message)
    lines = [
        f"From: {message.sender or '(unknown)'}",
        f"Subject: {message.subject or '(no subject)'}",
    ]
    if message.recipients:
        lines.append(f"To: {', '.join(message.recipients)}")
    body = message.body if len(message.body) <= 800 else message.body[:800].rstrip() + "…"
    lines.append(body)
    lines.append(f"ID: {message.message_id or '(none)'}")
    return "\n".join(lines)


def _mail(jarvis: Jarvis, payload: Reply) -> Reply:
    """Read and send email through the mailbox capability (Odysseus email).

    Actions: ``list`` (``folder``, ``limit``), ``read`` (``message_id``,
    ``folder``), ``send`` (``to``, ``subject``, ``body``). Reading is
    retrieval -- candidate context, never adopted fact. Sending is an external
    material act: it needs the earned capability *and* an explicit
    ``approved: true`` per send, so nothing ever leaves the outbox by
    accident; without it the reply asks for approval and sends nothing.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use mail with action 'list', 'read', or 'send'.",
            "speak": False,
        }
    if jarvis.mail_source is None:
        return {
            "reply": "No mail capability is wired up right now.",
            "speak": False,
        }
    if not jarvis.can_do("send and read email"):
        return _capability_not_ready(jarvis, "send and read email")
    try:
        if action == "list":
            folder = str(payload.get("folder", "inbox")).strip() or "inbox"
            limit_raw = payload.get("limit", 10)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 10
            messages = jarvis.list_emails(folder=folder, limit=limit)
            if not messages:
                return {"reply": f"No messages in {folder}.", "speak": False}
            lines = [_format_email(m) for m in messages]
            return {
                "reply": f"Messages in {folder}:\n\n" + "\n\n".join(lines),
                "speak": False,
                "count": len(messages),
            }
        if action == "read":
            message_id = str(payload.get("message_id", "")).strip()
            if not message_id:
                return {"reply": "Provide a message id.", "speak": False}
            folder = str(payload.get("folder", "inbox")).strip() or "inbox"
            return {
                "reply": _format_email(jarvis.read_email(message_id, folder=folder)),
                "speak": False,
            }
        if action == "send":
            raw_to = payload.get("to", "")
            recipients = _note_tags(raw_to)
            if not recipients:
                return {"reply": "Provide at least one recipient.", "speak": False}
            subject = str(payload.get("subject", "")).strip()
            body = str(payload.get("body", "")).strip()
            if not subject and not body:
                return {"reply": "Provide a subject and/or a body.", "speak": False}
            approved = payload.get("approved", False)
            if isinstance(approved, str):
                approved = approved.strip().lower() in ("true", "1", "yes")
            if not approved:
                return {
                    "reply": (
                        "Sending email is an external act — confirm it explicitly "
                        "by sending again with approved: true. Nothing was sent."
                    ),
                    "speak": False,
                }
            sent = jarvis.send_email(to=recipients, subject=subject, body=body)
            return {
                "reply": f"Sent to {', '.join(sent.recipients)}: {sent.subject or '(no subject)'}",
                "speak": False,
            }
    except Exception as error:  # noqa: BLE001 - the mailbox boundary
        return {"reply": f"I couldn't do that ({type(error).__name__}).", "speak": False}
    return {"reply": "Unknown mail action.", "speak": False}


def _documents(jarvis: Jarvis, payload: Reply) -> Reply:
    """Manage the files the companion shares (work-with-files capability).

    Actions: ``list``, ``read``, ``info``, ``save``, ``edit``, ``search``, ``remove``.
    ``list`` names each document with its owner (companion-shared vs generated).
    ``info`` answers "whose is that, and when did I get it?" from the recorded
    provenance (Vision §26). ``save`` takes ``name`` and ``content`` with
    ``encoding`` ``"text"`` (default) or ``"b64"`` (binary kept intact), an
    optional ``path`` folder to file the document under (``"docs/api.md"``,
    relative and sandbox-safe), and an optional ``owner`` ``"companion"``
    (default) or ``"jarvis"``. ``edit`` rewrites an existing document from a
    free-form ``instruction``: the live model *proposes* the revised text (Vision
    §38) and Jarvis applies it, keeping the recorded attribution and reporting
    what actually changed; offline there is no grounded proposal to apply. ``read``
    returns the content as text (truncated for the surface) or base64. ``search``
    takes ``query`` and returns the documents whose name or text match, each with a
    snippet and match strength -- candidates, never a verdict.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use documents with action 'list', 'read', 'info', 'save', "
            "'edit', 'search', or 'remove'.",
            "speak": False,
        }
    if jarvis.documents_store is None:
        return {
            "reply": "No documents capability is wired up right now.",
            "speak": False,
        }
    if not jarvis.can_do("work with files"):
        return _capability_not_ready(jarvis, "work with files")
    try:
        if action == "list":
            names = jarvis.list_documents()
            if not names:
                return {"reply": "No documents yet — share a file.", "speak": False}
            lines = "".join(f"  - {_ownership_tag(jarvis, name)}{name}\n" for name in names)
            return {
                "reply": f"Documents I'm keeping ({len(names)}):\n\n{lines}",
                "speak": False,
                "count": len(names),
            }
        if action == "read":
            name = _document_name(payload.get("name"))
            if not name:
                return {"reply": "Provide a document name to read.", "speak": False}
            raw = jarvis.read_document(name)
            return _document_read_reply(name, raw)
        if action == "info":
            name = _document_name(payload.get("name"))
            if not name:
                return {"reply": "Provide a document name to inspect.", "speak": False}
            return _document_info_reply(name, jarvis)
        if action == "save":
            name = _document_name(payload.get("name"))
            if not name:
                return {"reply": "Provide a document name.", "speak": False}
            try:
                folder = _document_folder(payload.get("path"))
            except ValueError:
                return {
                    "reply": "That document path escapes my sandbox.",
                    "speak": False,
                }
            if folder:
                name = f"{folder}/{name}"
            content = payload.get("content")
            if content is None:
                return {"reply": "Provide the document content.", "speak": False}
            encoding = str(payload.get("encoding", "text")).strip().lower()
            if encoding == "b64":
                try:
                    raw = base64.b64decode(str(content), validate=True)
                except (ValueError, TypeError):
                    return {"reply": "content was not valid base64.", "speak": False}
            else:
                raw = str(content).encode("utf-8")
            owner = _document_owner(payload.get("owner"))
            if owner is None:
                return {"reply": "Owner must be 'companion' or 'jarvis'.", "speak": False}
            jarvis.write_document(name, raw, owner=owner)
            nbytes = len(raw)
            note = " " if _looks_text(raw) else " (binary)"
            return {
                "reply": f"Kept {name} ({nbytes} bytes{note}).",
                "speak": False,
                "name": name,
            }
        if action == "edit":
            name = _document_name(payload.get("name"))
            if not name:
                return {"reply": "Provide a document name to edit.", "speak": False}
            instruction = str(payload.get("instruction", "")).strip()
            if not instruction:
                return {
                    "reply": "Tell me what to change (instruction).",
                    "speak": False,
                }
            if jarvis.document_editor is None:
                return {
                    "reply": "Editing needs a live model to propose the rewrite — "
                    "share the corrected content via save instead.",
                    "speak": False,
                }
            try:
                edit = jarvis.edit_document(name, instruction)
            except ValueError:
                return {
                    "reply": "That document isn't text, so I can't rewrite it.",
                    "speak": False,
                }
            if edit is None:
                return {
                    "reply": "I couldn't come up with a concrete rewrite for that — "
                    "share the corrected content via save instead.",
                    "speak": False,
                }
            return {
                "reply": f"Rewrote {name}: {edit.note} "
                f"({len(edit.content.encode('utf-8'))} bytes).",
                "speak": False,
                "name": name,
                "note": edit.note,
            }
        if action == "search":
            query = str(payload.get("query", "")).strip()
            if not query:
                return {"reply": "Provide a query to search my documents.", "speak": False}
            limit_raw = payload.get("limit", 5)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 5
            hits = jarvis.search_documents(query, limit=limit)
            if not hits:
                return {
                    "reply": "Nothing in my documents matches that.",
                    "speak": False,
                    "count": 0,
                }
            lines = "".join(
                f"  - {hit.name} ({hit.relevance:.2f}): {hit.snippet}\n"
                for hit in hits
            )
            return {
                "reply": f"Documents matching \"{query}\" ({len(hits)}):\n\n{lines}",
                "speak": False,
                "count": len(hits),
                "hits": [
                    {"name": hit.name, "snippet": hit.snippet}
                    for hit in hits
                ],
            }
        if action == "remove":
            name = _document_name(payload.get("name"))
            if not name:
                return {"reply": "Provide a document name to remove.", "speak": False}
            jarvis.remove_document(name)
            return {"reply": f"Removed {name}.", "speak": False}
    except Exception as error:  # noqa: BLE001 - the store boundary
        return {"reply": f"I couldn't do that ({type(error).__name__}).", "speak": False}
    return {"reply": "Unknown documents action.", "speak": False}


def _document_name(raw: object) -> str:
    """A safe document name from arbitrary input (its basename only).

    Browser upload paths (``C:/Users/me/file.txt``, ``../file.txt``) collapse to
    the bare file name; a folder is filed separately through ``path`` so the
    sandbox boundary is never near a traversal.
    """
    text = str(raw or "").strip()
    if not text:
        return ""
    return Path(text.replace("\\", "/")).name


def _document_folder(raw: object) -> str:
    """A safe, relative folder to file documents under, or ``""`` when omitted.

    Raises :class:`ValueError` when the folder would escape the sandbox
    (absolute, or containing ``..``/``.`` or empty segments), mirroring the
    store's own name gate.
    """
    text = str(raw or "").strip().replace("\\", "/")
    if not text:
        return ""
    parts = text.split("/")
    if (
        text.startswith("/")
        or any(part in ("", ".", "..") for part in parts)
        or any(":" in part for part in parts)
    ):
        raise ValueError("document path escapes the sandbox")
    return text


def _looks_text(content: bytes) -> bool:
    """Best-effort guess of whether ``content`` is text (utf-8-decodable)."""
    try:
        content.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _ownership_tag(jarvis: Jarvis, name: str) -> str:
    """A short attribution prefix for a document in a listing (Vision §26).

    Companion-shared files are the norm; only a Jarvis-materialised artifact is
    tagged explicitly, so the common case stays quiet.
    """
    meta = jarvis.document_meta(name)
    if meta is not None and meta.owner is DocumentOwner.JARVIS:
        return "[jarvis] "
    return ""


def _document_owner(raw: object) -> DocumentOwner | None:
    """The attribution for a save, or None when the value is not a known owner."""
    if raw is None:
        return DocumentOwner.COMPANION
    text = str(raw).strip().lower()
    if text == "jarvis":
        return DocumentOwner.JARVIS
    if text == "companion":
        return DocumentOwner.COMPANION
    return None


def _document_info_reply(name: str, jarvis: Jarvis) -> Reply:
    """Render the recorded provenance of one document (Vision §26).

    ``requested_at``/``updated_at``/``owner`` are the store's honest record of
    attribution and timing; ``None`` means the file predates provenance tracking.
    """
    meta = jarvis.document_meta(name)
    if meta is None:
        return {
            "reply": f"I keep {name} but no provenance was recorded for it — it "
            "predates my ownership tracking.",
            "speak": False,
            "name": name,
        }
    owner = (
        "companion — I'm keeping a file you shared"
        if meta.owner is DocumentOwner.COMPANION
        else "jarvis — a document I generated"
    )
    return {
        "reply": (
            f"{name}\n"
            f"  Owner:   {owner}\n"
            f"  Size:    {meta.size_bytes} bytes\n"
            f"  Stored:  {meta.stored_at:%Y-%m-%d %H:%M} UTC\n"
            f"  Updated: {meta.updated_at:%Y-%m-%d %H:%M} UTC"
        ),
        "speak": False,
        "name": name,
        "meta": {
            "name": meta.name,
            "owner": meta.owner.value,
            "size_bytes": meta.size_bytes,
            "stored_at": meta.stored_at.isoformat(),
            "updated_at": meta.updated_at.isoformat(),
        },
    }


def _document_read_reply(name: str, raw: bytes) -> Reply:
    """Render a document read: text when readably textual, base64 when binary.

    Long text is truncated for the surface (the reasoner reads in slices); the full
    byte length is always reported so the companion knows what was skipped.
    """
    if _looks_text(raw):
        text = raw.decode("utf-8", errors="replace")
        shown = text[:3000]
        if len(text) > len(shown):
            shown = f"{shown}\n\n... ({len(text)} chars total; say 'documents read " \
                    f"{name}' at the seam for the full stream)"
        return {"reply": f"{name}:\n\n{shown}", "speak": False, "name": name}
    return {
        "reply": f"{name} is binary ({len(raw)} bytes) — I keep it intact but can't "
        "read its contents yet. Say 'read <name>' at the seam for raw bytes.",
        "speak": False,
        "name": name,
        "encoding": "b64",
        "content": base64.b64encode(raw).decode("ascii"),
    }
