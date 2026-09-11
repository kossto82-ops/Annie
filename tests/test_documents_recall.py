"""Documents ride recall: the companion's files bear on queries like memory does.

When a Jarvis holds documents, recall no longer stops at beliefs and episodes: the
same query is answered by the document store too, each hit carrying provenance
("document: <name>") and a snippet -- a candidate, never a verdict (Vision §3). An
offline Jarvis (no store) recalls exactly as before, so the default is unchanged
(D7/D8), and the whole seam is deterministic and typed.
"""

from __future__ import annotations

from datetime import datetime

from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.infrastructure.document_memory_retriever import DocumentMemoryRetriever
from jarvis.infrastructure.document_store import LocalDocumentStore
from jarvis.jarvis import Jarvis


def _memory_io(docs: dict[str, bytes]):
    def io(operation: str, path: str, payload: bytes) -> bytes:
        if operation == "list":
            return "\n".join(sorted(docs)).encode("utf-8")
        if operation == "read":
            return docs.get(path, b"")
        if operation == "delete":
            docs.pop(path, None)
            return b""
        docs[path] = payload
        return b""

    return io


class _StubRetriever:
    """A base retriever whose recall is whatever the test says it is."""

    def __init__(self, memories: tuple[RecalledMemory, ...]) -> None:
        self._memories = memories

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[RecalledMemory, ...]:
        return self._memories[: max(0, limit)]


def _documented_store(*docs: tuple[str, bytes]) -> LocalDocumentStore:
    return LocalDocumentStore("root", io=_memory_io(dict(docs)))


class TestDocumentMemoryRetriever:
    def test_merges_document_hits_into_base_recall(self) -> None:
        base = _StubRetriever(
            (
                RecalledMemory(
                    content="one conclusion",
                    kind=MemoryKind.WORLD_BELIEF,
                    provenance="world belief",
                    relevance=0.5,
                ),
            )
        )
        store = _documented_store(("api.md", b"Jarvis api over websocket"))
        retriever = DocumentMemoryRetriever(base, lambda: store)
        memories = retriever.recall("jarvis api")
        assert memories[0].kind is MemoryKind.DOCUMENT
        assert memories[0].provenance == "document: api.md"
        assert "api" in memories[0].content.lower()
        assert {m.kind for m in memories} == {MemoryKind.DOCUMENT, MemoryKind.WORLD_BELIEF}

    def test_offline_source_returns_the_base_retriever_unchanged(self) -> None:
        base = _StubRetriever(
            (
                RecalledMemory(
                    content="only memory",
                    kind=MemoryKind.EPISODE,
                    provenance="episode",
                    relevance=1.0,
                ),
            )
        )
        retriever = DocumentMemoryRetriever(base, lambda: None)
        assert retriever.recall("anything") == base.recall("anything")

    def test_limit_applies_to_the_merged_recall(self) -> None:
        base = _StubRetriever(
            (
                RecalledMemory(
                    content="memory one",
                    kind=MemoryKind.EPISODE,
                    provenance="episode",
                    relevance=1.0,
                ),
            )
        )
        store = _documented_store(("api.md", b"Jarvis api"), ("auth.md", b"auth tokens"))
        retriever = DocumentMemoryRetriever(base, lambda: store)
        memories = retriever.recall("api", limit=1)
        assert len(memories) == 1
        assert memories[0].kind is MemoryKind.DOCUMENT  # the better match led


class TestDocumentsInJarvisRecall:
    def test_recall_surfaces_a_matching_document_with_provenance(self) -> None:
        jarvis = Jarvis(
            enable_recall=True,
            documents_store=_documented_store(("api.md", b"Jarvis api over websocket")),
        )
        memories = jarvis.recall("jarvis api")
        documents = [m for m in memories if m.kind is MemoryKind.DOCUMENT]
        assert len(documents) == 1
        assert documents[0].provenance == "document: api.md"

    def test_an_episode_recalls_a_matching_document(self) -> None:
        jarvis = Jarvis(
            enable_recall=True,
            documents_store=_documented_store(("api.md", b"Jarvis api over websocket")),
        )
        episode = jarvis.think("jarvis api")
        assert any(
            memory.kind is MemoryKind.DOCUMENT
            and memory.provenance == "document: api.md"
            for memory in episode.recalled_memories
        )

    def test_conversational_reason_gets_documents_as_context(self) -> None:
        jarvis = Jarvis(
            enable_recall=True,
            documents_store=_documented_store(("runbook.md", b"deployment runbook")),
        )
        memories = jarvis.recall("deployment")
        assert any(m.kind is MemoryKind.DOCUMENT for m in memories)

    def test_no_store_keeps_recall_honest_and_empty(self) -> None:
        jarvis = Jarvis(enable_recall=True)
        assert jarvis.recall("anything at all") == ()

    def test_embedding_recall_still_folds_documents_in(self) -> None:
        jarvis = Jarvis(
            enable_recall=True,
            documents_store=_documented_store(("api.md", b"Jarvis api over websocket")),
        )

        class ClusterEmbedder:
            def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
                return tuple(((0.0, 1.0),) * len(texts))

        jarvis.enable_embedding_recall(ClusterEmbedder())  # type: ignore[arg-type]
        memories = jarvis.recall("jarvis api")
        assert any(m.kind is MemoryKind.DOCUMENT for m in memories)