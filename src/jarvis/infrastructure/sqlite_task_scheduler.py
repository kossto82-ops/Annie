"""SqliteTaskScheduler: a TaskScheduler on a real database at the edge (Odysseus #7, D10).

A task scheduler is a bounded, reversible material capability: a store of scheduled
tasks the user asked Jarvis to manage. This implementation persists those tasks as
JSON payloads in a SQLite table keyed by task id, so the seam the Local scheduler
serves through a ``tasks.json`` file is served through transactional commits instead.
Task content is bookkeeping for *what* to run and *when*; nothing here reasons about
the tasks (D6) or executes them.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from jarvis.domain.value_objects.scheduled_task import ScheduledTask

_Record = dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC)


def _to_record(task: ScheduledTask) -> _Record:
    return {
        "name": task.name,
        "command": task.command,
        "cron": task.cron,
        "description": task.description,
        "enabled": task.enabled,
        "next_run": task.next_run.isoformat() if task.next_run is not None else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


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


class SqliteTaskScheduler:
    """A TaskScheduler over scheduled tasks keyed by id in a SQLite table."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._conn = connection
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._tasks: dict[str, ScheduledTask] = {}
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            "task_id TEXT PRIMARY KEY, "
            "payload TEXT NOT NULL)"
        )
        self._load()

    # -- TaskScheduler --------------------------------------------------------

    def list_tasks(self, *, limit: int = 100) -> tuple[ScheduledTask, ...]:
        tasks = sorted(
            self._tasks.values(), key=lambda t: t.created_at, reverse=True
        )
        return tuple(tasks[:limit])

    def get_task(self, task_id: str) -> ScheduledTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"no scheduled task with id {task_id!r}")
        return task

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
        self._upsert(task)
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
        current = self.get_task(task_id)
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
        self._upsert(constructed)
        return constructed

    def delete_task(self, task_id: str) -> None:
        if task_id not in self._tasks:
            raise KeyError(f"no scheduled task with id {task_id!r}")
        self._tasks.pop(task_id)
        self._conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        self._conn.commit()

    def enable_task(self, task_id: str) -> ScheduledTask:
        return self._set_enabled(task_id, True)

    def disable_task(self, task_id: str) -> ScheduledTask:
        return self._set_enabled(task_id, False)

    def due_tasks(self) -> tuple[ScheduledTask, ...]:
        now = _now()
        return tuple(
            t
            for t in self._tasks.values()
            if t.enabled and t.next_run is not None and t.next_run <= now
        )

    # -- storage helpers ------------------------------------------------------

    def _set_enabled(self, task_id: str, enabled: bool) -> ScheduledTask:
        current = self.get_task(task_id)
        flipped = ScheduledTask(
            id=current.id,
            name=current.name,
            command=current.command,
            cron=current.cron,
            description=current.description,
            enabled=enabled,
            next_run=current.next_run,
            created_at=current.created_at,
            updated_at=_now(),
        )
        self._upsert(flipped)
        return flipped

    def _upsert(self, task: ScheduledTask) -> None:
        self._tasks[task.id] = task
        payload = json.dumps(_to_record(task), separators=(",", ":"))
        self._conn.execute(
            "INSERT INTO tasks (task_id, payload) VALUES (?, ?) "
            "ON CONFLICT(task_id) DO UPDATE SET payload = excluded.payload",
            (task.id, payload),
        )
        self._conn.commit()

    def _load(self) -> None:
        rows = self._conn.execute(
            "SELECT task_id, payload FROM tasks"
        ).fetchall()
        for task_id, payload in rows:
            self._tasks[task_id] = _from_record(task_id, json.loads(payload))