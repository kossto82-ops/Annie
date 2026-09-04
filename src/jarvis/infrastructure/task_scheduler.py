"""LocalTaskScheduler: a file-backed TaskScheduler at the edge (Odysseus #7).

A task scheduler is a bounded, file-backed store of scheduled tasks -- the
simplest local representation of recurring or one-shot actions the user asked
Jarvis to manage. Like ``LocalNotesStore``, the actual disk access is an
injectable ``io`` callable so offline tests run deterministically without
touching the filesystem (D8). The store only keeps and returns task content --
it never reasons about the tasks (D6), and creating, updating, deleting,
enabling and disabling are reversible material actions the surface requests.

The store serialises its tasks to a single ``tasks.json`` document inside
``root``, keyed by task id. ``build_task_scheduler()`` returns ``None``
without the ``JARVIS_TASKS_ROOT`` directory, so a Jarvis built from it stays
offline by default (D7/D8).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from jarvis.domain.value_objects.scheduled_task import ScheduledTask

_IO = Callable[[str, str, str], str]
_Record = dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC)


class LocalTaskScheduler:
    """A bounded, file-backed store of scheduled tasks with an injectable ``io`` driver."""

    _FILENAME = "tasks.json"

    def __init__(
        self,
        root: str | Path,
        io: _IO | None = None,
        *,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        """Bind the store to a sandbox ``root`` with an injectable ``io`` driver.

        ``io(operation, path, content)`` mirrors the filesystem protocol: ``read``
        returns file text, ``write`` writes ``content`` and returns ``""``,
        ``delete`` removes the file and returns ``""``. Defaults to real disk
        access through :func:`pathlib`; injecting a fake keeps tests offline (D8).
        """
        self._root = Path(root).resolve()
        self._io = io or self._default_io
        self._id_factory = id_factory or (lambda: str(uuid4()))

    # -- filesystem driver ----------------------------------------------------

    def _default_io(self, operation: str, path: str, content: str) -> str:
        resolved = (self._root / path).resolve()
        if not resolved.is_relative_to(self._root):
            raise ValueError("path escapes the tasks sandbox")
        if operation == "read":
            return resolved.read_text(encoding="utf-8") if resolved.exists() else ""
        if operation == "delete":
            if resolved.exists():
                resolved.unlink()
            return ""
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return ""

    # -- storage helpers ------------------------------------------------------

    def _file(self) -> str:
        return self._FILENAME

    def _load(self) -> dict[str, _Record]:
        raw = self._io("read", self._file(), "")
        if not raw:
            return {}
        return json.loads(raw)

    def _save(self, data: dict[str, _Record]) -> None:
        self._io("write", self._file(), json.dumps(data))

    def _read_task(self, task_id: str) -> ScheduledTask:
        task = self._load().get(task_id)
        if task is None:
            raise KeyError(f"no scheduled task with id {task_id!r}")
        return self._from_record(task_id, task)

    # -- TaskScheduler --------------------------------------------------------

    def list_tasks(self, *, limit: int = 100) -> tuple[ScheduledTask, ...]:
        data = self._load()
        tasks = sorted(
            (self._from_record(tid, rec) for tid, rec in data.items()),
            key=lambda t: t.created_at,
            reverse=True,
        )
        return tuple(tasks[:limit])

    def get_task(self, task_id: str) -> ScheduledTask:
        return self._read_task(task_id)

    def create_task(
        self,
        *,
        name: str,
        command: str,
        cron: str = "",
        description: str = "",
        enabled: bool = True,
    ) -> ScheduledTask:
        task_id = self._id_factory()
        now = _now()
        task = ScheduledTask(
            id=task_id,
            name=name,
            command=command,
            cron=cron,
            description=description,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        data = self._load()
        data[task_id] = self._to_record(task)
        self._save(data)
        return task

    def update_task(
        self,
        task_id: str,
        *,
        name: str,
        command: str,
        cron: str,
        description: str,
        enabled: bool,
    ) -> ScheduledTask:
        current = self._read_task(task_id)
        constructed = ScheduledTask(
            id=task_id,
            name=name if name else current.name,
            command=command if command else current.command,
            cron=cron if cron else current.cron,
            description=description if description else current.description,
            enabled=enabled,
            next_run=current.next_run,
            created_at=current.created_at,
            updated_at=_now(),
        )
        data = self._load()
        data[task_id] = self._to_record(constructed)
        self._save(data)
        return constructed

    def delete_task(self, task_id: str) -> None:
        data = self._load()
        if task_id not in data:
            raise KeyError(f"no scheduled task with id {task_id!r}")
        del data[task_id]
        self._save(data)

    def enable_task(self, task_id: str) -> ScheduledTask:
        current = self._read_task(task_id)
        enabled = ScheduledTask(
            id=current.id,
            name=current.name,
            command=current.command,
            cron=current.cron,
            description=current.description,
            enabled=True,
            next_run=current.next_run,
            created_at=current.created_at,
            updated_at=_now(),
        )
        data = self._load()
        data[task_id] = self._to_record(enabled)
        self._save(data)
        return enabled

    def disable_task(self, task_id: str) -> ScheduledTask:
        current = self._read_task(task_id)
        disabled = ScheduledTask(
            id=current.id,
            name=current.name,
            command=current.command,
            cron=current.cron,
            description=current.description,
            enabled=False,
            next_run=current.next_run,
            created_at=current.created_at,
            updated_at=_now(),
        )
        data = self._load()
        data[task_id] = self._to_record(disabled)
        self._save(data)
        return disabled

    def due_tasks(self) -> tuple[ScheduledTask, ...]:
        now = _now()
        tasks = self.list_tasks()
        return tuple(
            t for t in tasks if t.enabled and t.next_run is not None and t.next_run <= now
        )

    # -- record mapping -------------------------------------------------------

    @staticmethod
    def _to_record(task: ScheduledTask) -> _Record:
        rec: _Record = {
            "name": task.name,
            "command": task.command,
            "cron": task.cron,
            "description": task.description,
            "enabled": task.enabled,
            "next_run": task.next_run.isoformat() if task.next_run is not None else None,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }
        return rec

    @staticmethod
    def _from_record(task_id: str, rec: _Record) -> ScheduledTask:
        next_run_raw = rec.get("next_run")
        return ScheduledTask(
            id=task_id,
            name=rec.get("name", ""),
            command=rec.get("command", ""),
            cron=rec.get("cron", ""),
            description=rec.get("description", ""),
            enabled=rec.get("enabled", True),
            next_run=(
                datetime.fromisoformat(next_run_raw)
                if next_run_raw is not None
                else None
            ),
            created_at=datetime.fromisoformat(rec["created_at"]),
            updated_at=datetime.fromisoformat(rec["updated_at"]),
        )


def build_task_scheduler() -> LocalTaskScheduler | None:
    """Build the default file-backed task scheduler, or ``None`` when not configured.

    Wireless when the ``JARVIS_TASKS_ROOT`` directory is unset, so a Jarvis
    built from this factory stays offline by default (D7/D8).
    """
    root = os.environ.get("JARVIS_TASKS_ROOT")
    if not root:
        return None
    return LocalTaskScheduler(root)
