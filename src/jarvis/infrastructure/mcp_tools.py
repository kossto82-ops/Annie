"""MCP adapter (client direction): external server tools behind the ToolRegistry.

The delegation edges live on injectable seams (D7, D8). In the same spirit, this
module lets an external MCP server's tools become ordinary :class:`ToolSpec` entries
in Jarvis's own :class:`ToolRegistry` -- the client direction of Phase 4 part 2. The
registry still holds the gate: every MCP tool is declared at
:data:`PermissionLevel.EXTERNAL_ACTION`, so the policy demands explicit approval
before any externally-visible call runs, and every run is observed as a
:class:`ToolCall` like any other tool.

* :class:`McpTransport` -- the sync seam over a live MCP session. ``list_tools``
  discovers the server's tool shape and ``call`` executes one op. Predictable and
  fakeable, so the whole adapter is offline-testable without ``pydantic-ai``.
* :class:`PydanticAiMcpToolset` -- a transport backed by pydantic-ai's
  ``MCPToolset`` (imported lazily), bridging the async world to the sync seam.
* :class:`McpTool` -- a domain :class:`Tool` that forwards ``run`` to the transport.
* :func:`register_mcp_tools` -- turns a transport's discovered tools into registered
  ``ToolSpec`` entries (optionally namespaced) and returns the names it registered.
* :func:`build_mcp_toolset` / :func:`register_mcp_config` -- composition helpers that
  read a pydantic-ai ``mcpServers`` config file and wire one server.

The domain stays clean: this module never decides *whether* to act; it only makes an
approved MCP call possible and observable.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from jarvis.domain.enums.permission_level import PermissionLevel
from jarvis.domain.tools.tool_registry import ToolRegistry
from jarvis.domain.value_objects.tool_call_result import ToolCallResult
from jarvis.domain.value_objects.tool_spec import ToolSpec


@dataclass(frozen=True, slots=True, kw_only=True)
class McpToolInfo:
    """What an external MCP tool declares: name, purpose, and argument notes."""

    name: str
    description: str
    args: dict[str, str] = field(default_factory=dict[str, str])


class McpTransport(Protocol):
    """The sync seam over one live MCP session (offline-fakeable, D8).

    ``list_tools`` returns the tools the server exposes; ``call`` executes one by its
    wire name and returns its text output, raising on a server or protocol error so a
    failed call is honest, never a fabricated success.
    """

    label: str

    def list_tools(self) -> tuple[McpToolInfo, ...]: ...

    def call(self, name: str, arguments: Mapping[str, str]) -> str: ...


def _run_async(coro: Any) -> Any:
    """Drive an awaitable from the sync world, safely inside or outside a loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # A loop is already running on this thread (e.g. inside an async app): give the
    # MCP coroutine its own short-lived loop on a worker thread instead.
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def args_from_schema(input_schema: Mapping[str, Any] | None) -> dict[str, str]:
    """Map an MCP JSON-schema ``properties`` block to arg-name -> description."""
    properties = input_schema.get("properties") if input_schema is not None else None
    if not isinstance(properties, dict):
        return {}
    args: dict[str, str] = {}
    for name, meta in cast(dict[str, Any], properties).items():
        if isinstance(meta, dict):
            note = cast(dict[str, Any], meta).get("description")
            args[name] = str(note) if isinstance(note, str) and note.strip() else name
        else:
            args[name] = str(name)
    return args


def info_from_tool(tool: Any) -> McpToolInfo:
    """Adapt one pydantic-ai / mcp ``Tool`` object into a domain-safe shape."""
    name = str(tool.name)
    description = coerce_description(tool)
    input_schema = getattr(tool, "input_schema", None)
    schema: Mapping[str, Any] | None = (
        cast(Mapping[str, Any], input_schema) if isinstance(input_schema, Mapping) else None
    )
    return McpToolInfo(name=name, description=description, args=args_from_schema(schema))


def coerce_description(tool: Any) -> str:
    """A non-empty description from a tool (description, title, or name)."""
    description = getattr(tool, "description", None)
    if isinstance(description, str) and description.strip():
        return description
    title = getattr(tool, "title", None)
    if isinstance(title, str) and title.strip():
        return title
    return str(tool.name)


def extract_result_text(result: Any) -> str:
    """Flatten an MCP ``CallToolResult`` into plain text (or drop it entirely)."""
    text_parts: list[str] = []
    content = getattr(result, "content", None)
    if isinstance(content, (list, tuple)):
        for block in cast(list[Any], content):
            text = getattr(block, "text", None)
            if isinstance(text, str) and text:
                text_parts.append(text)
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        try:
            text_parts.append(json.dumps(structured, ensure_ascii=False))
        except (TypeError, ValueError):
            text_parts.append(str(structured))
    if getattr(result, "is_error", False):
        detail = "\n".join(text_parts).strip() or "the MCP server reported an error"
        raise McpCallError(detail)
    return "\n".join(text_parts)


