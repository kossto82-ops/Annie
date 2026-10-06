"""Scheduled execution: sweep due tasks once through the earned-agency executor.

The ``TaskScheduler`` seam stores *what* to run and *when*, and records runs;
it never executes anything (D6/D7). This small orchestrator composes the
scheduler with the instruction executor: a ``fire`` pass takes every
currently-due enabled task exactly once, runs its ``command`` through the same
``approved=False`` executor ``tasks run`` uses, and records each outcome on
the task (the store then advances the recurrence; see D35). The sweep never
sleeps or loops on its own — a caller (the ``tasks fire`` command, or a
shutdown-safe cadence) invokes it whenever a sweep is wanted, so the
execution stays deterministic, offline-testable, and free of background
threads (D8).

One command is *reserved* by the core instead of delegated to an agent:
:data:`FORGETTING_SWEEP`, the honest forgetting cadence (D39). It names the
core's own read-only memory sweep, so a scheduled task can keep memory health
fresh on a cron without a model, a tool, or a network. It deletes nothing —
:func:`is_forgetting_sweep` recognises the verb, and the caller runs the
sweep against its live state (D39); every other command still goes to the
earned-agency executor untouched.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from jarvis.domain.retrieval.task_scheduler import TaskScheduler
from jarvis.domain.value_objects.task_result import TaskResult

#: The one scheduled command the core reserves: a read-only forgetting sweep.
FORGETTING_SWEEP = "forgetting sweep"


def is_forgetting_sweep(command: str) -> bool:
    """Whether ``command`` is the reserved read-only forgetting sweep.

    Case- and whitespace-insensitive, and matched as the *whole* command: a
    longer instruction that merely mentions forgetting ("forget the old
    address") is not the reserved verb and is never hijacked from the
    executor (D39).
    """
    return " ".join(command.split()).lower() == FORGETTING_SWEEP


@dataclass(frozen=True, slots=True, kw_only=True)
class ScheduledRun:
    """One due task the sweep fired, with the outcome recorded on the task."""

    task_id: str
    name: str
    ok: bool
    output: str


def run_due_tasks(
    scheduler: TaskScheduler,
    executor: Callable[[str], TaskResult],
) -> tuple[ScheduledRun, ...]:
    """Fire every currently-due enabled task once through ``executor``.

    The sweep snapshots ``scheduler.due_tasks()`` at the start, so each task
    runs at most once per call even when the store cannot advance its
    recurrence. Each outcome is recorded through ``scheduler.record_run``;
    one task failing (an ``ok=False`` result or a raised executor error) is
    recorded on that task and the sweep keeps going — nothing is swallowed
    into a fake success, the per-task run report carries the honest failure.
    """
    runs: list[ScheduledRun] = []
    for task in scheduler.due_tasks():
        try:
            outcome = executor(task.command)
            ok, output = outcome.success, outcome.summary
        except Exception as error:  # noqa: BLE001 - executor boundary; the run report carries it
            ok, output = False, str(error)
        recorded = scheduler.record_run(task.id, ok=ok, output=output)
        runs.append(
            ScheduledRun(
                task_id=recorded.id, name=recorded.name, ok=ok, output=output
            )
        )
    return tuple(runs)