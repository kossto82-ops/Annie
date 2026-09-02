"""SearXNGResearchSource: the deep-research adapter, tested fully offline.

The network is an injectable `transport` callable, so every test here runs with no
socket and deterministically (Vision §38, D8). The adapter only *gathers* cited
documents and describes what it found; it never decides anything (D6).
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from jarvis import Jarvis
from jarvis.domain.retrieval.research_source import ResearchSource
from jarvis.domain.value_objects.research_report import ResearchReport
from jarvis.infrastructure.odysseus_search_source import (
    SearXNGResearchSource,
    build_odysseus_search_source,
)

_RESULTS = {
    "results": [
        {"title": "First hit", "url": "https://a.example/p", "content": "snippet one"},
        {"title": "Second hit", "url": "https://b.example/q", "content": "snippet two"},
    ]
}


def _json_transport(payload: object) -> object:
    encoded = json.dumps(payload).encode("utf-8")

    def transport(
        url: str, headers: Mapping[str, str], body: bytes, timeout: float
    ) -> bytes:
        return encoded

    return transport


class TestDeepResearch:
    def test_returns_a_report_with_cited_documents(self) -> None:
        src = SearXNGResearchSource(
            instance="https://search.example", transport=_json_transport(_RESULTS)  # type: ignore[arg-type]
        )
        report = src.deep_research("epistemic humility", depth=1)
        assert isinstance(report, ResearchReport)
        assert report.query == "epistemic humility"
        assert len(report.documents) == 2
        doc = report.documents[0]
        assert doc.source == "searxng"
        assert doc.url == "https://a.example/p"
        assert doc.title == "First hit"
        assert "snippet one" in doc.content
        assert doc.metadata["engine"] == "searxng"

    def test_summary_describes_retrieval_not_a_verdict(self) -> None:
        src = SearXNGResearchSource(
            instance="https://search.example", transport=_json_transport(_RESULTS)  # type: ignore[arg-type]
        )
        report = src.deep_research("frogs", depth=1)
        assert "frogs" in report.summary
        assert "2" in report.summary
        assert "First hit" in report.summary

    def test_empty_results_yield_an_honest_report(self) -> None:
        src = SearXNGResearchSource(
            instance="https://search.example", transport=_json_transport({"results": []})  # type: ignore[arg-type]
        )
        report = src.deep_research("nothing exists", depth=1)
        assert report.documents == ()
        assert "found nothing" in report.summary

    def test_depth_scales_the_result_count(self) -> None:
        results = {
            "results": [
                {"title": f"h{i}", "url": f"https://x/{i}", "content": "c"}
                for i in range(20)
            ]
        }
        src = SearXNGResearchSource(
            instance="https://search.example", transport=_json_transport(results)  # type: ignore[arg-type]
        )
        assert len(src.deep_research("broad", depth=1).documents) == 5
        assert len(src.deep_research("broad", depth=3).documents) == 15

    def test_depth_is_bounded(self) -> None:
        results = {
            "results": [
                {"title": f"h{i}", "url": f"https://x/{i}", "content": "c"}
                for i in range(500)
            ]
        }
        src = SearXNGResearchSource(
            instance="https://search.example", transport=_json_transport(results)  # type: ignore[arg-type]
        )
        # A hostile depth never requests an unbounded result set: the adapter clamps
        # it to an upper bound (10 * base=5 = 50) before talking to the instance.
        assert len(src.deep_research("broad", depth=10**6).documents) == 50

    def test_hits_the_searxng_json_api_endpoint(self) -> None:
        calls: list[str] = []

        def transport(
            url: str, headers: Mapping[str, str], body: bytes, timeout: float
        ) -> bytes:
            calls.append(url)
            return b'{"results": []}'

        src = SearXNGResearchSource(instance="https://search.example", transport=transport)
        src.deep_research("api check", depth=1)
        assert calls and "search.example/search?q=api+check" in calls[0]
        assert "format=json" in calls[0]
        assert "safesearch=" in calls[0]

    def test_transport_failure_raises_a_clear_error(self) -> None:
        def boom(
            url: str, headers: Mapping[str, str], body: bytes, timeout: float
        ) -> bytes:
            raise OSError("network unreachable")

        src = SearXNGResearchSource(instance="https://search.example", transport=boom)
        with pytest.raises(RuntimeError) as exc:
            src.deep_research("ask", depth=1)
        assert "network unreachable" in str(exc.value)

    def test_bad_payload_raises_a_clear_error(self) -> None:
        def transport(
            url: str, headers: Mapping[str, str], body: bytes, timeout: float
        ) -> bytes:
            return b"<html>not json</html>"

        src = SearXNGResearchSource(instance="https://search.example", transport=transport)
        with pytest.raises(RuntimeError) as exc:
            src.deep_research("ask", depth=1)
        assert "unparseable" in str(exc.value)


class TestResearchProtocol:
    def test_adapts_to_the_research_source_seam(self) -> None:
        src = SearXNGResearchSource(
            instance="https://search.example", transport=_json_transport(_RESULTS)  # type: ignore[arg-type]
        )
        assert isinstance(src, ResearchSource)


class TestFactory:
    def test_returns_a_source_when_an_instance_is_configured(self) -> None:
        src = build_odysseus_search_source(  # type: ignore[arg-type]
            environ={"SEARXNG_INSTANCE": "https://s.example"},
            transport=_json_transport(_RESULTS),
        )
        assert src is not None
        assert src.deep_research("x", depth=1).documents

    def test_returns_none_without_an_instance(self) -> None:
        assert build_odysseus_search_source(environ={}) is None


class TestJarvisIntegration:
    def test_jarvis_is_offline_by_default(self) -> None:
        jarvis = Jarvis()
        assert jarvis.research_source is None
        with pytest.raises(RuntimeError):
            jarvis.deep_research("anything")

    def test_jarvis_uses_the_wired_research_source(self) -> None:
        class _Source:
            def deep_research(self, query: str, *, depth: int = 1):  # type: ignore[no-untyped-def]
                return ResearchReport(query=query, summary="summary", documents=())

        jarvis = Jarvis(research_source=_Source())  # type: ignore[arg-type]
        report = jarvis.deep_research("pineapple pizza")
        assert report.summary == "summary"