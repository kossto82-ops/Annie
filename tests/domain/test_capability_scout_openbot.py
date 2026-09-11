"""Tests for the 'execute on computer' capability in the scout catalog and
capability registry (Increment 161).

Verifies that the OpenBot capability is registered in the catalog, backed
by the OpenBotCapability provider, and not falsely claimed when offline.
"""

from __future__ import annotations

from jarvis.domain.services.capability_scout import catalog
from jarvis.domain.value_objects.capability import Capability
from jarvis.infrastructure.capability_registry import (
    OpenBotCapability,
    build_default_registry,
)
from jarvis.infrastructure.openbot_task_agent import OpenBotTaskAgent
from jarvis.infrastructure.openbot_transport import FakeOpenBotTransport


class TestCapabilityScout:
    def test_execute_on_computer_is_in_catalog(self) -> None:
        names = {cap.name for cap in catalog()}
        assert "execute on computer" in names

    def test_execute_on_computer_entry_has_correct_fields(self) -> None:
        entries = [cap for cap in catalog() if cap.name == "execute on computer"]
        assert len(entries) == 1
        entry = entries[0]
        assert isinstance(entry, Capability)
        assert "computer" in entry.description.lower() or "browser" in entry.description.lower()
        assert entry.requirement  # non-empty


class TestOpenBotCapability:
    def test_capability_name(self) -> None:
        agent = OpenBotTaskAgent(FakeOpenBotTransport())
        cap = OpenBotCapability(agent)
        assert cap.capability == "execute on computer"

    def test_live_transport_reports_available(self) -> None:
        agent = OpenBotTaskAgent(FakeOpenBotTransport(reachable=True))
        cap = OpenBotCapability(agent)
        assert cap.is_available() is True

    def test_unreachable_transport_reports_unavailable(self) -> None:
        agent = OpenBotTaskAgent(FakeOpenBotTransport(reachable=False))
        cap = OpenBotCapability(agent)
        assert cap.is_available() is False

    def test_non_openbot_agent_reports_unavailable(self) -> None:
        class _PlainAgent:
            def run_task(self, task: str) -> object:  # type: ignore[override]
                return object()

        cap = OpenBotCapability(_PlainAgent())  # type: ignore[arg-type]
        assert cap.is_available() is False


class TestBuildDefaultRegistryOpenBot:
    def test_openbot_agent_wires_execute_on_computer(self) -> None:
        agent = OpenBotTaskAgent(FakeOpenBotTransport(reachable=True))
        registry = build_default_registry(None, openbot_agent=agent)
        assert registry.provider_for("execute on computer") is not None

    def test_no_openbot_agent_yields_no_execute_on_computer(self) -> None:
        registry = build_default_registry(None)
        assert registry.provider_for("execute on computer") is None

    def test_unreachable_openbot_agent_yields_unavailable(self) -> None:
        agent = OpenBotTaskAgent(FakeOpenBotTransport(reachable=False))
        registry = build_default_registry(None, openbot_agent=agent)
        provider = registry.provider_for("execute on computer")
        assert provider is not None
        assert provider.is_available() is False
