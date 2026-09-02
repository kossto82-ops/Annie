"""Tool: the protocol a runnable tool satisfies (Vision §34).

A Tool is an ability to *act*, not to think. Executing one returns a
:class:`ToolCallResult`; deciding *whether* to run it, and *what to make of its
outcome*, stays in the cognitive core. Tools carry no cognition of their own --
only their declared :class:`ToolSpec` (what, arguments, permission) and a callable
``run``. Adapters live in ``jarvis.infrastructure`` (D7); the domain knows the shape.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jarvis.domain.value_objects.tool_call_result import ToolCallResult
from jarvis.domain.value_objects.tool_spec import ToolSpec


@runtime_checkable
class Tool(Protocol):
    """A runnable extension of Jarvis's ability to act in the world."""

    spec: ToolSpec

    def run(self, arguments: dict[str, str]) -> ToolCallResult:
        """Execute the tool with ``arguments`` and return its outcome.

        The implementation may raise on failure; the registry converts that into a
        failed :class:`ToolCallResult` for the trace so a future model can evaluate
        the outcome without an exception crossing the cognitive boundary.
        """
        ...