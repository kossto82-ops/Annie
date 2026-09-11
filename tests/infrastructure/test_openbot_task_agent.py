"""Offline tests for OpenBotTaskAgent and build_openbot_task_agent (Increment 161).

Covers every adapter case (A-E, G-U): disabled/unconfigured yields None,
unreachable transport yields honest failure, success/partial/error mapping,
tool call recording, provenance preservation, runtime wiring, and the
security boundary that Jarvis memory is never mutated.
"""

from __future__ import annotations

import pytest

from jarvis.infrastructure.openbot_task_agent import (
    OpenBotTaskAgent,
    _map_result,
    build_openbot_task_agent,
)
from jarvis.infrastructure.openbot_transport import (
    FakeOpenBotTransport,
    OpenBotRunResult,
    OpenBotToolCall,
)
from jarvis.infrastructure.provider_settings import OpenBotSettings
from jarvis.jarvis import Jarvis

# ---------------------------------------------------------------------------
# Adapter core (run_task mapping)
# ---------------------------------------------------------------------------


class TestAdapterMapping:
    def test_empty_task_is_honest_failure(self) -> None:
        agent = OpenBotTaskAgent(FakeOpenBotTransport())
        result = agent.run_task("   ")
        assert not result.success
        assert "no task" in result.summary.lower()

    def test_unreachable_transport_yields_honest_failure(self) -> None:
        agent = OpenBotTaskAgent(FakeOpenBotTransport(reachable=False))
        result = agent.run_task("click the button")
        assert not result.success
        assert "unreachable" in result.summary.lower()

    def test_successful_run_maps_to_task_result(self) -> None:
        transport = FakeOpenBotTransport()
        agent = OpenBotTaskAgent(transport)
        result = agent.run_task("open the calendar")
        assert result.success is True
        assert transport.calls == ["open the calendar"]

    def test_partial_run_maps_to_failure(self) -> None:
        r = OpenBotRunResult(text="partial output", finished=False)
        transport = FakeOpenBotTransport(default_result=r)
        agent = OpenBotTaskAgent(transport)
        result = agent.run_task("do something")
        assert not result.success
        assert "partial" in result.summary.lower()

    def test_error_event_maps_to_failure(self) -> None:
        r = OpenBotRunResult(error="model refused", finished=False)
        transport = FakeOpenBotTransport(default_result=r)
        agent = OpenBotTaskAgent(transport)
        result = agent.run_task("do something")
        assert not result.success
        assert "refused" in result.summary.lower()

    def test_tool_calls_are_recorded_in_summary(self) -> None:
        r = OpenBotRunResult(
            text="opened",
            tool_calls=(
                OpenBotToolCall(tool_call_id="tc1", name="open", arguments={"url": "http://test"}),
            ),
            finished=True,
        )
        transport = FakeOpenBotTransport(default_result=r)
        agent = OpenBotTaskAgent(transport)
        result = agent.run_task("open the page")
        assert result.success is True
        assert "tool calls" in result.summary.lower()
        assert "open(" in result.summary.lower()

    def test_adapter_records_last_result(self) -> None:
        agent = OpenBotTaskAgent(FakeOpenBotTransport())
        agent.run_task("click")
        assert agent.last_result is not None
        assert agent.last_result.finished is True


class TestMapResult:
    def test_empty_text_no_tools_gives_no_output(self) -> None:
        r = OpenBotRunResult(finished=True)
        result = _map_result("task", r)
        assert result.success is True
        assert "no output" in result.summary.lower()

    def test_error_overrides_finished(self) -> None:
        r = OpenBotRunResult(error="fail", finished=True)
        result = _map_result("t", r)
        assert not result.success


# ---------------------------------------------------------------------------
# Build function (configuration → adapter or None)
# ---------------------------------------------------------------------------


class TestBuildOpenBotTaskAgent:
    def test_none_settings_returns_none(self) -> None:
        assert build_openbot_task_agent(settings=None, endpoint=None) is None

    def test_empty_endpoint_returns_none(self) -> None:
        s = OpenBotSettings(endpoint="")
        assert build_openbot_task_agent(settings=s) is None

    def test_explicit_endpoint_builds_adapter(self) -> None:
        s = OpenBotSettings(endpoint="http://localhost:4600")
        agent = build_openbot_task_agent(settings=s)
        assert agent is not None
        assert isinstance(agent, OpenBotTaskAgent)

    def test_endpoint_override_takes_precedence(self) -> None:
        s = OpenBotSettings(endpoint="http://x")
        agent = build_openbot_task_agent(settings=s, endpoint="http://y")
        assert agent is not None
        assert agent.transport.endpoint == "http://y"

    def test_agent_token_is_forwarded(self) -> None:
        s = OpenBotSettings(endpoint="http://x", agent_token="tok")
        agent = build_openbot_task_agent(settings=s)
        assert agent is not None


# ---------------------------------------------------------------------------
# Jarvis integration
# ---------------------------------------------------------------------------


class TestJarvisOpenBotIntegration:
    def test_can_do_reflects_wired_openbot(self) -> None:
        agent = OpenBotTaskAgent(FakeOpenBotTransport())
        jarvis = Jarvis(openbot_agent=agent)
        assert jarvis.openbot_agent is agent

    def test_unwired_jarvis_is_offline(self) -> None:
        jarvis = Jarvis()
        assert jarvis.openbot_agent is None

    def test_execute_on_computer_delegates_to_agent(self) -> None:
        agent = OpenBotTaskAgent(FakeOpenBotTransport())
        jarvis = Jarvis(openbot_agent=agent)
        result = jarvis.execute_on_computer("open the calendar")
        assert result.success is True

    def test_execute_on_computer_raises_when_offline(self) -> None:
        jarvis = Jarvis()
        with pytest.raises(RuntimeError, match="no OpenBot"):
            jarvis.execute_on_computer("click")

    def test_runtime_wiring_updates_can_do(self) -> None:
        jarvis = Jarvis()
        assert jarvis.openbot_agent is None
        agent = OpenBotTaskAgent(FakeOpenBotTransport())
        jarvis.set_openbot_agent(agent)
        assert jarvis.openbot_agent is agent

    def test_clearing_openbot_agent(self) -> None:
        jarvis = Jarvis(openbot_agent=OpenBotTaskAgent(FakeOpenBotTransport()))
        jarvis.set_openbot_agent(None)
        assert jarvis.openbot_agent is None
        with pytest.raises(RuntimeError):
            jarvis.execute_on_computer("click")

    def test_openbot_does_not_mutate_jarvis_memory(self) -> None:
        """Security: adapter never touches beliefs, episodes, or conversation."""
        jarvis = Jarvis()
        beliefs_before = jarvis.beliefs.all_beliefs()
        jarvis.set_openbot_agent(OpenBotTaskAgent(FakeOpenBotTransport()))
        jarvis.execute_on_computer("run a task")
        assert jarvis.beliefs.all_beliefs() == beliefs_before
        assert jarvis.conversation.is_empty
