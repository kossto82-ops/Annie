"""Tests for the scheduled-execution driver (Increment 183, D35).

Covers ``run_due_tasks`` — the fire-once sweep that composes the
``TaskScheduler`` seam with the earned-agency executor — plus the Jarvis
facade and the real-store recurrence behaviour the sweep depends on: after a
fire, ``record_run`` advances a cron task's ``next_run`` so the same
occurrence is never due again.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from jarvis.domain.services.scheduled_execution import ScheduledRun, run_due_tasks
from jarvis.domain.value_objects.scheduled_task import ScheduledTask
from jarvis.domain.value_objects.task_result import TaskResult
from jarvis.infrastructure.sqlite_task_scheduler import SqliteTaskScheduler
from jarvis.jarvis import Jarvis

_NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def _task(
    *,
    tid: str,
    name: str,
    command: str,
    next_run: datetime | None = None,
    enabled: bool = True,
) -> ScheduledTask:
    return ScheduledTask(
        id=tid,
        name=name,
        command=command,
        cron="",
        description="",
        enabled=enabled,
        next_run=next_run,
        created_at=_NOW - timedelta(days=1),
        updated_at=_NOW - timedelta(days=1),
    )


class _FakeScheduler:
    """A minimal ``TaskScheduler`` exposing just enough for the driver tests."""

    def __init__(self) -> None:
        self.tasks: dict[str, ScheduledTask] = {}
        self.recorded: list[tuple[str, bool, str]] = []

    def list_tasks(self, *, limit: int = 100) -> tuple[ScheduledTask, ...]:
        return tuple(self.tasks.values())[:limit]

    def get_task(self, task_id: str) -> ScheduledTask:
        return self.tasks[task_id]

    def create_task(
        self,
        *,
        name: str,
        command: str,
        cron: str = "",
        description: str = "",
        enabled: bool = True,
    ) -> ScheduledTask:
        task = _task(tid=f"t{len(self.tasks) + 1}", name=name, command=command)
        self.tasks[task.id] = task
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
        current = self.tasks[task_id]
        task = ScheduledTask(
            id=current.id, name=name, command=command, cron=cron or current.cron,
            description=description, enabled=enabled, next_run=current.next_run,
            last_run=current.last_run, last_status=current.last_status,
            last_output=current.last_output, created_at=current.created_at,
            updated_at=current.updated_at,
        )
        self.tasks[task_id] = task
        return task

    def delete_task(self, task_id: str) -> None:
        self.tasks.pop(task_id)

    def enable_task(self, task_id: str) -> ScheduledTask:
        current = self.tasks[task_id]
        task = ScheduledTask(id=current.id, name=current.name, command=current.command,
                             cron=current.cron, enabled=True)
        self.tasks[task_id] = task
        return task

    def disable_task(self, task_id: str) -> ScheduledTask:
        current = self.tasks[task_id]
        task = ScheduledTask(id=current.id, name=current.name, command=current.command,
                             cron=current.cron, enabled=False)
        self.tasks[task_id] = task
        return task

    def due_tasks(self) -> tuple[ScheduledTask, ...]:
        return tuple(
            t
            for t in self.tasks.values()
            if t.enabled and t.next_run is not None and t.next_run <= _NOW
        )

    def record_run(self, task_id: str, *, ok: bool, output: str) -> ScheduledTask:
        self.recorded.append((task_id, ok, output))
        current = self.tasks[task_id]
        ran = ScheduledTask(
            id=current.id,
            name=current.name,
            command=current.command,
            cron=current.cron,
            description=current.description,
            enabled=current.enabled,
            next_run=current.next_run,
            last_run=_NOW,
            last_status="ok" if ok else "error",
            last_output=output[:2000],
            created_at=current.created_at,
            updated_at=_NOW,
        )
        self.tasks[task_id] = ran
        return ran


class _Executor:
    """A stand-in for the ``approved=False`` instruction executor."""

    def __init__(self) -> None:
        self.ran: list[str] = []

    def __call__(self, command: str) -> TaskResult:
        self.ran.append(command)
        if command == "boom":
            raise RuntimeError("blown up")
        return TaskResult(
            task=command,
            summary="done " + command,
            success=command != "fail",
        )


class TestRunDueTasks:
    def test_fires_each_due_task_once_and_records(self) -> None:
        scheduler = _FakeScheduler()
        scheduler.tasks["a"] = _task(
            tid="a", name="alpha", command="echo a", next_run=_NOW - timedelta(minutes=1)
        )
        scheduler.tasks["b"] = _task(
            tid="b", name="beta", command="echo b", next_run=_NOW - timedelta(minutes=2)
        )
        executor = _Executor()
        runs = run_due_tasks(scheduler, executor)
        assert executor.ran == ["echo a", "echo b"]
        assert runs == (
            ScheduledRun(task_id="a", name="alpha", ok=True, output="done echo a"),
            ScheduledRun(task_id="b", name="beta", ok=True, output="done echo b"),
        )
        assert scheduler.recorded == [
            ("a", True, "done echo a"),
            ("b", True, "done echo b"),
        ]

    def test_ignores_tasks_not_yet_due(self) -> None:
        scheduler = _FakeScheduler()
        scheduler.tasks["later"] = _task(
            tid="later", name="later", command="echo", next_run=_NOW + timedelta(hours=1)
        )
        scheduler.tasks["nope"] = _task(tid="nope", name="nope", command="echo", next_run=None)
        executor = _Executor()
        assert run_due_tasks(scheduler, executor) == ()
        assert executor.ran == []
        assert scheduler.recorded == []

    def test_a_honest_failure_is_recorded_and_the_sweep_keeps_going(self) -> None:
        scheduler = _FakeScheduler()
        scheduler.tasks["bad"] = _task(
            tid="bad", name="bad", command="fail", next_run=_NOW - timedelta(minutes=1)
        )
        scheduler.tasks["good"] = _task(
            tid="good", name="good", command="ok", next_run=_NOW - timedelta(minutes=1)
        )
        executor = _Executor()
        runs = run_due_tasks(scheduler, executor)
        assert [r.ok for r in runs] == [False, True]
        assert runs[0].output == "done fail"
        assert scheduler.recorded == [
            ("bad", False, "done fail"),
            ("good", True, "done ok"),
        ]

    def test_an_executor_crash_is_recorded_and_the_sweep_keeps_going(self) -> None:
        scheduler = _FakeScheduler()
        scheduler.tasks["boom"] = _task(
            tid="boom", name="boom", command="boom", next_run=_NOW - timedelta(minutes=1)
        )
        scheduler.tasks["after"] = _task(
            tid="after", name="after", command="after", next_run=_NOW - timedelta(minutes=1)
        )
        executor = _Executor()
        runs = run_due_tasks(scheduler, executor)
        assert executor.ran == ["boom", "after"]
        assert runs[0].ok is False and runs[0].output == "blown up"
        assert runs[1].ok is True

    @staticmethod
    def _cron_store() -> tuple[SqliteTaskScheduler, dict[str, datetime], _Executor]:
        probe = {"current": datetime(2026, 9, 25, 8, 0, tzinfo=UTC)}

        def clock() -> datetime:
            return probe["current"]

        store = SqliteTaskScheduler(
            sqlite3.connect(":memory:"), clock=clock, id_factory=lambda: "t1"
        )
        return store, probe, _Executor()

    def test_firing_a_cron_task_advances_it_and_never_due_again(self) -> None:
        store, probe, executor = self._cron_store()
        store.create_task(name="daily", command="report", cron="0 9 * * *")
        probe["current"] = datetime(2026, 9, 25, 9, 5, tzinfo=UTC)  # due now
        runs = run_due_tasks(store, executor)
        assert [r.name for r in runs] == ["daily"]
        after = store.get_task("t1")
        assert after.next_run == datetime(2026, 9, 26, 9, 0, tzinfo=UTC)
        assert store.due_tasks() == ()


class TestJarvisFireDueTasks:
    def test_fire_runs_only_due_tasks_through_the_facade(self) -> None:
        scheduler = _FakeScheduler()
        scheduler.tasks["due"] = _task(
            tid="due", name="due", command="send", next_run=_NOW - timedelta(minutes=1)
        )
        scheduler.tasks["later"] = _task(
            tid="later", name="later", command="wait", next_run=_NOW + timedelta(hours=1)
        )

        class _Agent:
            def run_task(self, task: str) -> TaskResult:
                return TaskResult(task=task, summary="sent", success=True)

        jarvis = Jarvis(task_scheduler=scheduler, instruction_agent=_Agent())  # type: ignore[arg-type]
        runs = jarvis.fire_due_tasks()
        assert [r.name for r in runs] == ["due"]
        assert scheduler.recorded == [("due", True, "sent")]

    def test_no_executor_means_nothing_runs_and_nothing_is_recorded(self) -> None:
        scheduler = _FakeScheduler()
        scheduler.tasks["due"] = _task(
            tid="due", name="due", command="send", next_run=_NOW - timedelta(minutes=1)
        )
        jarvis = Jarvis(task_scheduler=scheduler)  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="executor"):
            jarvis.fire_due_tasks()
        assert scheduler.recorded == []

    def test_offline_raises_clearly(self) -> None:
        with pytest.raises(RuntimeError, match="task-scheduler capability"):
            Jarvis().fire_due_tasks()