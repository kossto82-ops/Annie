"""Tests for the MCP adapter (client direction): external tools into ToolRegistry.

Everything here is offline (D8): the transport is a fake session, the
pydantic-ai-backed toolset is driven with a fake async toolset, and the config
composition is exercised lazily (construction never connects). The tools land as
ordinary ``EXTERNAL_ACTION`` specs behind the registry's approval gate, matching
how any other tool runs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from jarvis.domain.enums.permission_level import PermissionLevel
from jarvis.domain.tools.tool_registry import ToolRegistry
from jarvis.infrastructure.mcp_tools import (
    McpCallError,
    McpTool,
    McpToolInfo,
    PydanticAiMcpToolset,
    args_from_schema,
    build_mcp_toolset,
    coerce_description,
    extract_result_text,
    info_from_tool,
    register_mcp_config,
    register_mcp_tools,
)
from jarvis.infrastructure.task_agent_source import build_sandboxed_registry


class _FakeTransport:
    """An :class:`McpTransport` fake: canned tools, recorded calls."""

    def __init__(self, tools: tuple[McpToolInfo, ...]) -> None:
        self.label = "repo"
        self._tools = tools
        self.calls: list[tuple[str, dict[str, str]]] = []

    def list_tools(self) -> tuple[McpToolInfo, ...]:
        return self._tools

    def call(self, name: str, arguments: Mapping[str, str]) -> str:
        self.calls.append((name, dict(arguments)))
        if name == "boom":
            raise RuntimeError("the external server refused")
        return f"{name}:{':'.join(f'{k}={v}' for k, v in arguments.items())}"


class _FakeTool:
    """A duck-typed mcp ``Tool`` for the mapping helpers (no mcp SDK import)."""

    def __init__(
        self, name: str, description: str | None, input_schema: object | None
    ) -> None:
        self.name = name
        self.title = name.title()
        self.description = description
        self.input_schema = input_schema


class _FakeText:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResult:
    def __init__(
        self,
        content: list[object],
        *,
        is_error: bool = False,
        structured_content: object | None = None,
    ) -> None:
        self.content = content
        self.is_error = is_error
        self.structured_content = structured_content


class TestToolsRegistration:
    def test_registers_tools_as_namespaced_external_specs(self) -> None:
        transport = _FakeTransport(
            (
                McpToolInfo(
                    name="status",
                    description="show repository status",
                    args={"path": "the path to show"},
                ),
                McpToolInfo(name="commit", description="commit the changes"),
            )
        )
        registry = ToolRegistry()
        names = register_mcp_tools(registry, transport, namespace="repo")

        assert names == ("repo.status", "repo.commit")
        spec = registry.spec("repo.status")
        assert spec is not None
        assert spec.description == "show repository status"
        assert spec.args == {"path": "the path to show"}
        assert spec.permission is PermissionLevel.EXTERNAL_ACTION
        assert spec.requires_approval

    def test_a_tool_runs_through_the_transport_and_records_the_call(self) -> None:
        transport = _FakeTransport(
            (McpToolInfo(name="status", description="show repo status"),)
        )
        registry = ToolRegistry()
        register_mcp_tools(registry, transport, namespace="repo")

        result = registry.run("repo.status", {"path": "src"}, approved=True)
        assert result.ok
        assert result.value == "status:path=src"
        assert transport.calls == [("status", {"path": "src"})]

    def test_registry_gate_refuses_an_unapproved_external_call(self) -> None:
        transport = _FakeTransport(
            (McpToolInfo(name="commit", description="commit the changes"),)
        )
        registry = ToolRegistry()
        register_mcp_tools(registry, transport, namespace="repo")

        result = registry.run("repo.commit", {})
        assert not result.ok
        assert "requires explicit approval" in result.error

    def test_an_explicitly_approved_external_call_runs(self) -> None:
        transport = _FakeTransport(
            (McpToolInfo(name="commit", description="commit the changes"),)
        )
        registry = ToolRegistry()
        register_mcp_tools(registry, transport, namespace="repo")

        result = registry.run("repo.commit", {}, approved=True)
        assert result.ok

    def test_a_failing_external_call_is_an_honest_failure(self) -> None:
        transport = _FakeTransport(
            (McpToolInfo(name="boom", description="always fails"),)
        )
        registry = ToolRegistry()
        register_mcp_tools(registry, transport, namespace="repo")

        result = registry.run("repo.boom", {}, approved=True)
        assert not result.ok
        assert "the external server refused" in result.error


class TestPydanticAiMcpToolset:
    def test_it_bridges_async_discovery_to_the_sync_seam(self) -> None:
        async def list_tools() -> list[_FakeTool]:
            return [
                _FakeTool(
                    "status",
                    "show repository status",
                    {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "the path"},
                            "depth": {"type": "number"},
                        },
                    },
                )
            ]

        wrapped = PydanticAiMcpToolset(_ToolsetSession(list_all=list_tools), label="repo")

        (info,) = wrapped.list_tools()
        assert info.name == "status"
        assert info.description == "show repository status"
        assert info.args == {"path": "the path", "depth": "depth"}

    def test_it_bridges_async_calls_and_extracts_text(self) -> None:
        async def call(name: str, arguments: dict[str, str]) -> _FakeResult:
            del name, arguments
            return _FakeResult([_FakeText("merged ok")])

        wrapped = PydanticAiMcpToolset(_ToolsetSession(call_fn=call), label="repo")
        text = wrapped.call("merge", {"branch": "main"})
        assert text == "merged ok"

    def test_an_error_result_raises_honestly(self) -> None:
        async def call(name: str, arguments: dict[str, str]) -> _FakeResult:
            del name, arguments
            return _FakeResult([_FakeText("no such branch")], is_error=True)

        wrapped = PydanticAiMcpToolset(_ToolsetSession(call_fn=call), label="repo")
        with pytest.raises(McpCallError, match="no such branch"):
            wrapped.call("merge", {})


class _ToolsetSession:
    """A fake pydantic-ai ``MCPToolset``: async ``list_tools`` / ``direct_call_tool``."""

    def __init__(
        self,
        list_all: Any | None = None,
        call_fn: Any | None = None,
    ) -> None:
        self._list_all = list_all
        self._call_fn = call_fn

    async def list_tools(self) -> list[_FakeTool]:
        if self._list_all is None:
            raise AssertionError("list_tools not expected")
        return await self._list_all()

    async def direct_call_tool(self, name: str, arguments: dict[str, str]) -> Any:
        if self._call_fn is None:
            raise AssertionError("direct_call_tool not expected")
        return await self._call_fn(name, arguments)


class TestMappingHelpers:
    def test_args_come_from_the_json_schema_properties(self) -> None:
        assert args_from_schema(
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "where to look"},
                    "all": {"type": "boolean"},
                    "nested": {"type": "object", "properties": {"x": {"type": "string"}}},
                },
            }
        ) == {"path": "where to look", "all": "all", "nested": "nested"}

    def test_missing_properties_mean_no_arguments(self) -> None:
        assert args_from_schema({}) == {}
        assert args_from_schema({"type": "object"}) == {}
        assert args_from_schema(None) == {}

    def test_description_falls_back_to_title_then_name(self) -> None:
        assert coerce_description(_FakeTool("x", None, None)) == "X"
        assert coerce_description(_FakeTool("x", "  ", None)) == "X"
        assert coerce_description(_FakeTool("x", "real purpose", None)) == "real purpose"

    def test_info_maps_an_mcp_tool_duck_type(self) -> None:
        info = info_from_tool(
            _FakeTool(
                "ls",
                "list files",
                {"type": "object", "properties": {"path": {"description": "dir"}}},
            )
        )
        assert info.name == "ls"
        assert info.description == "list files"
        assert info.args == {"path": "dir"}

    def test_result_text_joins_text_blocks_and_structured_content(self) -> None:
        assert extract_result_text(_FakeResult([_FakeText("one"), _FakeText("two")])) == (
            "one\ntwo"
        )
        assert "merged" in extract_result_text(
            _FakeResult([], structured_content={"merged": True})
        )
        assert extract_result_text(_FakeResult([])) == ""

    def test_an_error_result_raises_even_with_empty_content(self) -> None:
        with pytest.raises(McpCallError):
            extract_result_text(_FakeResult([], is_error=True))


class TestMcpTool:
    def test_satisfies_the_tool_protocol(self) -> None:
        from jarvis.domain.tools.tool import Tool

        tool = McpTool(
            McpToolInfo(name="status", description="show status"),
            _FakeTransport((McpToolInfo(name="status", description="show status"),)),
            name="status",
        )
        assert isinstance(tool, Tool)

    def test_it_runs_under_its_given_name(self) -> None:
        transport = _FakeTransport((McpToolInfo(name="status", description="s"),))
        tool = McpTool(
            McpToolInfo(name="status", description="s"),
            transport,
            name="repo.status",
        )
        result = tool.run({"path": "src"})
        assert result.ok
        assert result.value == "status:path=src"
        assert transport.calls == [("status", {"path": "src"})]


class TestBuildSandboxedRegistryWiring:
    def test_mcp_config_adds_namespaced_tools_alongside_local_tools(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: object
    ) -> None:
        import json
        from pathlib import Path

        import jarvis.infrastructure.mcp_tools as module

        config = Path(str(tmp_path)) / "mcp.json"
        config.write_text(
            json.dumps({"mcpServers": {"repo": {"url": "http://127.0.0.1:1/mcp"}}}),
            encoding="utf-8",
        )

        def fake_build(_path: str | Any) -> _FakeTransport:
            return _FakeTransport(
                (McpToolInfo(name="status", description="show repo status"),)
            )

        monkeypatch.setattr(module, "build_mcp_toolset", fake_build)
        monkeypatch.setenv("JARVIS_AGENT_ROOT", "/tmp/root")
        monkeypatch.setenv("JARVIS_MCP_CONFIG", str(config))

        registry = build_sandboxed_registry()
        assert registry is not None
        assert "echo" in registry.tool_names()
        assert "filesystem" in registry.tool_names()
        assert "repo.status" in registry.tool_names()
        assert registry.run("echo", {"text": "hi"}).ok

    def test_no_source_still_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("JARVIS_AGENT_ROOT", raising=False)
        monkeypatch.delenv("JARVIS_MCP_CONFIG", raising=False)
        assert build_sandboxed_registry() is None

    def test_a_broken_mcp_config_does_not_disable_local_tools(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: object
    ) -> None:
        from pathlib import Path

        config = Path(str(tmp_path)) / "mcp.json"
        config.write_text("not json", encoding="utf-8")
        monkeypatch.setenv("JARVIS_AGENT_ROOT", "/tmp/root")
        monkeypatch.setenv("JARVIS_MCP_CONFIG", str(config))

        registry = build_sandboxed_registry()
        assert registry is not None
        assert "echo" in registry.tool_names()
        assert registry.run("echo", {"text": "hi"}).ok


def _no_spec(_name: str) -> None:
    return None


class TestConfigComposition:
    def test_build_without_pydantic_ai_is_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import jarvis.infrastructure.mcp_tools as module

        monkeypatch.setattr(module.importlib.util, "find_spec", _no_spec)
        assert build_mcp_toolset("whatever.json") is None

    def test_register_mcp_config_returns_empty_without_pydantic_ai(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import jarvis.infrastructure.mcp_tools as module

        monkeypatch.setattr(module.importlib.util, "find_spec", _no_spec)
        assert register_mcp_config(ToolRegistry(), "whatever.json") == ()