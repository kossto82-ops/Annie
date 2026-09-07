"""Editing a stored document via the chat seam (Vision §38, Increment 149).

The model merely *proposes* the revised text; Jarvis applies it through the
documents capability, keeps the recorded attribution, and frames what changed
from the real diff -- so everything here is deterministic and offline, with a fake
editor whose proposal is scripted. The honest edges (no store, no editor, decline,
binary file, identical rewrite) are pinned too.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from jarvis import Jarvis
from jarvis.domain.enums.document_owner import DocumentOwner
from jarvis.domain.value_objects.document_meta import DocumentMeta
from jarvis.infrastructure.document_store import build_document_store
from jarvis.infrastructure.llm_document_editor import LlmDocumentEditor
from jarvis.infrastructure.perceiver_factory import build_document_editor
from jarvis.infrastructure.scripted_language_model import ScriptedLanguageModel
from jarvis.infrastructure.silent_document_editor import SilentDocumentEditor


class _FakeStore:
    """A tiny DocumentStore for offline, disk-free edit tests."""

    def __init__(self) -> None:
        self._docs: dict[str, bytes] = {}
        self._meta: dict[str, DocumentOwner] = {}
        self._now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

    def list_documents(self) -> tuple[str, ...]:
        return tuple(sorted(self._docs))

    def read_document(self, name: str) -> bytes:
        return self._docs[name]

    def write_document(
        self, name: str, content: bytes, *, owner: DocumentOwner = DocumentOwner.COMPANION
    ) -> None:
        self._docs[name] = content
        self._meta[name] = owner

    def remove_document(self, name: str) -> None:
        self._docs.pop(name, None)
        self._meta.pop(name, None)

    def document_meta(self, name: str) -> DocumentMeta | None:
        if name not in self._meta:
            return None
        return DocumentMeta(
            name=name,
            owner=self._meta[name],
            size_bytes=len(self._docs[name]),
            stored_at=self._now,
            updated_at=self._now,
        )

    def search_documents(self, query: str, *, limit: int = 5) -> tuple[object, ...]:
        return ()


class _ScriptedEditor:
    """An editor that scripts what it proposes (no network, deterministic)."""

    def __init__(self, proposal: str | None = "Revised text.") -> None:
        self._proposal = proposal
        self.calls: list[tuple[str, str]] = []

    def propose(self, source_text: str, instruction: str) -> str | None:
        self.calls.append((source_text, instruction))
        return self._proposal


class TestDocumentEditing:
    def test_edit_requires_a_documents_store(self) -> None:
        jarvis = Jarvis(document_editor=_ScriptedEditor())  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="documents capability"):
            jarvis.edit_document("a.txt", "rewrite")

    def test_edit_requires_an_editor(self) -> None:
        jarvis = Jarvis(documents_store=_FakeStore())  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="document editor"):
            jarvis.edit_document("a.txt", "rewrite")

    def test_edit_applies_the_proposal_and_preserves_attribution(self) -> None:
        store = _FakeStore()
        store.write_document("plan.md", b"old plan", owner=DocumentOwner.JARVIS)
        editor = _ScriptedEditor(proposal="new plan\n")
        jarvis = Jarvis(documents_store=store, document_editor=editor)  # type: ignore[arg-type]
        edit = jarvis.edit_document("plan.md", "make it shorter")
        assert edit is not None
        assert edit.content == "new plan"
        assert edit.note == "1 line(s) removed, 1 added"
        assert store.read_document("plan.md") == b"new plan"
        meta = store.document_meta("plan.md")
        assert meta is not None
        assert meta.owner is DocumentOwner.JARVIS
        assert editor.calls == [("old plan", "make it shorter")]

    def test_edit_derives_the_note_from_the_real_diff(self) -> None:
        store = _FakeStore()
        source = "line one\nline two\nline three\n"
        store.write_document("notes.txt", source.encode("utf-8"))
        jarvis = Jarvis(
            documents_store=store,  # type: ignore[arg-type]
            document_editor=_ScriptedEditor(proposal="line one\nline three\n"),  # type: ignore[arg-type]
        )
        edit = jarvis.edit_document("notes.txt", "drop line two")
        assert edit is not None
        assert edit.note == "1 line(s) removed, 0 added"

    def test_identical_rewrite_is_reported_and_stays_untouched(self) -> None:
        store = _FakeStore()
        source = "same text"
        store.write_document("a.txt", source.encode("utf-8"))
        jarvis = Jarvis(
            documents_store=store,  # type: ignore[arg-type]
            document_editor=_ScriptedEditor(proposal="same text"),  # type: ignore[arg-type]
        )
        edit = jarvis.edit_document("a.txt", "keep it")
        assert edit is not None
        assert "unchanged" in edit.note
        assert store.read_document("a.txt") == b"same text"

    def test_a_declining_editor_returns_none_and_writes_nothing(self) -> None:
        store = _FakeStore()
        store.write_document("a.txt", b"kept")
        jarvis = Jarvis(
            documents_store=store,  # type: ignore[arg-type]
            document_editor=_ScriptedEditor(proposal=None),  # type: ignore[arg-type]
        )
        assert jarvis.edit_document("a.txt", "rewrite") is None
        assert store.read_document("a.txt") == b"kept"

    def test_binary_documents_are_never_rewritten(self) -> None:
        store = _FakeStore()
        store.write_document("img.bin", b"\x00\x01\xff")
        jarvis = Jarvis(
            documents_store=store,  # type: ignore[arg-type]
            document_editor=_ScriptedEditor(proposal="x"),  # type: ignore[arg-type]
        )
        with pytest.raises(ValueError, match="not text"):
            jarvis.edit_document("img.bin", "make it text")

    def test_editors_are_aligned_with_provider_settings(self) -> None:
        online = build_document_editor("ollama", "llama3")
        assert isinstance(online, LlmDocumentEditor)
        offline = build_document_editor("keyword")
        assert isinstance(offline, SilentDocumentEditor)
        assert build_document_editor("scripted") is not None

    def test_provider_settings_drive_the_editor(self) -> None:
        assert isinstance(
            build_document_editor("ollama", "llama3"), LlmDocumentEditor
        )
        assert isinstance(
            build_document_editor("scripted", ""), SilentDocumentEditor
        )

    def test_local_store_and_llm_editor_cooperate_on_disk(self, tmp_path: Path) -> None:
        store = build_document_store(tmp_path / "docs")
        assert store is not None
        store.write_document("a.txt", b"original on disk")
        jarvis = Jarvis(
            documents_store=store,
            document_editor=LlmDocumentEditor(
                ScriptedLanguageModel(default="rewritten on disk")
            ),
        )
        edit = jarvis.edit_document("a.txt", "rewrite it")
        assert edit is not None
        assert (tmp_path / "docs" / "a.txt").read_bytes() == b"rewritten on disk"
        assert (tmp_path / "docs" / "_jarvis-meta.json").is_file()

    def test_silent_editor_on_the_documents_seam_does_not_fabricate(self) -> None:
        store = _FakeStore()
        store.write_document("a.txt", b"kept")
        jarvis = Jarvis(
            documents_store=store,  # type: ignore[arg-type]
            document_editor=SilentDocumentEditor(),
        )
        assert jarvis.edit_document("a.txt", "reword") is None
        assert store.read_document("a.txt") == b"kept"