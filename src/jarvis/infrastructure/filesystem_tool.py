"""FileSystemTool: read/write access to local files (Vision §34, 06_TOOLS_AGENCY).

The filesystem client at the edge of Jarvis: it lets Jarvis read, write and list
files the way the Internet capability lets it fetch documents -- a *retrieval/act*
tool, never a decision-maker. The actual disk access is an injectable ``io``
callable so offline tests run deterministically without touching disk (D8). ``root``
bounds where the tool may operate, so a destructive (WRITE) act can never escape its
sandbox.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from jarvis.domain.enums.permission_level import PermissionLevel
from jarvis.domain.value_objects.tool_call_result import ToolCallResult
from jarvis.domain.value_objects.tool_spec import ToolSpec


class FileSystemTool:
    """Reads, writes and lists text files under a bounded ``root`` directory."""

    def __init__(
        self,
        root: str | Path,
        *,
        name: str = "filesystem",
        io: Callable[[str, str, str, str], str] | None = None,
    ) -> None:
        """Bind the tool to a sandbox ``root`` with an injectable ``io`` driver.

        ``io(operation, path, content, "")`` returns the file text for ``read``,
        the empty string for a successful ``write``, and a newline-joined listing
        of relative paths (directories marked with a trailing ``/``) for ``list``.
        ``name`` gives the tool a unique registry id (e.g. ``project:myapp``) when
        several roots are wired. Defaults to real disk access through
        :func:`pathlib`; injecting a fake keeps tests offline (D8).
        """
        self.spec = ToolSpec(
            name=name,
            description="read, write and list local text files under a bounded directory",
            args={
                "operation": "read, write or list",
                "path": "path relative to the tool root",
                "content": "content to write (write only)",
            },
            permission=PermissionLevel.WRITE,
        )
        self._root = Path(root).resolve()
        self._io = io or self._default_io

    def _default_io(self, operation: str, path: str, content: str, _: str) -> str:
        if operation == "list":
            return self._list_tree()
        resolved = (self._root / path).resolve()
        if not resolved.is_relative_to(self._root):
            raise ValueError("path escapes the tool sandbox")
        if operation == "read":
            return resolved.read_text(encoding="utf-8")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return ""

    def _list_tree(self) -> str:
        """Relative paths under ``root``, sorted, directories marked with a '/'."""
        lines: list[str] = []
        for child in sorted(self._root.rglob("*"), key=lambda p: p.as_posix()):
            lines.append(
                child.relative_to(self._root).as_posix()
                + ("/" if child.is_dir() else "")
            )
        return "\n".join(lines)

    def run(self, arguments: dict[str, str]) -> ToolCallResult:
        operation = arguments.get("operation", "read")
        path = arguments.get("path", "")
        if operation not in ("read", "write", "list"):
            # A typo ("Read", "append") must never silently become a write.
            return ToolCallResult(
                ok=False,
                error=(
                    "filesystem requires operation 'read', 'write' or 'list', "
                    f"got {operation!r}"
                ),
            )
        if operation != "list" and not path:
            return ToolCallResult(ok=False, error="filesystem requires a path")
        try:
            value = self._io(operation, path, arguments.get("content", ""), "")
        except Exception as exc:  # noqa: BLE001 - a tool failing must not cross
            return ToolCallResult(ok=False, error=str(exc))
        return ToolCallResult(value=value, ok=True)