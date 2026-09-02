"""ToolRegistry: a domain service that keeps and runs tools (Vision §34).

The registry is where a tool call travels the loop of 06_TOOLS_AGENCY:
``selection -> permission -> execution -> observation -> evaluation``. It holds the
Tools by name, applies a :class:`ToolPolicy` gate before any run, executes through
the Tool, and records every :class:`ToolCall` in an observable trace so the core can
reason over *what it did* and *how it went*.

It never decides *whether* Jarvis should act: it only makes an approved call
possible and observable. Approval for risky levels is the caller's explicit step --
the registry refuses without it, it does not ask for it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from time import perf_counter

from jarvis.domain.tools.tool import Tool
from jarvis.domain.tools.tool_policy import ToolPolicy
from jarvis.domain.value_objects.tool_call import ToolCall
from jarvis.domain.value_objects.tool_call_result import ToolCallResult
from jarvis.domain.value_objects.tool_spec import ToolSpec

ToolObserver = Callable[[ToolCall], None]


class ToolRegistry:
    """An approved-only, observable registry of runnable tools."""

    def __init__(
        self,
        *,
        policy: ToolPolicy | None = None,
        observer: ToolObserver | None = None,
    ) -> None:
        self._policy = policy or ToolPolicy()
        self._observer = observer
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register ``tool`` by its spec name, replacing any same-named tool."""
        self._tools[tool.spec.name] = tool

    def unregister(self, name: str) -> None:
        """Remove the tool named ``name``; a no-op when it is not registered."""
        self._tools.pop(name, None)

    def tool_names(self) -> tuple[str, ...]:
        """Every registered tool name, in registration order."""
        return tuple(self._tools.keys())

    def spec(self, name: str) -> ToolSpec | None:
        """The declaration of tool ``name``, or None when it is not registered."""
        tool = self._tools.get(name)
        return tool.spec if tool is not None else None

    def run(
        self,
        name: str,
        arguments: Mapping[str, str],
        *,
        approved: bool = False,
    ) -> ToolCallResult:
        """Run tool ``name`` under the policy gate and record the call.

        ``approved`` must be True for a call at a permission level requiring
        approval; otherwise the registry refuses before execution. The resulting
        :class:`ToolCall` (with timing and outcome) is passed to the observer so the
        core can evaluate the act afterwards.
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolCallResult(ok=False, error=f"unknown tool: {name}")

        verdict = self._policy.approve(tool.spec.permission)
        if not verdict.allowed and not approved:
            return ToolCallResult(ok=False, error=verdict.reason)

        started = perf_counter()
        try:
            result = tool.run(dict(arguments))
            value: str = result.value
            error: str = "" if result.ok else result.error
        except Exception as exc:  # noqa: BLE001 - a tool failing must not cross
            value = ""
            error = str(exc)

        call = ToolCall(
            tool=name,
            arguments=dict(arguments),
            permission=tool.spec.permission,
            duration_seconds=perf_counter() - started,
            ok=not error,
            error=error,
        )
        if self._observer is not None:
            self._observer(call)

        if not error:
            return ToolCallResult(value=value, ok=True)
        return ToolCallResult(ok=False, error=error)