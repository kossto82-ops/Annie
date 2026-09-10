"""Tests for the task-scheduler capability seam (Odysseus #7).

Covers the ``ScheduledTask`` value object, the ``TaskScheduler`` Protocol
surface, the ``TaskSchedulerCapability`` provider, and Jarvis's integration:
``can_do`` reflects a wired scheduler, the task methods hand read/write to the
store edge, and an unwired Jarvis stays offline with clear errors.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jarvis.domain.retrieval.task_scheduler import TaskScheduler
from jarvis.domain.services.cron import next_run_after, validate_cron
from jarvis.domain.value_objects.capability import Capability
from jarvis.domain.value_objects.scheduled_task import ScheduledTask
from jarvis.domain.value_objects.task_result import TaskResult
from jarvis.infrastructure.capability_registry import (
    TaskSchedulerCapability,
    build_default_registry,
)
from jarvis.jarvis import Jarvis


class _FakeTaskScheduler:
    """An in-memory task scheduler recording calls for deterministic assertions."""

    def __init__(self) -> None:
        self.tasks: dict[str, ScheduledTask] = {}
        self.created: list[str] = []
        self.deleted: list[str] = []

    def list_tasks(self, *, limit: int = 100) -> tuple[ScheduledTask, ...]:
        tasks = sorted(
            self.tasks.values(), key=lambda t: t.created_at, reverse=True,
        )
        return tuple(tasks[:limit])

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
        n = len(self.tasks) + 1
        task = ScheduledTask(
            id=f"t{n}", name=name, command=command, cron=cron,
            description=description, enabled=enabled,
        )
        self.tasks[task.id] = task
        self.created.append(task.id)
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
        task = ScheduledTask(
            id=task_id, name=name, command=command, cron=cron,
            description=description, enabled=enabled,
        )
        self.tasks[task_id] = task
        return task

    def delete_task(self, task_id: str) -> None:
        self.deleted.append(task_id)
        self.tasks.pop(task_id, None)

    def enable_task(self, task_id: str) -> ScheduledTask:
        task = self.tasks[task_id]
        enabled = ScheduledTask(
            id=task.id, name=task.name, command=task.command, cron=task.cron,
            description=task.description, enabled=True,
        )
        self.tasks[task_id] = enabled
        return enabled

    def disable_task(self, task_id: str) -> ScheduledTask:
        task = self.tasks[task_id]
        disabled = ScheduledTask(
            id=task.id, name=task.name, command=task.command, cron=task.cron,
            description=task.description, enabled=False,
        )
        self.tasks[task_id] = disabled
        return disabled

    def due_tasks(self) -> tuple[ScheduledTask, ...]:
        now = datetime.now(UTC)
        return tuple(
            t for t in self.tasks.values()
            if t.enabled and t.next_run is not None and t.next_run <= now
        )

    def record_run(self, task_id: str, *, ok: bool, output: str) -> ScheduledTask:
        current = self.tasks[task_id]
        ran = ScheduledTask(
            id=current.id, name=current.name, command=current.command,
            cron=current.cron, description=current.description,
            enabled=current.enabled, next_run=current.next_run,
            last_run=datetime.now(UTC), last_status="ok" if ok else "error",
            last_output=output[:2000],
        )
        self.tasks[task_id] = ran
        return ran


class _FakeInstructionAgent:
    """A stub executor returning (or raising) a canned outcome."""

    def __init__(self, *, ok: bool = True, summary: str = "did it") -> None:
        self._ok = ok
        self._summary = summary
        self.ran: list[str] = []

    def run_task(self, task: str) -> TaskResult:
        self.ran.append(task)
        if not self._ok and self._summary == "raise":
            raise RuntimeError("executor boom")
        return TaskResult(task=task, summary=self._summary, success=self._ok)


class TestScheduledTask:
    def test_requires_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            ScheduledTask(id="1", name="", command="echo hi")

    def test_requires_command(self) -> None:
        with pytest.raises(ValueError, match="command"):
            ScheduledTask(id="1", name="backup", command="")

    def test_records_provenance(self) -> None:
        task = ScheduledTask(id="7", name="backup", command="tar czf")
        assert task.provenance == "scheduled task 7 'backup'"


class TestTaskSchedulerProtocol:
    def test_fake_scheduler_satisfies_the_protocol(self) -> None:
        assert isinstance(_FakeTaskScheduler(), TaskScheduler)


class TestTaskSchedulerCapability:
    def test_task_capability_backs_the_tasks_name(self) -> None:
        provider = TaskSchedulerCapability(_FakeTaskScheduler())  # type: ignore[arg-type]
        assert provider.capability == "manage tasks"
        assert provider.is_available()

    def test_default_registry_backs_tasks_when_a_scheduler_is_wired(self) -> None:
        scheduler = _FakeTaskScheduler()
        registry = build_default_registry(None, task_scheduler=scheduler)  # type: ignore[arg-type]
        assert registry.provider_for("manage tasks") is not None

    def test_default_registry_without_a_scheduler_has_no_tasks(self) -> None:
        registry = build_default_registry(None)
        assert registry.provider_for("manage tasks") is None


class TestJarvisTasks:
    @staticmethod
    def _acquire(jarvis: Jarvis) -> None:
        capability = Capability(
            name="manage tasks",
            description="create and run scheduled recurring tasks",
            requirement="a wired task scheduler at the edge (TaskScheduler)",
            provenance="test",
        )
        jarvis.remember_capability(capability)
        jarvis.acquire_capability("manage tasks")

    def test_can_do_reflects_a_wired_scheduler(self) -> None:
        jarvis = Jarvis(task_scheduler=_FakeTaskScheduler())  # type: ignore[arg-type]
        self._acquire(jarvis)
        assert jarvis.can_do("manage tasks")

    def test_unwired_jarvis_is_offline_to_tasks(self) -> None:
        jarvis = Jarvis()
        self._acquire(jarvis)
        assert not jarvis.can_do("manage tasks")

    def test_create_and_read_round_trips(self) -> None:
        jarvis = Jarvis(task_scheduler=_FakeTaskScheduler())  # type: ignore[arg-type]
        task = jarvis.create_scheduled_task(
            name="backup", command="tar czf /tmp/bak.tar.gz ~", cron="0 2 * * *",
        )
        assert task.id
        assert jarvis.get_scheduled_task(task.id).name == "backup"
        names = [t.name for t in jarvis.list_scheduled_tasks()]
        assert names[-1] == "backup"

    def test_update_and_delete(self) -> None:
        scheduler = _FakeTaskScheduler()
        jarvis = Jarvis(task_scheduler=scheduler)  # type: ignore[arg-type]
        task = jarvis.create_scheduled_task(name="a", command="echo a")
        jarvis.update_scheduled_task(
            task.id, name="b", command="echo b", cron="*/5 * * * *",
            description="desc", enabled=False,
        )
        assert jarvis.get_scheduled_task(task.id).name == "b"
        jarvis.delete_scheduled_task(task.id)
        assert scheduler.deleted == [task.id]

    def test_enable_and_disable(self) -> None:
        jarvis = Jarvis(task_scheduler=_FakeTaskScheduler())  # type: ignore[arg-type]
        task = jarvis.create_scheduled_task(
            name="cron", command="echo", enabled=True,
        )
        disabled = jarvis.disable_scheduled_task(task.id)
        assert not disabled.enabled
        enabled = jarvis.enable_scheduled_task(task.id)
        assert enabled.enabled

    def test_due_tasks(self) -> None:
        scheduler = _FakeTaskScheduler()
        jarvis = Jarvis(task_scheduler=scheduler)  # type: ignore[arg-type]
        past = datetime.now(UTC) - timedelta(hours=1)
        future = datetime.now(UTC) + timedelta(hours=1)
        task = jarvis.create_scheduled_task(
            name="due", command="echo", enabled=True,
        )
        # Manually set next_run to the past
        due_task = ScheduledTask(
            id=task.id, name=task.name, command=task.command,
            cron=task.cron, enabled=True, next_run=past,
        )
        scheduler.tasks[task.id] = due_task
        # Also create a future task
        future_task = jarvis.create_scheduled_task(
            name="later", command="echo", enabled=True,
        )
        future_t = ScheduledTask(
            id=future_task.id, name=future_task.name, command=future_task.command,
            enabled=True, next_run=future,
        )
        scheduler.tasks[future_task.id] = future_t
        due = jarvis.due_scheduled_tasks()
        due_names = [t.name for t in due]
        assert "due" in due_names
        assert "later" not in due_names

    def test_wiring_a_scheduler_at_runtime_updates_can_do(self) -> None:
        jarvis = Jarvis()
        self._acquire(jarvis)
        assert not jarvis.can_do("manage tasks")
        jarvis.set_task_scheduler(_FakeTaskScheduler())  # type: ignore[arg-type]
        assert jarvis.can_do("manage tasks")
        jarvis.set_task_scheduler(None)
        assert not jarvis.can_do("manage tasks")

    def test_methods_raise_clearly_when_offline(self) -> None:
        jarvis = Jarvis()
        with pytest.raises(RuntimeError, match="task-scheduler capability"):
            jarvis.list_scheduled_tasks()


class TestCron:
    def test_empty_means_unscheduled(self) -> None:
        validate_cron("")
        validate_cron("   ")
        assert next_run_after("", datetime.now(UTC)) is None

    def test_common_shapes_validate(self) -> None:
        for cron in ("0 9 * * *", "*/15 * * * *", "0 0 1 * *", "30 8 * * MON-FRI", "0 12 * JAN *"):
            validate_cron(cron)

    def test_bad_shapes_raise_clearly(self) -> None:
        for cron in ("nope", "0 9 * *", "0 9 * * * *", "61 * * * *", "0 24 * * *",
                     "0 9 * * XXX", "0 9 * * */0", "0 9 * * 1-"):
            with pytest.raises(ValueError, match="cron"):
                validate_cron(cron)

    def test_next_run_after_simple(self) -> None:
        after = datetime(2026, 9, 10, 8, 30, tzinfo=UTC)
        assert next_run_after("0 9 * * *", after) == datetime(2026, 9, 10, 9, 0, tzinfo=UTC)
        assert next_run_after("* * * * *", after) == datetime(2026, 9, 10, 8, 31, tzinfo=UTC)

    def test_next_run_skips_to_next_day(self) -> None:
        after = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)
        assert next_run_after("0 9 * * *", after) == datetime(2026, 9, 11, 9, 0, tzinfo=UTC)

    def test_next_run_weekday_or_month_day(self) -> None:
        # 2026-09-10 is a Thursday.
        after = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
        assert next_run_after("0 9 * * MON", after) == datetime(2026, 9, 14, 9, 0, tzinfo=UTC)
        assert next_run_after("0 9 11 * *", after) == datetime(2026, 9, 11, 9, 0, tzinfo=UTC)

    def test_impossible_date_gives_up_honestly(self) -> None:
        after = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
        assert next_run_after("0 0 30 2 *", after) is None


class TestJarvisRunScheduledTask:
    def _wired(self, agent: _FakeInstructionAgent | None) -> tuple[Jarvis, str]:
        scheduler = _FakeTaskScheduler()
        jarvis = Jarvis(
            task_scheduler=scheduler,  # type: ignore[arg-type]
            instruction_agent=agent,  # type: ignore[arg-type]
        )
        task = jarvis.create_scheduled_task(name="job", command="do the thing")
        assert isinstance(scheduler, _FakeTaskScheduler)
        return jarvis, task.id

    def test_success_runs_and_records(self) -> None:
        agent = _FakeInstructionAgent(ok=True, summary="all done")
        jarvis, task_id = self._wired(agent)
        outcome = jarvis.run_scheduled_task(task_id)
        assert outcome.success is True
        assert agent.ran == ["do the thing"]
        stored = jarvis.get_scheduled_task(task_id)
        assert stored.last_status == "ok"
        assert stored.last_output == "all done"
        assert stored.last_run is not None

    def test_honest_failure_is_recorded(self) -> None:
        agent = _FakeInstructionAgent(ok=False, summary="it broke")
        jarvis, task_id = self._wired(agent)
        outcome = jarvis.run_scheduled_task(task_id)
        assert outcome.success is False
        assert jarvis.get_scheduled_task(task_id).last_status == "error"

    def test_executor_crash_is_recorded_and_raised(self) -> None:
        agent = _FakeInstructionAgent(ok=False, summary="raise")
        jarvis, task_id = self._wired(agent)
        with pytest.raises(RuntimeError, match="executor boom"):
            jarvis.run_scheduled_task(task_id)
        assert jarvis.get_scheduled_task(task_id).last_status == "error"

    def test_disabled_task_is_refused_without_recording(self) -> None:
        agent = _FakeInstructionAgent()
        jarvis, task_id = self._wired(agent)
        jarvis.disable_scheduled_task(task_id)
        with pytest.raises(RuntimeError, match="disabled"):
            jarvis.run_scheduled_task(task_id)
        assert agent.ran == []
        assert jarvis.get_scheduled_task(task_id).last_run is None

    def test_missing_executor_is_refused_without_recording(self) -> None:
        jarvis, task_id = self._wired(None)
        with pytest.raises(RuntimeError, match="executor"):
            jarvis.run_scheduled_task(task_id)
        assert jarvis.get_scheduled_task(task_id).last_run is None

    def test_offline_and_unknown_are_clear_errors(self) -> None:
        with pytest.raises(RuntimeError, match="task-scheduler capability"):
            Jarvis().run_scheduled_task("t1")
        jarvis, _ = self._wired(_FakeInstructionAgent())
        with pytest.raises(KeyError):
            jarvis.run_scheduled_task("missing")
