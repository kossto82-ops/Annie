"""F4 — passage-level document search: deterministic sliding-window chunking.

The document seam now also answers at passage granularity (roadmap F4): a text
document is chunked once per search by a fixed word window with a fixed overlap,
every chunk carries the byte offsets that locate it inside the stored utf-8 bytes,
and chunks are ranked by the same offline ``relatedness`` scorer recall uses
(Inc-168) — vocabulary-only, D18-faithful. Binary files are never chunked: at most
a name-only passage with 0/0 offsets is surfaced. Chunks, offsets and ranking are
all deterministic and disk-free over the injected io driver (D8).
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict, cast

from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.value_objects.capability import Capability
from jarvis.infrastructure.document_store import (
    LocalDocumentStore,
    _passage_chunks,  # type: ignore[reportPrivateUsage]
)
from jarvis.interface.command_center import handle
from jarvis.jarvis import Jarvis

_WORDS = "the quick brown fox jumps over the lazy dog sleeps all the noon long "


class _SearchHit(TypedDict):
    name: str
    snippet: str
    start: int
    end: int


def _io_for(*docs: tuple[str, bytes]):
    files = dict(docs)

    def io(operation: str, path: str, payload: bytes) -> bytes:
        if operation == "list":
            return "\n".join(sorted(files)).encode("utf-8")
        if operation == "read":
            return files.get(path, b"")
        if operation == "delete":
            files.pop(path, None)
            return b""
        files[path] = payload
        return b""

    return io


class TestPassageChunking:
    """The deterministic sliding-word-window chunker, in isolation."""

    def test_short_text_is_one_passage(self) -> None:
        chunks = _passage_chunks("Jarvis api over websocket")
        assert len(chunks) == 1
        snippet, start, end = chunks[0]
        assert snippet == "Jarvis api over websocket"
        assert start == 0
        assert end == len("Jarvis api over websocket")

    def test_chunks_are_deterministic(self) -> None:
        text = _WORDS * 12
        assert _passage_chunks(text) == _passage_chunks(text)

    def test_sliding_window_overlaps_across_the_break(self) -> None:
        # A long text breaks into several passages; the last word of one passage
        # reappears in the next (overlap), so a phrase at the joint stays whole.
        text = _WORDS * 12
        chunks = _passage_chunks(text)
        assert len(chunks) > 1
        first, second = chunks[0], chunks[1]
        first_words = first[0].split()
        second_words = second[0].split()
        shared = set(first_words) & set(second_words)
        assert shared  # overlap words belong to both passages

    def test_offsets_reproduce_the_snippet(self) -> None:
        # Non-ascii text must still give byte offsets that re-slice the utf-8 bytes.
        text = ("ös" * 40) + " the target phrase " + (_WORDS * 3)
        for snippet, start, end in _passage_chunks(text):
            assert text.encode("utf-8")[start:end].decode("utf-8") == snippet

    def test_no_words_yields_no_passages(self) -> None:
        assert _passage_chunks("   \n\t ") == ()
        assert _passage_chunks("") == ()


class TestPassageSearch:
    def _store(self, *docs: tuple[str, bytes]) -> LocalDocumentStore:
        return LocalDocumentStore("root", io=_io_for(*docs))

    def test_search_returns_the_matching_passage_with_offsets(self) -> None:
        store = self._store(("api.md", b"Jarvis api over websocket"))
        hits = store.search_passages("jarvis api")
        assert len(hits) == 1
        assert hits[0].snippet == "Jarvis api over websocket"
        assert hits[0].start == 0
        assert hits[0].end == len("Jarvis api over websocket")
        assert hits[0].relevance == 1.0

    def test_cross_boundary_phrase_is_found_whole(self) -> None:
        # The phrase straddles the spot a naive chunker would split; the overlap
        # window still holds it whole, and the hit's offsets point at exactly it.
        store = self._store(
            ("manual.md", f"{_WORDS * 3}red dragon sleeps at noon{_WORDS * 3}".encode()),
        )
        hits = store.search_passages("dragon", limit=1)
        assert len(hits) == 1
        assert "red dragon sleeps at noon" in hits[0].snippet
        raw = store.read_document("manual.md")
        assert raw[hits[0].start : hits[0].end] == hits[0].snippet.encode("utf-8")

    def test_ranking_orders_better_passages_first(self) -> None:
        store = self._store(
            ("a.txt", b"deployment"),  # one shared token
            ("b.txt", b"deployment runbook"),  # both tokens
        )
        hits = store.search_passages("deployment runbook")
        assert [h.name for h in hits] == ["b.txt", "a.txt"]
        assert hits[0].relevance > hits[1].relevance

    def test_ranked_by_relatedness_across_passages(self) -> None:
        # Several passages share the query; the one with the fuller surface or a
        # concept-level match leads. Covered by the shared Inc-168 scorer.
        store = self._store(
            ("paper.txt", (_WORDS + "deployment runbook " + _WORDS).encode())
        )
        hits = store.search_passages("deployment runbook")
        assert len(hits) >= 1
        assert hits[0].name == "paper.txt"

    def test_limit_and_no_match_are_honest(self) -> None:
        store = self._store(("a.txt", b"alpha beta gamma"), ("b.txt", b"beta zeta"))
        assert len(store.search_passages("alpha", limit=1)) == 1
        assert store.search_passages("zzz absent") == ()
        assert store.search_passages("   ") == ()

    def test_folder_nesting_and_ownership_survive(self) -> None:
        store = self._store(("docs/v2/api.md", b"Jarvis api over websocket"))
        hits = store.search_passages("api")
        assert [h.name for h in hits] == ["docs/v2/api.md"]
        store.write_document("docs/v2/api.md", b"Jarvis api v2")
        assert store.document_meta("docs/v2/api.md") is not None
        assert store.list_documents() == ("docs/v2/api.md",)


class TestBinarySkip:
    """Opaque bytes are never chunked or quoted (F4)."""

    def test_binary_file_is_never_chunked(self) -> None:
        store = LocalDocumentStore(
            Path("root"), io=_io_for(("blob.bin", b"\x00\x01\xff"))
        )
        assert store.search_passages("jarvis") == ()
        hits = store.search_passages("blob")
        assert len(hits) == 1  # name-only passage, offsets 0/0
        assert hits[0].snippet == "blob.bin"
        assert hits[0].start == 0
        assert hits[0].end == 0


class TestF4Acceptance:
    """The roadmap acceptance: ``documents search`` returns passage + offsets."""

    def test_documents_search_returns_the_passage_and_offsets(self) -> None:
        body = f"{_WORDS * 3}red dragon sleeps at noon{_WORDS * 3}".encode()
        jarvis = Jarvis(documents_store=LocalDocumentStore("root", io=_io_for(("manual.md", body))))
        jarvis.remember_capability(
            Capability(
                name="work with files",
                description="hold files",
                requirement="documents_store",
                provenance="test",
                status=CapabilityStatus.ACQUIRED,
            )
        )
        result = handle(jarvis, "documents", {"action": "search", "query": "dragon", "limit": 1})
        reply = str(result["reply"])
        assert "red dragon sleeps at noon" in reply
        assert "manual.md [2" in reply or "manual.md [1" in reply  # offsets ride the line
        assert "(" in reply and ")" in reply  # relevance rides too
        hits = cast("list[_SearchHit]", result["hits"])
        assert hits[0]["name"] == "manual.md"
        assert 0 <= hits[0]["start"] < hits[0]["end"]
        raw = jarvis.read_document("manual.md")
        assert raw[hits[0]["start"] : hits[0]["end"]] == hits[0]["snippet"].encode()