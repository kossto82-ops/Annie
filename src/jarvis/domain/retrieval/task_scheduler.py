"""TaskScheduler: the seam between Jarvis and a local task scheduler (Odysseus #7).

A task scheduler is a *material*, low-risk, reversible capability Jarvis may
gain (Vision §34, revised D1). Like ``NotesStore``/``CalendarStore``, this is
a domain Protocol behind which a concrete adapter lives in ``infrastructure``
(D7): the storage back-end stays at the edge, the transport is injectable, and
tests stay deterministic and offline (D8).

A ``TaskScheduler`` *stores* and *returns* plain scheduled-task content with
provenance. It never reasons about the tasks (D6) and never writes to Jarvis's
beliefs or memory on its own. Creating/updating/deleting/enabling/disabling
are reversible material actions the caller must have gated; reading is
retrieval that becomes candidate evidence.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jarvis.domain.value_objects.scheduled_task import ScheduledTask


@runtime_checkable
class TaskScheduler(Protocol):
    """Gives Jarvis read and write access to a local task scheduler on request."""

    def list_tasks(self, *, limit: int = 100) -> tuple[ScheduledTask, ...]:
        """Return up to ``limit`` tasks, newest first, as retrieval artifacts.

        An empty tuple is an honest "no tasks here", not an error. Each task
        carries provenance; Jarvis weighs them as candidate evidence (D6).
        """
        ...

    def get_task(self, task_id: str) -> ScheduledTask:
        """Return one task by its id, or raise when it cannot be retrieved.

        Raises only on a real failure of the underlying store; an unknown id is
        a clear error, never a fabricated task.
        """
        ...

    def create_task(
        self,
        *,
        name: str,
        command: str,
        cron: str = "",
        description: str = "",
        enabled: bool = True,
    ) -> ScheduledTask:
        """Create and return a task; a reversible material action on request."""
        ...

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
        """Update a task's fields and return the refreshed task."""
        ...

    def delete_task(self, task_id: str) -> None:
        """Delete a task by its id; a reversible material action on request."""
        ...

    def enable_task(self, task_id: str) -> ScheduledTask:
        """Enable a task and return the refreshed task."""
        ...

    def disable_task(self, task_id: str) -> ScheduledTask:
        """Disable a task and return the refreshed task."""
        ...

    def due_tasks(self) -> tuple[ScheduledTask, ...]:
        """Return all enabled tasks whose ``next_run`` is in the past, or () when none.

        An empty tuple is an honest "nothing due", not an error.
        """
        ...
