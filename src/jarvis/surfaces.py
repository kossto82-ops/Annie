"""CRUD surfaces for notes, documents, calendar events, and scheduled tasks.

Each surface wraps a single store (or pair of stores for documents + editor)
and exposes the method body that previously lived in the monolithic Jarvis
class.  The Jarvis class retains thin delegator methods that forward here.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from jarvis.domain.enums.document_owner import DocumentOwner
from jarvis.domain.value_objects.calendar_event import CalendarEvent
from jarvis.domain.value_objects.document_edit import DocumentEdit
from jarvis.domain.value_objects.document_hit import DocumentHit
from jarvis.domain.value_objects.document_meta import DocumentMeta
from jarvis.domain.value_objects.note import Note
from jarvis.domain.value_objects.scheduled_task import ScheduledTask
from jarvis.domain.value_objects.task_result import TaskResult

if TYPE_CHECKING:
    from jarvis.jarvis import Jarvis


class NotesSurface:
    """CRUD operations for the notes capability."""

    def __init__(self, jarvis: Jarvis) -> None:
        self._jarvis = jarvis

    def list_notes(self, *, limit: int = 100) -> tuple[Note, ...]:
        if self._jarvis._notes_store is None:
            raise RuntimeError("no notes capability configured; set_notes_store")
        return self._jarvis._notes_store.list_notes(limit=limit)

    def get_note(self, note_id: str) -> Note:
        if self._jarvis._notes_store is None:
            raise RuntimeError("no notes capability configured; set_notes_store")
        return self._jarvis._notes_store.get_note(note_id)

    def create_note(
        self, *, title: str, body: str = "", tags: tuple[str, ...] = ()
    ) -> Note:
        if self._jarvis._notes_store is None:
            raise RuntimeError("no notes capability configured; set_notes_store")
        return self._jarvis._notes_store.create_note(title=title, body=body, tags=tags)

    def update_note(
        self,
        note_id: str,
        *,
        title: str,
        body: str,
        tags: tuple[str, ...],
    ) -> Note:
        if self._jarvis._notes_store is None:
            raise RuntimeError("no notes capability configured; set_notes_store")
        return self._jarvis._notes_store.update_note(
            note_id, title=title, body=body, tags=tags
        )

    def delete_note(self, note_id: str) -> None:
        if self._jarvis._notes_store is None:
            raise RuntimeError("no notes capability configured; set_notes_store")
        self._jarvis._notes_store.delete_note(note_id)

    def search_notes(self, query: str, *, limit: int = 10) -> tuple[Note, ...]:
        if self._jarvis._notes_store is None:
            raise RuntimeError("no notes capability configured; set_notes_store")
        return self._jarvis._notes_store.search_notes(query, limit=limit)


class DocumentsSurface:
    """CRUD operations for the documents capability (project files)."""

    def __init__(self, jarvis: Jarvis) -> None:
        self._jarvis = jarvis

    def list_documents(self) -> tuple[str, ...]:
        if self._jarvis._documents_store is None:
            raise RuntimeError(
                "no documents capability configured; set_documents_store"
            )
        return self._jarvis._documents_store.list_documents()

    def read_document(self, name: str) -> bytes:
        if self._jarvis._documents_store is None:
            raise RuntimeError(
                "no documents capability configured; set_documents_store"
            )
        return self._jarvis._documents_store.read_document(name)

    def write_document(
        self,
        name: str,
        content: bytes | str,
        *,
        owner: DocumentOwner = DocumentOwner.COMPANION,
    ) -> None:
        if self._jarvis._documents_store is None:
            raise RuntimeError(
                "no documents capability configured; set_documents_store"
            )
        payload = content if isinstance(content, bytes) else content.encode("utf-8")
        self._jarvis._documents_store.write_document(name, payload, owner=owner)

    def document_meta(self, name: str) -> DocumentMeta | None:
        if self._jarvis._documents_store is None:
            raise RuntimeError(
                "no documents capability configured; set_documents_store"
            )
        return self._jarvis._documents_store.document_meta(name)

    def remove_document(self, name: str) -> None:
        if self._jarvis._documents_store is None:
            raise RuntimeError(
                "no documents capability configured; set_documents_store"
            )
        self._jarvis._documents_store.remove_document(name)

    def search_documents(
        self, query: str, *, limit: int = 5
    ) -> tuple[DocumentHit, ...]:
        if self._jarvis._documents_store is None:
            raise RuntimeError(
                "no documents capability configured; set_documents_store"
            )
        return self._jarvis._documents_store.search_documents(query, limit=limit)

    def edit_document(self, name: str, instruction: str) -> DocumentEdit | None:
        from jarvis.jarvis import _describe_document_change

        if self._jarvis._documents_store is None:
            raise RuntimeError(
                "no documents capability configured; set_documents_store"
            )
        if self._jarvis._document_editor is None:
            raise RuntimeError("no document editor configured; set_document_editor")
        raw = self._jarvis._documents_store.read_document(name)
        try:
            source = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError(
                f"{name} is not text; documents stay intact as bytes"
            ) from None
        proposal = self._jarvis._document_editor.propose(source, instruction)
        if not proposal or not proposal.strip():
            return None
        proposal = proposal.strip()
        if proposal == source.strip():
            return DocumentEdit(content=source, note="unchanged -- already as you asked")
        meta = self._jarvis._documents_store.document_meta(name)
        owner = meta.owner if meta is not None else DocumentOwner.COMPANION
        self._jarvis._documents_store.write_document(
            name, proposal.encode("utf-8"), owner=owner
        )
        return DocumentEdit(
            content=proposal, note=_describe_document_change(source, proposal)
        )


class CalendarSurface:
    """CRUD operations for the calendar capability."""

    def __init__(self, jarvis: Jarvis) -> None:
        self._jarvis = jarvis

    def list_calendar_events(
        self, *, limit: int = 100
    ) -> tuple[CalendarEvent, ...]:
        if self._jarvis._calendar_store is None:
            raise RuntimeError("no calendar capability configured; set_calendar_store")
        return self._jarvis._calendar_store.list_events(limit=limit)

    def get_calendar_event(self, event_id: str) -> CalendarEvent:
        if self._jarvis._calendar_store is None:
            raise RuntimeError("no calendar capability configured; set_calendar_store")
        return self._jarvis._calendar_store.get_event(event_id)

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
        if self._jarvis._calendar_store is None:
            raise RuntimeError("no calendar capability configured; set_calendar_store")
        return self._jarvis._calendar_store.create_event(
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
        if self._jarvis._calendar_store is None:
            raise RuntimeError("no calendar capability configured; set_calendar_store")
        return self._jarvis._calendar_store.update_event(
            event_id,
            title=title,
            start=start,
            end=end,
            description=description,
            location=location,
            all_day=all_day,
        )

    def delete_calendar_event(self, event_id: str) -> None:
        if self._jarvis._calendar_store is None:
            raise RuntimeError("no calendar capability configured; set_calendar_store")
        self._jarvis._calendar_store.delete_event(event_id)

    def calendar_events_in_range(
        self, start: datetime, end: datetime, *, limit: int = 100
    ) -> tuple[CalendarEvent, ...]:
        if self._jarvis._calendar_store is None:
            raise RuntimeError("no calendar capability configured; set_calendar_store")
        return self._jarvis._calendar_store.events_in_range(start, end, limit=limit)


class TaskSchedulerSurface:
    """CRUD operations for the task-scheduler capability."""

    def __init__(self, jarvis: Jarvis) -> None:
        self._jarvis = jarvis

    def list_scheduled_tasks(
        self, *, limit: int = 100
    ) -> tuple[ScheduledTask, ...]:
        if self._jarvis._task_scheduler is None:
            raise RuntimeError(
                "no task-scheduler capability configured; set_task_scheduler"
            )
        return self._jarvis._task_scheduler.list_tasks(limit=limit)

    def get_scheduled_task(self, task_id: str) -> ScheduledTask:
        if self._jarvis._task_scheduler is None:
            raise RuntimeError(
                "no task-scheduler capability configured; set_task_scheduler"
            )
        return self._jarvis._task_scheduler.get_task(task_id)

    def create_scheduled_task(
        self,
        *,
        name: str,
        command: str,
        cron: str = "",
        description: str = "",
        enabled: bool = True,
    ) -> ScheduledTask:
        if self._jarvis._task_scheduler is None:
            raise RuntimeError(
                "no task-scheduler capability configured; set_task_scheduler"
            )
        return self._jarvis._task_scheduler.create_task(
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
        if self._jarvis._task_scheduler is None:
            raise RuntimeError(
                "no task-scheduler capability configured; set_task_scheduler"
            )
        return self._jarvis._task_scheduler.update_task(
            task_id,
            name=name,
            command=command,
            cron=cron,
            description=description,
            enabled=enabled,
        )

    def delete_scheduled_task(self, task_id: str) -> None:
        if self._jarvis._task_scheduler is None:
            raise RuntimeError(
                "no task-scheduler capability configured; set_task_scheduler"
            )
        self._jarvis._task_scheduler.delete_task(task_id)

    def enable_scheduled_task(self, task_id: str) -> ScheduledTask:
        if self._jarvis._task_scheduler is None:
            raise RuntimeError(
                "no task-scheduler capability configured; set_task_scheduler"
            )
        return self._jarvis._task_scheduler.enable_task(task_id)

    def disable_scheduled_task(self, task_id: str) -> ScheduledTask:
        if self._jarvis._task_scheduler is None:
            raise RuntimeError(
                "no task-scheduler capability configured; set_task_scheduler"
            )
        return self._jarvis._task_scheduler.disable_task(task_id)

    def due_scheduled_tasks(self) -> tuple[ScheduledTask, ...]:
        if self._jarvis._task_scheduler is None:
            raise RuntimeError(
                "no task-scheduler capability configured; set_task_scheduler"
            )
        return self._jarvis._task_scheduler.due_tasks()

    def run_scheduled_task(self, task_id: str) -> TaskResult:
        if self._jarvis._task_scheduler is None:
            raise RuntimeError(
                "no task-scheduler capability configured; set_task_scheduler"
            )
        task = self._jarvis._task_scheduler.get_task(task_id)
        if not task.enabled:
            raise RuntimeError(f"task {task_id!r} is disabled; enable it first")
        if self._jarvis._instruction_agent is None:
            raise RuntimeError(
                "no instruction executor configured; set_instruction_agent"
            )
        try:
            outcome = self._jarvis._instruction_agent.run_task(task.command)
        except Exception as error:  # noqa: BLE001 - record the honest failure
            self._jarvis._task_scheduler.record_run(task_id, ok=False, output=str(error))
            raise
        self._jarvis._task_scheduler.record_run(
            task_id, ok=outcome.success, output=outcome.summary
        )
        return outcome