class McpCallError(RuntimeError):
    """An MCP call reported an error; its message is the server's honest account."""


class PydanticAiMcpToolset:
    """An :class:`McpTransport` backed by a pydantic-ai ``MCPToolset``.

    ``pydantic-ai`` is imported lazily by the composition helpers, never here, so
    constructing the transport records nothing and connects nothing: the server is
    only reached when a tool actually runs (D8, offline by construction).
    """

    def __init__(self, toolset: Any, *, label: str) -> None:
        self._toolset = toolset
        self.label = label

    # -- McpTransport ---------------------------------------------------------

    def list_tools(self) -> tuple[McpToolInfo, ...]:
        tools = _run_async(self._toolset.list_tools())  # manages its own session
        return tuple(info_from_tool(tool) for tool in tools)

    def call(self, name: str, arguments: Mapping[str, str]) -> str:
        result = _run_async(
            self._toolset.direct_call_tool(name, dict(arguments))
        )  # manages its own session
        return extract_result_text(result)


class McpTool:
    """A domain :class:`Tool` that executes one external MCP tool through a transport."""

    def __init__(
        self,
        info: McpToolInfo,
        transport: McpTransport,
        *,
        name: str,
        permission: PermissionLevel = PermissionLevel.EXTERNAL_ACTION,
    ) -> None:
        self.spec = ToolSpec(
            name=name,
            description=info.description,
            args=dict(info.args),
            permission=permission,
        )
        self._transport = transport
        self._wire_name = info.name

    def run(self, arguments: dict[str, str]) -> ToolCallResult:
        try:
            value = self._transport.call(self._wire_name, arguments)
        except Exception as exc:  # noqa: BLE001 - a failing external tool stays honest
            return ToolCallResult(value="", ok=False, error=str(exc))
        return ToolCallResult(value=value, ok=True)


def register_mcp_tools(
    registry: ToolRegistry,
    transport: McpTransport,
    *,
    namespace: str = "",
    permission: PermissionLevel = PermissionLevel.EXTERNAL_ACTION,
) -> tuple[str, ...]:
    """Discover ``transport``'s tools and register each as an :class:`McpTool`.

    A non-empty ``namespace`` (e.g. the server name) yields ``<namespace>.<name>``
    registry names, so several MCP servers and Jarvis's local tools coexist without
    colliding. Returns the names registered.
    """
    names: list[str] = []
    for info in transport.list_tools():
        spec_name = f"{namespace}.{info.name}" if namespace else info.name
        registry.register(
            McpTool(info, transport, name=spec_name, permission=permission)
        )
        names.append(spec_name)
    return tuple(names)


def build_mcp_toolset(config_path: str | os.PathLike[str]) -> McpTransport | None:
    """Build a transport for a pydantic-ai ``mcpServers`` config file, or ``None``.

    ``None`` when ``pydantic-ai`` is not installed (offline Jarvis keeps working) or
    the config exposes no server. Building is lazy: nothing connects until a tool
    actually runs. A malformed config raises so the misconfiguration is not silent.
    """
    if importlib.util.find_spec("pydantic_ai") is None:
        return None
    try:
        from pydantic_ai.mcp import load_mcp_toolsets
    except ImportError:
        return None

    toolsets = load_mcp_toolsets(os.fspath(config_path))
    if not toolsets:
        return None
    first = toolsets[0]
    label = str(getattr(first, "prefix", "") or getattr(first, "label", "mcp"))
    wrapped = getattr(first, "wrapped", first)
    return PydanticAiMcpToolset(wrapped, label=label)


def register_mcp_config(
    registry: ToolRegistry,
    config_path: str | os.PathLike[str],
    *,
    namespace: str = "",
    permission: PermissionLevel = PermissionLevel.EXTERNAL_ACTION,
) -> tuple[str, ...]:
    """Register every tool of one configured MCP server into ``registry``.

    Uses the server label as the namespace unless one is given, so tools land as
    ``<server>.<tool>``. Returns the names registered; ``()`` when the config is
    absent or ``pydantic-ai`` is not installed.
    """
    transport = build_mcp_toolset(config_path)
    if transport is None:
        return ()
    return register_mcp_tools(
        registry,
        transport,
        namespace=namespace or transport.label,
        permission=permission,
    )