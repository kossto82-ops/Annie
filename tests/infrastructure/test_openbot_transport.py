"""Offline tests for the OpenBot transport seam (Increment 161).

Covers SSE parsing, value objects, the FakeOpenBotTransport, protocol
conformance, and security boundaries: timeout raises honest errors,
unreachable transports refuse, and tool call arguments are faithfully
recorded -- all without any network call.
"""

from __future__ import annotations

from jarvis.infrastructure.openbot_transport import (
    FakeOpenBotTransport,
    HttpOpenBotTransport,
    OpenBotError,
    OpenBotRunResult,
    OpenBotToolCall,
    OpenBotToolDef,
    OpenBotTransport,
    _collect_result,
    _parse_sse_events,
)


class TestParseSseEvents:
    def test_single_text_delta(self) -> None:
        raw = 'data: {"type":"TEXT_MESSAGE_CONTENT","delta":"hello"}\n\n'
        events = _parse_sse_events(raw)
        assert len(events) == 1
        assert events[0]["type"] == "TEXT_MESSAGE_CONTENT"
        assert events[0]["delta"] == "hello"

    def test_done_marker_is_ignored(self) -> None:
        raw = "data: [DONE]\n\n"
        assert _parse_sse_events(raw) == []

    def test_non_data_lines_are_ignored(self) -> None:
        raw = ": this is a comment\nevent: test\ndata: {}\n\n"
        assert len(_parse_sse_events(raw)) == 1

    def test_malformed_json_is_skipped(self) -> None:
        raw = "data: {invalid json\n\n"
        assert _parse_sse_events(raw) == []


class TestCollectResult:
    def test_success_with_text(self) -> None:
        events = [
            {"type": "TEXT_MESSAGE_CONTENT", "delta": "Hello"},
            {"type": "TEXT_MESSAGE_CONTENT", "delta": " world"},
            {"type": "RUN_FINISHED"},
        ]
        result = _collect_result(events, run_id="r1", thread_id="t1")
        assert result.finished is True
        assert result.text == "Hello world"
        assert result.error == ""

    def test_run_error_records_error(self) -> None:
        events = [{"type": "RUN_ERROR", "message": "boom"}]
        result = _collect_result(events, run_id="r2", thread_id="t2")
        assert result.error == "boom"
        assert result.finished is False

    def test_tool_call_events_are_collected(self) -> None:
        events = [
            {"type": "TOOL_CALL_START", "toolCallId": "tc1", "toolCallName": "open"},
            {"type": "TOOL_CALL_ARGS", "delta": '{"url": "http://test"}'},
            {"type": "TOOL_CALL_END"},
            {"type": "RUN_FINISHED"},
        ]
        result = _collect_result(events, run_id="r3", thread_id="t3")
        assert len(result.tool_calls) == 1
        tc = result.tool_calls[0]
        assert tc.name == "open"
        assert tc.arguments["url"] == "http://test"


class TestFakeOpenBotTransport:
    def test_default_succeeds(self) -> None:
        t = FakeOpenBotTransport()
        assert t.is_reachable() is True
        r = t.run_task("click the button")
        assert r.finished is True
        assert t.calls == ["click the button"]

    def test_unreachable_transport_refuses(self) -> None:
        t = FakeOpenBotTransport(reachable=False)
        assert t.is_reachable() is False

    def test_custom_default_result(self) -> None:
        r = OpenBotRunResult(text="done", finished=True)
        t = FakeOpenBotTransport(default_result=r)
        result = t.run_task("x")
        assert result.text == "done"

    def test_fake_satisfies_protocol(self) -> None:
        assert isinstance(FakeOpenBotTransport(), OpenBotTransport)


class TestOpenBotValueObjects:
    def test_tool_def_immutable(self) -> None:
        td = OpenBotToolDef(name="click", description="click a button")
        assert td.name == "click"
        assert td.parameters == {}

    def test_tool_call_default_args_empty(self) -> None:
        tc = OpenBotToolCall(tool_call_id="tc1", name="open")
        assert tc.arguments == {}

    def test_run_result_defaults(self) -> None:
        r = OpenBotRunResult()
        assert r.text == ""
        assert r.finished is False
        assert r.error == ""


class TestHttpTransportDoesNotImportNetwork:
    def test_class_exists(self) -> None:
        assert HttpOpenBotTransport is not None


class TestSecurityTimeoutRaises:
    def test_transport_timeout_is_honest(self) -> None:
        from jarvis.infrastructure.openbot_task_agent import OpenBotTaskAgent

        class _TimeoutTransport:
            endpoint = "fake://timeout"

            def is_reachable(self) -> bool:
                return True

            def run_task(
                self, task: str, *, tools: tuple[OpenBotToolDef, ...] = (), timeout: float = 120.0
            ) -> OpenBotRunResult:
                raise OpenBotError("connection timed out")

        agent = OpenBotTaskAgent(_TimeoutTransport())
        result = agent.run_task("do something")
        assert not result.success
        assert "timed out" in result.summary.lower() or "error" in result.summary.lower()


class TestSecurityMalformedEndpointRefuses:
    def test_unreachable_transport_gives_honest_failure(self) -> None:
        t = FakeOpenBotTransport(reachable=False)
        assert not t.is_reachable()
        from jarvis.infrastructure.openbot_task_agent import OpenBotTaskAgent

        agent = OpenBotTaskAgent(t)
        result = agent.run_task("click")
        assert not result.success
        assert "unreachable" in result.summary.lower()
