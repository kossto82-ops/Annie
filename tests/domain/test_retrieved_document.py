"""RetrievedDocument: the value object that carries external information back.

It is immutable and must carry the provenance (source/url/title/metadata) that lets
Jarvis later tell external information apart from internal knowledge (Vision §8).
"""

from __future__ import annotations

import pytest

from jarvis.domain.value_objects.retrieved_document import RetrievedDocument


class TestRetrievedDocument:
    def test_requires_content(self) -> None:
        doc = RetrievedDocument(content="hello", source="web", url="https://e.com")
        assert doc.content == "hello"
        assert doc.source == "web"
        assert doc.url == "https://e.com"
        assert doc.title is None
        assert doc.metadata == {}
        assert doc.retrieved_at is not None

    def test_rejects_blank_content(self) -> None:
        with pytest.raises(ValueError):
            RetrievedDocument(content="   ", source="web")

    def test_is_immutable(self) -> None:
        doc = RetrievedDocument(content="x", source="web")
        with pytest.raises(AttributeError):
            doc.content = "y"  # type: ignore[misc]

    def test_keeps_provenance(self) -> None:
        doc = RetrievedDocument(
            content="body",
            source="web",
            url="https://e.com/a",
            title="A page",
            metadata={"published": "2026-01-01", "lang": "es"},
        )
        assert doc.title == "A page"
        assert doc.metadata == {"published": "2026-01-01", "lang": "es"}
