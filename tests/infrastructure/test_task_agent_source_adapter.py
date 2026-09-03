"""Tests for the in-Jarvis task agent adapter (ToolRegistryTaskAgent).

Covers the `ToolRegistryTaskAgent` running a decided multi-line tool-call task
through Jarvis's own `ToolRegistry`, its honest failure narration, and the
`build_default_task_agent` factory's config opt-in. Everything is offline and
deterministic (D8): `FileSystemTool` is driven with an injected `io`, and the
factory returns `None` without directory configuration.
"""

from __future__ import annotations

import pytest

from jarvis.domain.tools.tool_registry import ToolRegistry
from jarvis.infrastructure.echo_tool import EchoTool
from jarvis.infrastructure.filesystem_tool import FileSystemTool
from jarvis.infrastructure.task_agent_source import (
    ToolRegistryTaskAgent,
    build_default_task_agent,
)


def _registry_with_fake_io(record: dict[str, list[tuple[str, str]]]) -> ToolRegistry:
    """A registry holding a FileSystemTool whose io records writes in-memory."""

    def fake_io(operation: str, path: str, content: str, _: str = "") -> str:
        if operation == "read":
            entries = record.get(path, [])
            return entries[-1][1] if entries else ""
        record.setdefault(path, []).append((operation, content))
        return ""

    registry = ToolRegistry()
    registry.register(FileSystemTool("/tmp/root", io=fake_io))
    registry.register(EchoTool())
    return registry


class TestToolRegistryTaskAgent:
    def test_runs_a_multi_line_task_through_the_registry(self) -> None:
        record: dict[str, list[tuple[str, str]]] = {}
        agent = ToolRegistryTaskAgent(_registry_with_fake_io(record))
        result = agent.run_task(
            'filesystem operation=write path="notes.txt" '
            'content="review the doc"\necho text=finished'
        )
        assert result.success
        assert "filesystem ok" in result.summary
        assert "echo ok" in result.summary
        assert record["notes.txt"] == [("write", "review the doc")]

    def test_narrates_an_unknown_tool_honestly(self) -> None:
        agent = ToolRegistryTaskAgent(_registry_with_fake_io({}))
        result = agent.run_task("does_not_exist write x y")
        assert not result.success
        assert "unknown tool: does_not_exist" in result.summary

    def test_narrates_a_malformed_argument_honestly(self) -> None:
        agent = ToolRegistryTaskAgent(_registry_with_fake_io({}))
        result = agent.run_task("echo justtextwithoutarg")
        assert not result.success
        assert "malformed argument" in result.summary

    def test_blank_task_is_not_claimed_as_success(self) -> None:
        agent = ToolRegistryTaskAgent(_registry_with_fake_io({}))
        result = agent.run_task("   \n  \n")
        assert not result.success
        assert "no tool calls ran" in result.summary

    def test_ends_with_failed_lines_reported(self) -> None:
        agent = ToolRegistryTaskAgent(_registry_with_fake_io({}))
        result = agent.run_task("echo ok\nbogus arg=x")
        assert not result.success
        assert "echo ok" in result.summary
        assert "unknown tool: bogus" in result.summary

    def test_echo_tool_executes(self) -> None:
        agent = ToolRegistryTaskAgent(_registry_with_fake_io({}))
        result = agent.run_task("echo text=hello")
        assert result.success
        assert "echo ok" in result.summary

    def test_satisfies_the_task_agent_protocol(self) -> None:
        from jarvis.domain.retrieval.task_agent_source import TaskAgent

        agent = ToolRegistryTaskAgent(_registry_with_fake_io({}))
        assert isinstance(agent, TaskAgent)


class TestBuildDefaultTaskAgent:
    def test_returns_none_without_directory_configuration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("JARVIS_AGENT_ROOT", raising=False)
        assert build_default_task_agent() is None

    def test_builds_a_wired_offline_agent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("JARVIS_AGENT_ROOT", "/tmp/root")
        agent = build_default_task_agent()
        assert agent is not None
        assert isinstance(agent, ToolRegistryTaskAgent)
        result = agent.run_task("echo text=hi")
        assert result.success
