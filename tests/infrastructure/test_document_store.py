"""The local documents store, tested fully offline (D8) over an injectable io.

The store keeps one file per document under a bounded root -- exactly the bytes
of whatever the companion shares. Every test here drives a fake io driver so no
real disk is touched: reading, writing binary text, listing, deleting, the
flat-name sandbox, and the ``None`` offline factory are all exercised directly.
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
        for evil in ("..\\secret.txt", "a\\..\\b.txt", "a/b.txt", "/etc/passwd"):
            try:
                store.write_document(evil, b"x")
            except ValueError:
                continue
            raise AssertionError(f"flat-name sandbox let '{evil}' through")

    def test_read_missing_document_raises(self) -> None:
        io = _FakeIO()
        store = LocalDocumentStore(Path("C:\\jarvis-docs"), io=io)
        try:
            store.read_document("nope.txt")
        except KeyError:
            return
        raise AssertionError("reading a missing document should raise")


class TestBuildDocumentStore:
    def test_none_root_builds_no_store(self) -> None:
        assert build_document_store(None) is None
        assert build_document_store("") is None