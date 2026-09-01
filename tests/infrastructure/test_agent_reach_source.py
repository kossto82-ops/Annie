"""AgentReachSource: the Internet capability adapter, tested fully offline.

The network is an injectable `transport` callable, so every test here runs with no
socket and deterministically (Vision §38, D8) -- a real fetch, a search-key error,
an unavailable package, and Jarvis's offline default are all exercised directly.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from jarvis import Jarvis
from jarvis.infrastructure.agent_reach_source import (
    AgentReachSource,
    AgentReachUnavailable,
    build_agent_reach_source,
)


def _transport(source: str) -> object:
    """A transport that returns ``source`` bytes for any GET."""

    def transport(
        url: str, headers: Mapping[str, str], body: bytes, timeout: float
    ) -> bytes:
        return source.encode("utf-8")

    return transport


class TestRead:
    def test_read_returns_document_with_provenance(self) -> None:
        src = AgentReachSource(transport=_transport("# My page\nbody"))  # type: ignore[arg-type]
        doc = src.read("https://example.com/page")
        assert doc.source == "web"
        assert doc.url == "https://example.com/page"
        assert "My page" in doc.content

    def test_read_uses_the_injected_transport(self) -> None:
        calls: list[str] = []

        def transport(
            url: str, headers: Mapping[str, str], body: bytes, timeout: float
        ) -> bytes:
            calls.append(url)
            return b"content"

        src = AgentReachSource(transport=transport)
        src.read("https://a.com")
        assert calls and "r.jina.ai/https://a.com" in calls[0]


class TestSearch:
    def test_search_raises_clear_error_without_a_key(self) -> None:
        src = AgentReachSource(
            environ={}, transport=_transport("x")  # type: ignore[arg-type]
        )
        with pytest.raises(RuntimeError) as exc:
            src.search("hello")
        assert "JINA_API_KEY" in str(exc.value)

    def test_search_works_with_a_key(self) -> None:
        src = AgentReachSource(
            environ={"JINA_API_KEY": "k"},
            transport=_transport("results"),  # type: ignore[arg-type]
        )
        docs = src.search("hello")
        assert len(docs) == 1
        assert docs[0].source == "web_search"
        assert "results" in docs[0].content


class TestAvailableChannels:
    def test_reports_the_installed_channels(self) -> None:
        src = AgentReachSource()
        channels = src.available_channels()
        assert channels
        by_name = {c.name: c for c in channels}
        assert by_name["web"].status == "ok"

    def test_raises_when_package_is_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        src = AgentReachSource()
        import importlib

        def boom(name: str) -> object:
            raise ModuleNotFoundError(name)

        monkeypatch.setattr(importlib, "import_module", boom)
        with pytest.raises(AgentReachUnavailable):
            src.available_channels()


class TestFactory:
    def test_returns_a_source_when_agent_reach_is_installed(self) -> None:
        src = build_agent_reach_source()
        if src is not None:
            assert src.available_channels()

    def test_returns_none_when_agent_reach_is_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "jarvis.infrastructure.agent_reach_source.importlib.util.find_spec",
            lambda _name: None,
        )
        assert build_agent_reach_source() is None


class TestJarvisIntegration:
    def test_jarvis_is_offline_by_default(self) -> None:
        jarvis = Jarvis()
        assert jarvis.external_source is None
        assert jarvis.internet_channels() == ()
        with pytest.raises(RuntimeError):
            jarvis.read_external("https://a.com")

    def test_jarvis_uses_the_wired_source(self) -> None:
        class _Source:
            def read(self, url: str):  # type: ignore[no-untyped-def]
                from jarvis.domain.value_objects.retrieved_document import (
                    RetrievedDocument,
                )

                return RetrievedDocument(content="body", source="web", url=url)

            def search(self, query: str, *, limit: int = 5):
                return ()

            def available_channels(self):
                return ()

        jarvis = Jarvis(external_source=_Source())  # type: ignore[arg-type]
        assert jarvis.external_source is not None
        doc = jarvis.read_external("https://b.com")
        assert doc.source == "web"
        assert doc.url == "https://b.com"

    def test_a_failing_external_source_does_not_break_conversation(self) -> None:
        class _Broken:
            def read(self, url: str):
                raise RuntimeError("network down")

            def search(self, query: str, *, limit: int = 5):
                raise RuntimeError("network down")

            def available_channels(self):
                return ()

        jarvis = Jarvis(external_source=_Broken())  # type: ignore[arg-type]
        with pytest.raises(RuntimeError):
            jarvis.read_external("https://a.com")
        # ordinary thinking still works
        episode = jarvis.perceive("the sky is blue")
        assert episode is not None
