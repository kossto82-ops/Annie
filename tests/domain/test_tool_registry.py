"""ToolRegistry: the domain service that runs tools (Vision §34, 06_TOOLS_AGENCY).

Covers the selection->permission->execution->observation loop: a valid tool runs
and records a ToolCall, an unknown tool fails honestly, policy gates external/
destructive calls behind approval, arguments survive verbatim, and failures stay in
the result rather than crossing to the caller. All deterministic and offline (D8).
"""

from __future__ import annotations

import pytest

from jarvis.domain.enums.permission_level import PermissionLevel
from jarvis.domain.tools.tool_policy import ToolPolicy
from jarvis.domain.tools.tool_registry import ToolRegistry
from jarvis.domain.value_objects.tool_call import ToolCall
from jarvis.domain.value_objects.tool_call_result import ToolCallResult
from jarvis.domain.value_objects.tool_spec import ToolSpec


class EchoTool:
    """A minimal runnable tool for tests."""

    spec = ToolSpec(
        name="echo",
        description="echo the given text back",
        args={"text": "the text to echo"},
        permission=PermissionLevel.EXECUTE,
    )

    def run(self, arguments: dict[str, str]) -> ToolCallResult:
        return ToolCallResult(value=arguments.get("text", ""), ok=True)


class ExternalPinger:
    """A fake external tool: it pings a remote host and receives a pong."""

    spec = ToolSpec(
        name="ping",
        description="ping a remote host",
        permission=PermissionLevel.EXTERNAL_ACTION,
    )

    def run(self, arguments: dict[str, str]) -> ToolCallResult:
        return ToolCallResult(value="pong", ok=True)


class BoomTool:
    """A tool that always raises, to test failure stays inside the result."""

    spec = ToolSpec(name="boom", description="always explodes")

    def run(self, arguments: dict[str, str]) -> ToolCallResult:
        raise RuntimeError("kapow")


class TestToolSpec:
    def test_valid_spec_defaults_to_read(self) -> None:
        spec = ToolSpec(name="peek", description="look without touching")
        assert spec.name == "peek"
        assert spec.permission is PermissionLevel.READ
        assert spec.requires_approval is False

    def test_rejects_blank_name(self) -> None:
        with pytest.raises(ValueError):
            ToolSpec(name="  ", description="x")

    def test_external_action_requires_approval(self) -> None:
        spec = ToolSpec(
            name="ping",
            description="reach out",
            permission=PermissionLevel.EXTERNAL_ACTION,
        )
        assert spec.requires_approval is True

    def test_is_immutable(self) -> None:
        spec = ToolSpec(name="peek", description="look")
        with pytest.raises(AttributeError):
            spec.name = "other"  # type: ignore[misc]


class TestPolicy:
    def test_read_write_execute_are_allowed(self) -> None:
        policy = ToolPolicy()
        for level in (
            PermissionLevel.READ,
            PermissionLevel.WRITE,
            PermissionLevel.EXECUTE,
        ):
            assert policy.approve(level).allowed is True

    def test_external_and_destructive_require_approval(self) -> None:
        policy = ToolPolicy()
        for level in (PermissionLevel.EXTERNAL_ACTION, PermissionLevel.DESTRUCTIVE):
            decision = policy.approve(level)
            assert decision.allowed is False
            assert "requires explicit approval" in decision.reason


class TestRegistry:
    def test_runs_a_registered_tool_and_records_the_call(self) -> None:
        calls: list[ToolCall] = []
        registry = ToolRegistry(observer=calls.append)  # type: ignore[arg-type]
        registry.register(EchoTool())
        result = registry.run("echo", {"text": "hello"})
        assert result.ok is True
        assert result.value == "hello"
        assert calls, "every call must be recorded for the observation step"
        assert calls[0].tool == "echo"
        assert calls[0].arguments == {"text": "hello"}
        assert calls[0].ok is True

    def test_unknown_tool_fails_honestly_without_a_record(self) -> None:
        calls: list[ToolCall] = []
        registry = ToolRegistry(observer=calls.append)  # type: ignore[arg-type]
        result = registry.run("nope", {})
        assert result.ok is False
        assert "unknown tool" in result.error
        assert calls == []

    def test_missing_approval_refuses_an_external_tool(self) -> None:
        calls: list[ToolCall] = []
        registry = ToolRegistry(observer=calls.append)  # type: ignore[arg-type]
        registry.register(ExternalPinger())
        result = registry.run("ping", {"host": "example.com"}, approved=False)
        assert result.ok is False
        assert "requires explicit approval" in result.error
        assert calls == [], "a refused call never executes, so nothing is recorded"

    def test_approval_allows_an_external_tool_and_records_it(self) -> None:
        calls: list[ToolCall] = []
        registry = ToolRegistry(observer=calls.append)  # type: ignore[arg-type]
        registry.register(ExternalPinger())
        result = registry.run("ping", {"host": "example.com"}, approved=True)
        assert result.ok is True
        assert result.value == "pong"
        assert calls[0].permission is PermissionLevel.EXTERNAL_ACTION

    def test_a_raising_tool_is_recorded_as_failed_result(self) -> None:
        calls: list[ToolCall] = []
        registry = ToolRegistry(observer=calls.append)  # type: ignore[arg-type]
        registry.register(BoomTool())
        result = registry.run("boom", {})
        assert result.ok is False
        assert "kapow" in result.error
        assert calls[0].ok is False
        assert "kapow" in calls[0].error

    def test_unregister_is_a_noop_for_unknown(self) -> None:
        registry = ToolRegistry()
        registry.unregister("ghost")
        assert registry.tool_names() == ()

    def test_spec_exposes_the_declaration(self) -> None:
        registry = ToolRegistry()
        registry.register(EchoTool())
        spec = registry.spec("echo")
        assert spec is not None
        assert spec.name == "echo"
        assert registry.spec("missing") is None

    def test_tool_names_keep_registration_order(self) -> None:
        registry = ToolRegistry()
        registry.register(EchoTool())
        assert registry.tool_names() == ("echo",)