"""Filesystem and echo tool adapters, tested fully offline (D8).

The filesystem adapter takes an injectable ``io`` driver, so every test here runs
with no real disk access (Vision §38): reads, writes, sandbox escape prevention, and
argument validation are all exercised directly.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.domain.enums.permission_level import PermissionLevel
from jarvis.infrastructure.echo_tool import EchoTool
from jarvis.infrastructure.filesystem_tool import FileSystemTool


class TestEchoTool:
    def test_echoes_the_text_argument(self) -> None:
        result = EchoTool().run({"text": "hello"})
        assert result.ok is True
        assert result.value == "hello"

    def test_empty_text_echoes_empty(self) -> None:
        assert EchoTool().run({}).value == ""

    def test_declares_execute_permission(self) -> None:
        assert EchoTool.spec.permission is PermissionLevel.EXECUTE


class TestFileSystemTool:
    def test_reads_through_the_injected_io(self) -> None:
        calls: list[tuple[str, str]] = []

        def io(operation: str, path: str, content: str, _: str) -> str:
            calls.append((operation, path))
            return "file body"

        tool = FileSystemTool(root="C:\\work", io=io)
        result = tool.run({"operation": "read", "path": "a.txt"})
        assert result.ok is True
        assert result.value == "file body"
        assert calls == [("read", "a.txt")]

    def test_writes_through_the_injected_io(self) -> None:
        seen: dict[str, str] = {}

        def io(operation: str, path: str, content: str, _: str) -> str:
            if operation == "write":
                seen[path] = content
            return ""

        tool = FileSystemTool(root="C:\\work", io=io)
        result = tool.run(
            {"operation": "write", "path": "b.txt", "content": "new"}
        )
        assert result.ok is True
        assert seen == {"b.txt": "new"}

    def test_missing_path_fails_honestly(self) -> None:
        tool = FileSystemTool(root="C:\\work", io=self._null_io)
        result = tool.run({})
        assert result.ok is False
        assert "requires a path" in result.error

    def test_an_unknown_operation_never_writes(self) -> None:
        wrote: list[str] = []

        def io(operation: str, path: str, content: str, _: str) -> str:
            wrote.append(operation)
            return ""

        tool = FileSystemTool(root="C:\\work", io=io)
        result = tool.run({"operation": "Read", "path": "a.txt", "content": "boom"})
        assert result.ok is False
        assert "'read' or 'write'" in result.error
        assert wrote == [], "a typo must never silently become a write"

    @staticmethod
    def _null_io(operation: str, path: str, content: str, _: str) -> str:
        return ""

    def test_io_exception_is_reported_as_result_error(self) -> None:
        def io(operation: str, path: str, content: str, _: str) -> str:
            raise FileNotFoundError("missing")

        tool = FileSystemTool(root="C:\\work", io=io)
        result = tool.run({"operation": "read", "path": "gone.txt"})
        assert result.ok is False
        assert "missing" in result.error

    def test_default_io_prevents_sandbox_escape(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        tool = FileSystemTool(root=root)
        result = tool.run(
            {
                "operation": "read",
                "path": "..\\..\\evil.txt",
            }
        )
        assert result.ok is False
        assert "escapes the tool sandbox" in result.error

    def test_reads_real_files_with_the_default_io(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        target = root / "hello.txt"
        target.write_text("hi", encoding="utf-8")
        tool = FileSystemTool(root=root)
        result = tool.run({"operation": "read", "path": "hello.txt"})
        assert result.ok is True
        assert result.value == "hi"