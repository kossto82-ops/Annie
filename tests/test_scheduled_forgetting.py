"""Increment 188, D39: an honest forgetting cadence on the scheduler seam.

One scheduled command is reserved by the core — ``forgetting sweep`` — and it
runs the live *read-only* memory sweep, so a cron task can keep memory health
fresh without an agent, a model or a network. Everything that matters here is
about honesty, so these tests pin it hard:

1. the reserved verb is matched as a whole command, so an instruction that
   merely mentions forgetting is never hijacked from the executor;
2. a sweep reports what may fade and what the gates held back, and says it
   deleted nothing;
3. nothing is ever deleted by the cadence, however often it runs;
4. the sweep runs against the *live* Jarvis, needs no instruction executor,
   and never reaches one;
5. the recurrence is the scheduler's: an occurrence fires once, the outcome is
   recorded honestly (including a crash), and the sweep never re-fires.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.forgetting import ForgettingCandidates
from jarvis.domain.services.scheduled_execution import (
    FORGETTING_SWEEP,
    is_forgetting_sweep,
)
from jarvis.domain.value_objects.capability import Capability
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.task_result import TaskResult
from jarvis.infrastructure.sqlite_task_scheduler import SqliteTaskScheduler
from jarvis.interface.command_center import handle
from jarvis.jarvis import Jarvis

_NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def _belief(statement: str, *, weight: float = 0.5, age_days: int = 100) -> Belief:
    """A belief formed and last renewed ``age_days`` before the fixed clock."""
    formed = _NOW - timedelta(days=age_days)
    belief = Belief(statement=statement, formed_at=formed)
    belief.add_evidence(
        Evidence(
            content=f"evidence for {statement}",
            source=EvidenceSource.DIRECT_OBSERVATION,
            weight=Confidence(weight),
            observed_at=formed,
        )
    )
    return belief


def _trait_evidence() -> Evidence:
    """Who the companion says they are: stated strongly, but long un-refreshed."""
    return Evidence(
        content="she said so",
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(0.9),
        observed_at=_NOW - timedelta(days=100),
    )


class _SpyAgent:
    """A stand-in executor that records every command it was handed."""

    def __init__(self) -> None:
        self.ran: list[str] = []

    def run_task(self, task: str) -> TaskResult:
        self.ran.append(task)
        return TaskResult(task=task, summary=f"did {task}", success=True)


@pytest.fixture
def clock() -> Iterator[dict[str, datetime]]:
    """A scheduler clock the test moves forward to make a cron task due."""
    probe: dict[str, datetime] = {"now": _NOW - timedelta(hours=1)}
    yield probe


@pytest.fixture
def scheduler(clock: dict[str, datetime]) -> SqliteTaskScheduler:
    counter = {"n": 0}

    def new_id() -> str:
        counter["n"] += 1
        return f"t{counter['n']}"

    return SqliteTaskScheduler(
        sqlite3.connect(":memory:"), clock=lambda: clock["now"], id_factory=new_id
    )


def _due_task(
    scheduler: SqliteTaskScheduler, clock: dict[str, datetime], **kwargs: object
) -> str:
    """Create a daily cron task and move the clock past its first occurrence."""
    task = scheduler.create_task(cron="0 9 * * *", **kwargs)  # type: ignore[arg-type]
    first_run = task.next_run
    assert first_run is not None, "a cron task always gets a first occurrence"
    clock["now"] = first_run + timedelta(minutes=5)
    return task.id


class TestReservedVerb:
    def test_the_verb_is_one_exact_command(self) -> None:
        assert FORGETTING_SWEEP == "forgetting sweep"
        assert is_forgetting_sweep(FORGETTING_SWEEP)
        assert is_forgetting_sweep("  Forgetting   Sweep  ")

    @pytest.mark.parametrize(
        "command",
        [
            "forget",
            "forget the old address",
            "forgetting sweep now",
            "forgetting sweeps",
            "sweep",
            "",
        ],
    )
    def test_anything_else_is_the_executors_business(self, command: str) -> None:
        # A near miss must never be hijacked from the earned-agency executor:
        # only the whole reserved command is the core's own sweep.
        assert not is_forgetting_sweep(command)


class TestSweepIsReadOnly:
    def test_it_reports_candidates_and_says_it_deleted_nothing(self) -> None:
        jarvis = Jarvis()
        service = ForgettingCandidates(
            jarvis.beliefs, companion=jarvis.companion, now=lambda: _NOW
        )

        result = service.sweep()

        assert result.task == FORGETTING_SWEEP
        assert result.success is True
        assert "swept 0 may-fade memories" in result.summary
        assert "deleted nothing" in result.summary

    def test_the_gates_are_counted_as_held_back(self) -> None:
        companion = Jarvis().companion
        store = Jarvis().beliefs
        store.save(_belief("freshly renewed", weight=0.1, age_days=7))
        trait = Belief(statement="she prefers tea", formed_at=_NOW - timedelta(days=100))
        trait.add_evidence(_trait_evidence())
        store.save(trait)
        companion.observe("she prefers tea", _trait_evidence())
        service = ForgettingCandidates(
            store, companion=companion, now=lambda: _NOW,
            grounded_confidence=lambda: 0.4,
        )

        summary = service.sweep().summary

        assert "swept 0 may-fade memories" in summary
        assert "held back 1 grounded" in summary
        assert "held back 1 recently renewed" in summary

    def test_a_candidate_is_named_by_count_not_silently_deleted(self) -> None:
        jarvis = Jarvis()
        jarvis.beliefs.save(_belief("old topic"))
        service = ForgettingCandidates(
            jarvis.beliefs, companion=jarvis.companion, now=lambda: _NOW
        )

        first = service.sweep()
        second = service.sweep()

        assert "swept 1 may-fade memory" in first.summary
        assert first.summary == second.summary, "a cadence must stay honest, not drift"
        assert [b.statement for b in jarvis.beliefs.all_beliefs()] == ["old topic"]


class TestScheduledSweep:
    def test_a_due_sweep_runs_the_live_read_only_sweep_without_an_agent(
        self, scheduler: SqliteTaskScheduler, clock: dict[str, datetime]
    ) -> None:
        task_id = _due_task(
            scheduler,
            clock,
            name="nightly memory sweep",
            command=FORGETTING_SWEEP,
        )
        jarvis = Jarvis(task_scheduler=scheduler)  # no instruction executor wired
        jarvis.beliefs.save(_belief("old topic"))

        runs = jarvis.fire_due_tasks()

        assert [r.name for r in runs] == ["nightly memory sweep"]
        assert runs[0].ok is True
        assert "swept 1 may-fade memory" in runs[0].output
        assert "deleted nothing" in runs[0].output
        recorded = scheduler.get_task(task_id)
        assert recorded.last_status == "ok"
        assert "deleted nothing" in recorded.last_output
        assert [b.statement for b in jarvis.beliefs.all_beliefs()] == ["old topic"]

    def test_the_sweep_never_reaches_the_executor(
        self, scheduler: SqliteTaskScheduler, clock: dict[str, datetime]
    ) -> None:
        _due_task(scheduler, clock, name="sweep", command=FORGETTING_SWEEP)
        _due_task(scheduler, clock, name="mail", command="echo hi")
        agent = _SpyAgent()
        jarvis = Jarvis(task_scheduler=scheduler, instruction_agent=agent)  # type: ignore[arg-type]

        runs = jarvis.fire_due_tasks()

        assert agent.ran == ["echo hi"], "the core sweep is not an agent task"
        assert {r.name: r.ok for r in runs} == {"sweep": True, "mail": True}

    def test_a_near_miss_command_still_goes_to_the_executor(
        self, scheduler: SqliteTaskScheduler, clock: dict[str, datetime]
    ) -> None:
        _due_task(scheduler, clock, name="explicit", command="forget the old address")
        agent = _SpyAgent()
        jarvis = Jarvis(task_scheduler=scheduler, instruction_agent=agent)  # type: ignore[arg-type]
        jarvis.beliefs.save(_belief("old address"))

        jarvis.fire_due_tasks()

        assert agent.ran == ["forget the old address"]
        assert [b.statement for b in jarvis.beliefs.all_beliefs()] == ["old address"]

    def test_running_one_task_by_id_runs_the_sweep(
        self, scheduler: SqliteTaskScheduler, clock: dict[str, datetime]
    ) -> None:
        task_id = _due_task(
            scheduler, clock, name="sweep", command=" Forgetting Sweep "
        )
        jarvis = Jarvis(task_scheduler=scheduler)  # type: ignore[arg-type]

        outcome = jarvis.run_scheduled_task(task_id)

        assert outcome.success is True
        assert "deleted nothing" in outcome.summary
        assert scheduler.get_task(task_id).last_status == "ok"

    def test_a_disabled_sweep_task_refuses_to_run(
        self, scheduler: SqliteTaskScheduler, clock: dict[str, datetime]
    ) -> None:
        task_id = _due_task(scheduler, clock, name="sweep", command=FORGETTING_SWEEP)
        jarvis = Jarvis(task_scheduler=scheduler)  # type: ignore[arg-type]
        jarvis.disable_scheduled_task(task_id)

        with pytest.raises(RuntimeError, match="disabled"):
            jarvis.run_scheduled_task(task_id)

    def test_the_cadence_fires_once_per_occurrence(
        self, scheduler: SqliteTaskScheduler, clock: dict[str, datetime]
    ) -> None:
        task_id = _due_task(scheduler, clock, name="sweep", command=FORGETTING_SWEEP)
        jarvis = Jarvis(task_scheduler=scheduler)  # type: ignore[arg-type]

        first = jarvis.fire_due_tasks()
        second = jarvis.fire_due_tasks()

        assert len(first) == 1
        assert second == (), "the same occurrence must never fire twice"
        assert scheduler.due_tasks() == ()
        assert scheduler.get_task(task_id).next_run == datetime(
            2026, 10, 8, 9, 0, tzinfo=UTC
        )

    def test_a_task_that_is_not_due_never_sweeps(
        self, scheduler: SqliteTaskScheduler, clock: dict[str, datetime]
    ) -> None:
        scheduler.create_task(name="sweep", command=FORGETTING_SWEEP, cron="0 9 * * *")
        jarvis = Jarvis(task_scheduler=scheduler)  # type: ignore[arg-type]

        assert jarvis.fire_due_tasks() == ()
        assert scheduler.list_tasks()[0].last_run is None

    def test_a_sweep_crash_is_recorded_honestly_and_the_sweep_keeps_going(
        self,
        scheduler: SqliteTaskScheduler,
        clock: dict[str, datetime],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sweep_id = _due_task(scheduler, clock, name="sweep", command=FORGETTING_SWEEP)
        _due_task(scheduler, clock, name="mail", command="echo hi")

        def boom(self: Jarvis) -> TaskResult:
            raise RuntimeError("belief store unreachable")

        monkeypatch.setattr(Jarvis, "sweep_forgetting", boom)
        agent = _SpyAgent()
        jarvis = Jarvis(task_scheduler=scheduler, instruction_agent=agent)  # type: ignore[arg-type]

        runs = jarvis.fire_due_tasks()

        assert agent.ran == ["echo hi"], "one failure never aborts the sweep"
        assert {r.name: r.ok for r in runs} == {"sweep": False, "mail": True}
        failed = next(r for r in runs if r.name == "sweep")
        assert "belief store unreachable" in failed.output
        assert scheduler.get_task(sweep_id).last_status == "error"


class TestTasksCommandSurface:
    """The reserved verb is reachable the way a user actually reaches it."""

    def _capable(self, jarvis: Jarvis) -> None:
        jarvis.remember_capability(
            Capability(
                name="manage tasks",
                description="schedule and manage recurring tasks",
                requirement="a wired task scheduler at the edge (TaskScheduler)",
                provenance="test harness",
                status=CapabilityStatus.ACQUIRED,
            )
        )

    def test_creating_a_sweep_task_says_it_never_deletes(
        self, scheduler: SqliteTaskScheduler
    ) -> None:
        jarvis = Jarvis(task_scheduler=scheduler)  # type: ignore[arg-type]
        self._capable(jarvis)

        reply = handle(
            jarvis,
            "tasks",
            {
                "action": "create",
                "name": "nightly memory sweep",
                "command": FORGETTING_SWEEP,
                "cron": "0 3 * * *",
            },
        )

        assert "never deletes" in str(reply["reply"])

    def test_firing_it_narrates_the_honest_sweep(
        self, scheduler: SqliteTaskScheduler, clock: dict[str, datetime]
    ) -> None:
        _due_task(scheduler, clock, name="memory sweep", command=FORGETTING_SWEEP)
        jarvis = Jarvis(task_scheduler=scheduler)  # type: ignore[arg-type]
        jarvis.beliefs.save(_belief("old topic"))
        self._capable(jarvis)

        reply = handle(jarvis, "tasks", {"action": "fire"})

        assert reply["ok"] is True
        assert "Fired 1 due task(s)" in str(reply["reply"])
        assert "deleted nothing" in str(reply["reply"])
        assert [b.statement for b in jarvis.beliefs.all_beliefs()] == ["old topic"]