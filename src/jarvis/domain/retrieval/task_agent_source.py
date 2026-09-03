"""TaskAgent: the seam between Jarvis and an edge agent it can delegate to.

Delegation (revised D1) lets Jarvis hand a *material* task -- something in the
world, like files, email, or tool calls -- to an agent at the edge. The cognitive
cycle stays in the core: this Protocol only *acts* on a clearly-specified task
and returns a plain ``TaskResult`` account (D6). The decision to delegate at all,
and the specific task, are deliberate and gated through the controlled-autonomy
policy (ask-first for real-world effects, per `09_CONTROLLED_AUTONOMY` and the
Tool Registry's permission levels).

Like the other domain seams (``ExternalSource``, ``ResearchSource``, ``MailBox``),
this is a domain Protocol behind which a concrete agent adapter lives in
``infrastructure`` (D7): transport, network, and any agent orchestration stay at
the edge; the transport is injectable; tests stay deterministic and offline (D8).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jarvis.domain.value_objects.task_result import TaskResult


@runtime_checkable
class TaskAgent(Protocol):
    """Runs one delegated material task at the edge and reports its outcome."""

    def run_task(self, task: str) -> TaskResult:
        """Execute ``task`` and return its plain outcome.

        The task is a concrete, already-decided material instruction (never a
        reasoning cue). A ``success=False`` result is a truthful "this did not
        work", never a fabricated success.
        """
        ...
