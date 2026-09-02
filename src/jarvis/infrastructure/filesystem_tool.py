"""FileSystemTool: read/write access to local files (Vision §34, 06_TOOLS_AGENCY).

The filesystem client at the edge of Jarvis: it lets Jarvis read and write files the
way the Internet capability lets it fetch documents -- a *retrieval/act* tool, never
a decision-maker. The actual disk access is an injectable ``io`` callable so offline
tests run deterministically without touching disk (D8). ``root`` bounds where the
tool may operate, so a destructive (WRITE) act can never escape its sandbox.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from jarvis.domain.enums.permission_level import PermissionLevel
from jarvis.domain.value_objects.tool_call_result import ToolCallResult
from jarvis.domain.value_objects.tool_spec import ToolSpec


class FileSystemTool:
    """Reads and writes text files under a bounded ``root`` directory."""

    spec = ToolSpec(
        name="filesystem",
        description="read and write local text files under a bounded directory",
        args={
            "operation": "read or write",
            "path": "path relative to the tool root",
            "content": "content to write (write only)",
        },
        permission=PermissionLevel.WRITE,
    )

    def __init__(
        self,
        root: str | Path,
        io: Callable[[str, str, str, str], str] | None = None,
    ) -> None:
        """Bind the tool to a sandbox ``root`` with an injectable ``io`` driver.

        ``io(operation, path, content, "")`` returns the file text for ``read`` or
        the empty string for a successful ``write``. Defaults to real disk access
        through :func:`pathlib`; injecting a fake keeps tests offline (D8).
        """
        self._root = Path(root).resolve()
        self._io = io or self._default_io

    def _default_io(self, operation: str, path: str, content: str, _: str) -> str:
        resolved = (self._root / path).resolve()
        if not resolved.is_relative_to(self._root):
            raise ValueError("path escapes the tool sandbox")
        if operation == "read":
            return resolved.read_text(encoding="utf-8")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return ""

    def run(self, arguments: dict[str, str]) -> ToolCallResult:
        operation = arguments.get("operation", "read")
        path = arguments.get("path", "")
        if not path:
            return ToolCallResult(ok=False, error="filesystem requires a path")
        try:
            value = self._io(operation, path, arguments.get("content", ""), "")
        except Exception as exc:  # noqa: BLE001 - a tool failing must not cross
            return ToolCallResult(ok=False, error=str(exc))
        return ToolCallResult(value=value, ok=True)