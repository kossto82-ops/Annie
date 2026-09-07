"""The local documents store, tested fully offline (D8) over an injectable io.

The store keeps one file per document under a bounded root -- exactly the bytes
of whatever the companion shares, flat or filed under a relative folder. Every
test here drives a fake io driver so no real disk is touched: reading, writing
binary text, listing, deleting, nested folders, the bounded-path sandbox, and
the ``None`` offline factory are all exercised directly.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.infrastructure.document_store import LocalDocumentStore, build_document_store


class _FakeIO:
    """A tiny fake filesystem the store's sandbox thinks is real disk."""

    def __init__(self, start: dict[str, bytes] | None = None) -> None:
        self.files: dict[str, bytes] = dict(start or {})

    def __call__(self, operation: str, path: str, payload: bytes) -> bytes:
        if operation == "list":
            return "\n".join(sorted(self.files)).encode("utf-8")
        if operation == "read":
            return self.files[path]
        if operation == "write":
            self.files[path] = payload
        if operation == "delete":
            self.files.pop(path, None)
        return b""


class TestLocalDocumentStore:
    def test_reads_through_the_injected_io(self) -> None:
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=_FakeIO({"a.txt": b"hi"}))
        assert store.read_document("a.txt") == b"hi"

    def test_writes_exact_bytes(self) -> None:
        io = _FakeIO()
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=io)
        store.write_document("blob.bin", b"\x00\x01\xff")
        assert store.read_document("blob.bin") == b"\x00\x01\xff"

    def test_replaces_on_rewrite(self) -> None:
        io = _FakeIO({"v2.txt": b"old"})
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=io)
        store.write_document("v2.txt", b"new")
        assert store.read_document("v2.txt") == b"new"

    def test_lists_kept_documents(self) -> None:
        io = _FakeIO({"a.txt": b"1", "b.md": b"2"})
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=io)
        assert store.list_documents() == ("a.txt", "b.md")

    def test_removes_a_document(self) -> None:
        io = _FakeIO({"gone.txt": b"x"})
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=io)
        store.remove_document("gone.txt")
        assert store.list_documents() == ()

    def test_rejects_paths_that_escape_the_root(self) -> None:
        io = _FakeIO()
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=io)
        for evil in (
            "..\\secret.txt",
            "a\\..\\b.txt",
            "a/../b.txt",
            "/etc/passwd",
            "C:\\important.txt",
            "a//b.txt",
            "a/./b.txt",
            "a/",
        ):
            try:
                store.write_document(evil, b"x")
            except ValueError:
                continue
            raise AssertionError(f"bounded-path sandbox let '{evil}' through")

    def test_files_under_a_relative_folder(self) -> None:
        io = _FakeIO()
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=io)
        store.write_document("docs/api.md", b"# api")
        assert store.read_document("docs/api.md") == b"# api"
        assert store.read_document("docs\\api.md") == b"# api"  # backslashes normalise
        assert store.list_documents() == ("docs/api.md",)

    def test_nested_documents_search_by_content_snippet(self) -> None:
        io = _FakeIO(
            {"docs/v2/api.md": b"Jarvis api over websocket", "notes.md": b"grocery list"}
        )
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=io)
        hits = store.search_documents("jarvis api")
        assert [hit.name for hit in hits] == ["docs/v2/api.md"]
        assert "Jarvis api over websocket" in hits[0].snippet

    def test_removes_a_nested_document(self) -> None:
        io = _FakeIO({"docs/gone.txt": b"x", "keep.txt": b"y"})
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=io)
        store.remove_document("docs/gone.txt")
        assert store.list_documents() == ("keep.txt",)

    def test_read_missing_document_raises(self) -> None:
        io = _FakeIO()
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=io)
        try:
            store.read_document("nope.txt")
        except KeyError:
            return
        raise AssertionError("reading a missing document should raise")


class TestLocalDocumentStoreOnRealDisk:
    """The real ``_default_io`` driver, over a pytest tmp dir (still fully offline)."""

    def test_nested_write_lists_and_reads_on_disk(self, tmp_path: Path) -> None:
        store = LocalDocumentStore(tmp_path)
        store.write_document("docs/v2/api.md", b"# api")
        assert store.read_document("docs/v2/api.md") == b"# api"
        assert store.list_documents() == ("docs/v2/api.md",)

    def test_real_disk_rejects_escaping_names(self, tmp_path: Path) -> None:
        store = LocalDocumentStore(tmp_path)
        for evil in ("..\\secret.txt", "a/../b.txt", "/etc/passwd"):
            try:
                store.write_document(evil, b"x")
            except ValueError:
                continue
            raise AssertionError(f"real-disk sandbox let '{evil}' through")


class TestBuildDocumentStore:
    def test_none_root_builds_no_store(self) -> None:
        assert build_document_store(None) is None
        assert build_document_store("") is None


class TestDocumentSearch:
    """Searching mirrors lexical recall: candidates with a snippet, never a verdict."""

    def test_text_document_matches_by_content(self) -> None:
        io = _FakeIO({"api.md": b"Jarvis api over websocket"})
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=io)
        hits = store.search_documents("jarvis api")
        assert [hit.name for hit in hits] == ["api.md"]
        assert hits[0].relevance == 1.0
        assert "Jarvis api over websocket" in hits[0].snippet

    def test_binary_document_is_found_by_name_alone(self) -> None:
        io = _FakeIO({"blob.bin": b"\x00\x01\xff"})
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=io)
        hits = store.search_documents("blob")
        assert len(hits) == 1
        assert hits[0].name == "blob.bin"
        assert hits[0].snippet == "blob.bin"  # opaque bytes are never quoted
        assert store.search_documents("jarvis") == ()

    def test_most_relevant_document_leads(self) -> None:
        io = _FakeIO(
            {
                "old.txt": b"deployment runbook",
                "new.txt": b"deployment runbook for the api service",
            }
        )
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=io)
        hits = store.search_documents("deployment runbook")
        assert [hit.name for hit in hits] == ["new.txt", "old.txt"]

    def test_snippet_is_bounded_around_the_match(self) -> None:
        body = "lorem ipsum dolor sit amet " * 10
        io = _FakeIO({"notes.txt": body.encode("utf-8")})
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=io)
        hits = store.search_documents("dolor")
        assert len(hits) == 1
        assert "dolor" in hits[0].snippet
        assert len(hits[0].snippet) < 300

    def test_limit_and_no_match_are_honest(self) -> None:
        io = _FakeIO(
            {
                "a.txt": b"alpha beta gamma",
                "b.txt": b"alpha delta epsilon",
                "c.txt": b"beta zeta eta",
            }
        )
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=io)
        assert len(store.search_documents("alpha", limit=1)) == 1
        assert store.search_documents("nonexistent term") == ()
        assert store.search_documents("   ") == ()  # no scoreable tokens