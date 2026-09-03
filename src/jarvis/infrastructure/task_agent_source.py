"""ToolRegistryTaskAgent: a TaskAgent backed by Jarvis's own ToolRegistry.

Delegation (revised D1) hands a *material* task to an edge agent -- never
cognition. The most autonomous edge that stays *inside Jarvis* is its own
:class:`ToolRegistry` (Vision §34, 06_TOOLS_AGENCY): an approved-only, observable
runner of tools. This adapter makes that registry appear as a :class:`TaskAgent`
so a surface can hand it a decided task and get a plain :class:`TaskResult`.

Because the agent never reasons (D6), a task arrives in a small deterministic
script of tool-calls, one per line, quote-aware ``key=value`` arguments:

    filesystem write path="notes.txt" content="review the doc"
    echo text=done

Each line is ``tool_name key=value ...``; a value containing spaces is wrapped in
double quotes. The agent resolves the tool against the registry, executes it
through the policy gate (``approved=True`` -- the decision to delegate and this
exact task was already approved upstream by the controlled-autonomy policy), and
composes one :class:`TaskResult` narrating what it did and how it went. Nothing
here decides *whether* to act; it only makes an approved act happen and observable.

Tools carry their own sandboxes and injectable transports (FileSystemTool's
``root``/``io``, EchoTool), so the agent is fully offline-testable (D8) and never
depends on credentials or a remote server. A destructive or externally-visible act
still requires the tool's spec to permit it and the agent's upstream approval.
"""

from __future__ import annotations

import shlex

from jarvis.domain.tools.tool_registry import ToolRegistry
from jarvis.domain.value_objects.task_result import TaskResult


class ToolRegistryTaskAgent:
    """Runs a decided multi-line task script through a :class:`ToolRegistry`.

    Each non-empty line is a tool-call ``name key=value ...`` (quote-aware).
    Unknown tool names, unparseable lines, or tools the policy refuses even under
    approval yield a truthful failed :class:`TaskResult` -- never a fabricated
    success. A task that performs no successful tool call is not a success.
    """

    def __init__(self, registry: ToolRegistry, *, approved: bool = True) -> None:
        self._registry = registry
        self._approved = approved

    # -- TaskAgent ------------------------------------------------------------

    def run_task(self, task: str) -> TaskResult:
        """Execute ``task`` line-by-line and narrate the outcome."""
        summary_lines: list[str] = []
        failures: list[str] = []
        for raw_line in task.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            tokens, error = self._split(line)
            if error is not None:
                failures.append(error)
                continue
            tool_name = tokens[0]
            if self._registry.spec(tool_name) is None:
                failures.append(f"unknown tool: {tool_name}")
                continue
            arguments, error = self._arguments(tokens[1:], line)
            if error is not None:
                failures.append(error)
                continue
            result = self._registry.run(tool_name, arguments, approved=self._approved)
            if result.ok:
                summary_lines.append(f"{tool_name} ok")
            else:
                failures.append(f"{tool_name}: {result.error}")
        if failures:
            usage = "; ".join(summary_lines) if summary_lines else "no tool calls ran"
            return TaskResult(
                task=task,
                summary=usage + " | failed: " + ", ".join(failures),
                success=False,
            )
        if not summary_lines:
            return TaskResult(task=task, summary="no tool calls ran", success=False)
        return TaskResult(task=task, summary="; ".join(summary_lines), success=True)

    # -- Parsing --------------------------------------------------------------

    @staticmethod
    def _split(line: str) -> tuple[list[str], str | None]:
        """Split a line into quote-aware tokens; an error when it is unparseable."""
        try:
            tokens = shlex.split(line, posix=True)
        except ValueError as exc:
            return [], f"cannot parse {line!r}: {exc}"
        if not tokens:
            return [], "empty line"
        return tokens, None

    @staticmethod
    def _arguments(tokens: list[str], line: str) -> tuple[dict[str, str], str | None]:
        """Turn ``key=value`` tokens into an argument dict, one ``=`` per token."""
        arguments: dict[str, str] = {}
        for token in tokens:
            if "=" not in token:
                return {}, f"malformed argument {token!r} in {line!r}"
            key, _, value = token.partition("=")
            if not key:
                return {}, f"malformed argument {token!r} in {line!r}"
            arguments[key] = value
        return arguments, None


def build_default_task_agent() -> ToolRegistryTaskAgent | None:
    """Build the default in-Jarvis task agent, or ``None`` when not configured.

    Wires a :class:`ToolRegistry` with a sandboxed :class:`FileSystemTool` under
    the ``JARVIS_AGENT_ROOT`` directory (defaulting to the current directory when
    set) plus the harmless :class:`EchoTool`, and wraps it as a
    :class:`ToolRegistryTaskAgent`. ``None`` when directory configuration is
    missing, so a Jarvis built from this keeps working offline.
    """
    import os

    from jarvis.infrastructure.echo_tool import EchoTool
    from jarvis.infrastructure.filesystem_tool import FileSystemTool

    root = os.environ.get("JARVIS_AGENT_ROOT")
    if not root:
        return None
    registry = ToolRegistry()
    registry.register(FileSystemTool(root))
    registry.register(EchoTool())
    return ToolRegistryTaskAgent(registry)
