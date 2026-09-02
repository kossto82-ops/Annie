"""Jarvis tool surface: registering, running, and observing tool acts (Vision §34).

Tools extend Jarvis's ability to *act*, never to think: registration only makes an
action possible, the policy gates risky calls, and every run is published as a
ToolCallRecorded event so the trace holds what Jarvis did. All offline and
deterministic (D8).
"""

from __future__ import annotations

from jarvis import Jarvis
from jarvis.domain.enums.permission_level import PermissionLevel
from jarvis.domain.events.tool_events import ToolCallRecorded
from jarvis.domain.value_objects.tool_call_result import ToolCallResult
from jarvis.domain.value_objects.tool_spec import ToolSpec
from jarvis.infrastructure.echo_tool import EchoTool


class _FakePinger:
    """An external (approval-gated) tool for integration tests."""

    spec = ToolSpec(
        name="ping",
        description="ping a remote host",
        permission=PermissionLevel.EXTERNAL_ACTION,
    )

    def run(self, arguments: dict[str, str]) -> ToolCallResult:
        return ToolCallResult(value="pong", ok=True)


class TestJarvisTools:
    def test_default_jarvis_has_no_tools(self) -> None:
        jarvis = Jarvis()
        assert jarvis.tool_names() == ()
        assert jarvis.tool_channels() == ()

    def test_registering_a_tool_exposes_it(self) -> None:
        jarvis = Jarvis()
        jarvis.register_tool(EchoTool())
        assert jarvis.tool_names() == ("echo",)
        assert jarvis.tool_spec("echo") is not None

    def test_running_an_unapproved_external_tool_is_refused(self) -> None:
        jarvis = Jarvis()
        jarvis.register_tool(_FakePinger())
        result = jarvis.run_tool("ping", {"host": "x"})
        assert result.ok is False
        assert "requires explicit approval" in result.error

    def test_running_an_approved_external_tool_works(self) -> None:
        jarvis = Jarvis()
        jarvis.register_tool(_FakePinger())
        result = jarvis.run_tool("ping", {"host": "x"}, approved=True)
        assert result.ok is True
        assert result.value == "pong"

    def test_every_tool_call_is_recorded_as_an_event(self) -> None:
        jarvis = Jarvis()
        recorded: list[ToolCallRecorded] = []

        def handler(event: object) -> None:
            if isinstance(event, ToolCallRecorded):
                recorded.append(event)

        jarvis.nervous_system.subscribe(ToolCallRecorded, handler)  # type: ignore[arg-type]
        jarvis.register_tool(EchoTool())
        jarvis.run_tool("echo", {"text": "hi"})
        assert recorded
        assert recorded[0].call.tool == "echo"
        assert recorded[0].call.ok is True
        assert recorded[0].call.arguments == {"text": "hi"}

    def test_a_refused_call_is_not_recorded(self) -> None:
        jarvis = Jarvis()
        recorded: list[ToolCallRecorded] = []

        def handler(event: object) -> None:
            if isinstance(event, ToolCallRecorded):
                recorded.append(event)

        jarvis.nervous_system.subscribe(ToolCallRecorded, handler)  # type: ignore[arg-type]
        jarvis.register_tool(_FakePinger())
        jarvis.run_tool("ping", {})
        assert recorded == []

    def test_tool_calls_land_in_the_trace_for_provenance(self) -> None:
        jarvis = Jarvis()
        recorded: list[ToolCallRecorded] = []

        def handler(event: object) -> None:
            if isinstance(event, ToolCallRecorded):
                recorded.append(event)

        jarvis.nervous_system.subscribe(ToolCallRecorded, handler)  # type: ignore[arg-type]
        jarvis.register_tool(EchoTool())
        jarvis.run_tool("echo", {"text": "hi"})
        assert recorded
        # The call is retrievable by its own correlation id (Vision §26):
        events = jarvis.trace(recorded[0].call.started_at.isoformat())
        assert any(isinstance(e, ToolCallRecorded) for e in events)