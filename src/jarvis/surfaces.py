"""CRUD surfaces for notes, documents, calendar events, and scheduled tasks.

Each surface wraps a single store (or pair of stores for documents + editor)
and exposes the method body that previously lived in the monolithic Jarvis
class.  The Jarvis class retains thin delegator methods that forward here.
"""

from __future__ import annotations

import difflib
from datetime import datetime
from typing import TYPE_CHECKING

from jarvis.domain.enums.document_owner import DocumentOwner
from jarvis.domain.value_objects.calendar_event import CalendarEvent
from jarvis.domain.value_objects.document_edit import DocumentEdit
from jarvis.domain.value_objects.document_hit import DocumentHit
from jarvis.domain.value_objects.document_meta import DocumentMeta
from jarvis.domain.value_objects.note import Note
from jarvis.domain.value_objects.passage_hit import PassageHit
from jarvis.domain.value_objects.scheduled_task import ScheduledTask
from jarvis.domain.value_objects.task_result import TaskResult

if TYPE_CHECKING:
    from jarvis.domain.retrieval.calendar_store import CalendarStore
    from jarvis.domain.retrieval.calendar_sync import CalendarSyncResult
    from jarvis.domain.retrieval.document_editor import DocumentEditor
    from jarvis.domain.retrieval.document_store import DocumentStore
    from jarvis.domain.retrieval.notes_store import NotesStore
    from jarvis.domain.retrieval.task_agent_source import TaskAgent
    from jarvis.domain.retrieval.task_scheduler import TaskScheduler
    from jarvis.jarvis import Jarvis


def _describe_document_change(before: str, after: str) -> str:
    """Frame what actually changed between two texts, derived not guessed.

    The note a surface shows for a rewrite comes from the real diff (Vision §26,
    §38), never from what the editing model claims it did.
    """
    added = removed = 0
    for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm=""):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    if added == 0 and removed == 0:
        return "no change"
    changed = f"{removed} line(s) removed, {added} added"
    return changed


class NotesSurface:
    """CRUD operations for the notes capability."""

    def __init__(self, jarvis: Jarvis) -> None:
        self._jarvis = jarvis

    def _store(self) -> NotesStore:
        store = self._jarvis.notes_store
        if store is None:
            raise RuntimeError("no notes capability configured; set_notes_store")
        return store

    def list_notes(self, *, limit: int = 100) -> tuple[Note, ...]:
        return self._store().list_notes(limit=limit)

    def get_note(self, note_id: str) -> Note:
        return self._store().get_note(note_id)

    def create_note(
        self, *, title: str, body: str = "", tags: tuple[str, ...] = ()
    ) -> Note:
        return self._store().create_note(title=title, body=body, tags=tags)

    def update_note(
        self,
        note_id: str,
        *,
        title: str,
        body: str,
        tags: tuple[str, ...],
    ) -> Note:
        return self._store().update_note(
            note_id, title=title, body=body, tags=tags
        )

    def delete_note(self, note_id: str) -> None:
        self._store().delete_note(note_id)

    def search_notes(self, query: str, *, limit: int = 10) -> tuple[Note, ...]:
        return self._store().search_notes(query, limit=limit)


class DocumentsSurface:
    """CRUD operations for the documents capability (project files)."""

    def __init__(self, jarvis: Jarvis) -> None:
        self._jarvis = jarvis

    def _store(self) -> DocumentStore:
        store = self._jarvis.documents_store
        if store is None:
            raise RuntimeError(
                "no documents capability configured; set_documents_store"
            )
        return store

    def _editor(self) -> DocumentEditor:
        editor = self._jarvis.document_editor
        if editor is None:
            raise RuntimeError("no document editor configured; set_document_editor")
        return editor

    def list_documents(self) -> tuple[str, ...]:
        return self._store().list_documents()

    def read_document(self, name: str) -> bytes:
        return self._store().read_document(name)

    def write_document(
        self,
        name: str,
        content: bytes | str,
        *,
        owner: DocumentOwner = DocumentOwner.COMPANION,
    ) -> None:
        store = self._store()
        payload = content if isinstance(content, bytes) else content.encode("utf-8")
        store.write_document(name, payload, owner=owner)

    def document_meta(self, name: str) -> DocumentMeta | None:
        return self._store().document_meta(name)

    def remove_document(self, name: str) -> None:
        self._store().remove_document(name)

    def search_documents(
        self, query: str, *, limit: int = 5
    ) -> tuple[DocumentHit, ...]:
        return self._store().search_documents(query, limit=limit)

    def search_passages(
        self, query: str, *, limit: int = 5
    ) -> tuple[PassageHit, ...]:
        return self._store().search_passages(query, limit=limit)

    def edit_document(self, name: str, instruction: str) -> DocumentEdit | None:
        store = self._store()
        editor = self._editor()
        raw = store.read_document(name)
        try:
            source = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError(
                f"{name} is not text; documents stay intact as bytes"
            ) from None
        proposal = editor.propose(source, instruction)
        if not proposal or not proposal.strip():
            return None
        proposal = proposal.strip()
        if proposal == source.strip():
            return DocumentEdit(content=source, note="unchanged -- already as you asked")
        meta = store.document_meta(name)
        owner = meta.owner if meta is not None else DocumentOwner.COMPANION
        store.write_document(name, proposal.encode("utf-8"), owner=owner)
        return DocumentEdit(
            content=proposal, note=_describe_document_change(source, proposal)
        )


