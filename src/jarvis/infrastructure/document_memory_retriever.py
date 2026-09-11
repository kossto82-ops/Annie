"""DocumentMemoryRetriever: recall that also surfaces Jarvis's stored documents.

The document store is a seam of its own (project files, notes the companion
shared). ``DocumentMemoryRetriever`` folds it into *recall* -- the same query a
memory retriever answers -- so a conversation about "the API", say, can surface a
matching stored file alongside beliefs and episodes, each hit carrying provenance
("document: <name>") and a snippet instead of raw bytes (Vision §3, D6).

It wraps an existing :class:`MemoryRetriever` rather than re-implementing it: the
base ranks what Jarvis already holds by meaning or by tokens, and documents are
searched by name/text and merged in on the same relevance footing. With no
document store wired, it is exactly the base retriever, so an offline Jarvis is
unchanged (D7/D8). Documents are always searched lexically -- deterministic,
offline, and honest about a file whose bytes never meant anything to rank.
"""

from __future__ import annotations

from datetime import datetime

from collections.abc import Callable

from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.retrieval.document_store import DocumentStore
from jarvis.domain.retrieval.memory_retriever import MemoryRetriever
from jarvis.domain.value_objects.recalled_memory import RecalledMemory

_DocumentSource = Callable[[], DocumentStore | None]


class DocumentMemoryRetriever:
    """Merges document hits from a store into another retriever's recall."""

    def __init__(self, base: MemoryRetriever, source: _DocumentSource) -> None:
        """Wrap ``base``; documents come from ``source()`` on every recall.

        The source is a callable (not a store) so swapping the documents store at
        runtime is reflected without rewiring the retriever.
        """
        self._base = base
        self._source = source

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[RecalledMemory, ...]:
        memories = list(self._base.recall(query, limit=limit, since=since, until=until))
        store = self._source()
        if store is None:
            return tuple(memories[: max(0, limit)])
        documents = [
            RecalledMemory(
                content=hit.snippet,
                kind=MemoryKind.DOCUMENT,
                provenance=f"document: {hit.name}",
                relevance=hit.relevance,
            )
            for hit in store.search_documents(query, limit=limit)
        ]
        merged = memories + documents
        merged.sort(
            key=lambda m: (-m.relevance, -(m.source_confidence or 0.0), m.content)
        )
        return tuple(merged[: max(0, limit)])