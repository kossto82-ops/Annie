"""ResearchReport: the value object that carries a deep-research run back.

It is immutable, must carry its cited documents (which keep their provenance), and
must describe the retrieval -- it never asserts a verdict (Vision §38, D6).
"""

from __future__ import annotations

import pytest

from jarvis.domain.value_objects.research_report import ResearchReport
from jarvis.domain.value_objects.retrieved_document import RetrievedDocument


def _doc(content: str = "body") -> RetrievedDocument:
    return RetrievedDocument(content=content, source="searxng", url="https://e.com")


class TestResearchReport:
    def test_carries_query_summary_and_documents(self) -> None:
        report = ResearchReport(
            query="why is the sky blue",
            summary="Found 1 result",
            documents=(_doc(),),
        )
        assert report.query == "why is the sky blue"
        assert report.summary == "Found 1 result"
        assert len(report.sources) == 1
        assert report.retrieved_at is not None

    def test_defaults_to_no_documents(self) -> None:
        report = ResearchReport(query="night sky", summary="nothing")
        assert report.sources == ()

    def test_rejects_blank_query(self) -> None:
        with pytest.raises(ValueError):
            ResearchReport(query="   ", summary="x")

    def test_is_immutable(self) -> None:
        report = ResearchReport(query="q", summary="s", documents=(_doc(),))
        with pytest.raises(AttributeError):
            report.summary = "other"  # type: ignore[misc]

    def test_documents_keep_their_provenance(self) -> None:
        report = ResearchReport(
            query="q",
            summary="s",
            documents=(_doc(),),
        )
        source = report.sources[0]
        assert source.source == "searxng"
        assert source.url == "https://e.com"