class CalendarSurface:
    """CRUD operations for the calendar capability."""

    def __init__(self, jarvis: Jarvis) -> None:
        self._jarvis = jarvis

    def _store(self) -> CalendarStore:
        store = self._jarvis.calendar_store
        if store is None:
            raise RuntimeError("no calendar capability configured; set_calendar_store")
        return store

    def list_calendar_events(
        self, *, limit: int = 100
    ) -> tuple[CalendarEvent, ...]:
        return self._store().list_events(limit=limit)

    def get_calendar_event(self, event_id: str) -> CalendarEvent:
        return self._store().get_event(event_id)

    def create_calendar_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        description: str = "",
        location: str = "",
        all_day: bool = False,
    ) -> CalendarEvent:
        return self._store().create_event(
            title=title,
            start=start,
            end=end,
            description=description,
            location=location,
            all_day=all_day,
        )

    def update_calendar_event(
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
        return self._store().update_event(
            event_id,
            title=title,
            start=start,
            end=end,
            description=description,
            location=location,
            all_day=all_day,
        )

    def delete_calendar_event(self, event_id: str) -> None:
        self._store().delete_event(event_id)

    def calendar_events_in_range(
        self, start: datetime, end: datetime, *, limit: int = 100
    ) -> tuple[CalendarEvent, ...]:
        return self._store().events_in_range(start, end, limit=limit)

    def sync_calendar(self, *, limit: int | None = None) -> CalendarSyncResult:
        """Pull the CalDAV/ICS feed into the calendar store (roadmap F6a).

        One-way on request: never pushes back, never deletes local events. The
        returned ``CalendarSyncResult`` counts what the pull actually changed,
        so the surface narrates it truthfully.
        """
        syncer = self._jarvis.calendar_sync
        if syncer is None:
            raise RuntimeError("no calendar sync configured; set_calendar_sync")
        return syncer.sync_into(self._store(), limit=limit)


class TaskSchedulerSurface:
    """CRUD operations for the task-scheduler capability."""

    def __init__(self, jarvis: Jarvis) -> None:
        self._jarvis = jarvis

    def _store(self) -> TaskScheduler:
        store = self._jarvis.task_scheduler
        if store is None:
            raise RuntimeError(
                "no task-scheduler capability configured; set_task_scheduler"
            )
        return store

    def _agent(self) -> TaskAgent:
        agent = self._jarvis.instruction_agent
        if agent is None:
            raise RuntimeError(
                "no instruction executor configured; set_instruction_agent"
            )
        return agent

    def list_scheduled_tasks(
        self, *, limit: int = 100
    ) -> tuple[ScheduledTask, ...]:
        return self._store().list_tasks(limit=limit)

    def get_scheduled_task(self, task_id: str) -> ScheduledTask:
        return self._store().get_task(task_id)

    def create_scheduled_task(
        self,
        *,
        name: str,
        command: str,
        cron: str = "",
        description: str = "",
        enabled: bool = True,
    ) -> ScheduledTask:
        return self._store().create_task(
            name=name,
            command=command,
            cron=cron,
            description=description,
            enabled=enabled,
        )

    def update_scheduled_task(
        self,
        task_id: str,
        *,
        name: str,
        command: str,
        cron: str,
        description: str,
        enabled: bool,
    ) -> ScheduledTask:
        return self._store().update_task(
            task_id,
            name=name,
            command=command,
            cron=cron,
            description=description,
            enabled=enabled,
        )

    def delete_scheduled_task(self, task_id: str) -> None:
        self._store().delete_task(task_id)

    def enable_scheduled_task(self, task_id: str) -> ScheduledTask:
        return self._store().enable_task(task_id)

    def disable_scheduled_task(self, task_id: str) -> ScheduledTask:
        return self._store().disable_task(task_id)

    def due_scheduled_tasks(self) -> tuple[ScheduledTask, ...]:
        return self._store().due_tasks()

    def run_scheduled_task(self, task_id: str) -> TaskResult:
        store = self._store()
        task = store.get_task(task_id)
        if not task.enabled:
            raise RuntimeError(f"task {task_id!r} is disabled; enable it first")
        agent = self._agent()
        try:
            outcome = agent.run_task(task.command)
        except Exception as error:  # noqa: BLE001 - record the honest failure
            store.record_run(task_id, ok=False, output=str(error))
            raise
        store.record_run(task_id, ok=outcome.success, output=outcome.summary)
        return outcome
