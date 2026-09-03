"""Tests for the notes capability seam (Odysseus #8).

Covers the `Note` value object, the `NotesStore` Protocol surface, the
`NotesCapability` provider, and Jarvis's integration: `can_do` reflects a wired
store, the notes methods hand read/write to the store edge, and an unwired Jarvis
stays offline with clear errors.
"""

from __future__ import annotations

import pytest

from jarvis.domain.retrieval.notes_store import NotesStore
from jarvis.domain.value_objects.capability import Capability
from jarvis.domain.value_objects.note import Note
from jarvis.infrastructure.capability_registry import (
    NotesCapability,
    build_default_registry,
)
from jarvis.jarvis import Jarvis


class _FakeNotesStore:
    """An in-memory notes store recording calls for deterministic assertions."""

    def __init__(self) -> None:
        self._notes: dict[str, Note] = {}
        self.created: list[str] = []
        self.deleted: list[str] = []

    def list_notes(self, *, limit: int = 100) -> tuple[Note, ...]:
        return tuple(self._notes.values())[:limit]

    def get_note(self, note_id: str) -> Note:
        return self._notes[note_id]

    def create_note(
        self, *, title: str, body: str = "", tags: tuple[str, ...] = ()
    ) -> Note:
        note = Note(id=f"n{len(self._notes) + 1}", title=title, body=body, tags=tags)
        self._notes[note.id] = note
        self.created.append(note.id)
        return note

    def update_note(
        self,
        note_id: str,
        *,
        title: str,
        body: str,
        tags: tuple[str, ...],
    ) -> Note:
        note = Note(id=note_id, title=title, body=body, tags=tags)
        self._notes[note_id] = note
        return note

    def delete_note(self, note_id: str) -> None:
        self.deleted.append(note_id)
        self._notes.pop(note_id, None)

    def search_notes(self, query: str, *, limit: int = 10) -> tuple[Note, ...]:
        return tuple(n for n in self._notes.values() if query in n.title)[:limit]


class TestNote:
    def test_requires_title_or_body(self) -> None:
        with pytest.raises(ValueError):
            Note(id="1", title="", body="")

    def test_records_provenance(self) -> None:
        note = Note(id="1", title="ideas", body="text")
        assert note.provenance == "note 1 'ideas'"


class TestNotesStoreProtocol:
    def test_fake_store_satisfies_the_protocol(self) -> None:
        assert isinstance(_FakeNotesStore(), NotesStore)


class TestNotesCapability:
    def test_notes_capability_backs_the_notes_name(self) -> None:
        provider = NotesCapability(_FakeNotesStore())  # type: ignore[arg-type]
        assert provider.capability == "manage notes"
        assert provider.is_available()

    def test_default_registry_backs_notes_when_a_store_is_wired(self) -> None:
        store = _FakeNotesStore()
        registry = build_default_registry(None, notes_store=store)  # type: ignore[arg-type]
        assert registry.provider_for("manage notes") is not None

    def test_default_registry_without_a_store_has_no_notes(self) -> None:
        registry = build_default_registry(None)
        assert registry.provider_for("manage notes") is None


class TestJarvisNotes:
    @staticmethod
    def _acquire(jarvis: Jarvis) -> None:
        capability = Capability(
            name="manage notes",
            description="keep and retrieve local notes",
            requirement="a wired notes store at the edge (NotesStore)",
            provenance="test",
        )
        jarvis.remember_capability(capability)
        jarvis.acquire_capability("manage notes")

    def test_can_do_reflects_a_wired_store(self) -> None:
        jarvis = Jarvis(notes_store=_FakeNotesStore())  # type: ignore[arg-type]
        self._acquire(jarvis)
        assert jarvis.can_do("manage notes")

    def test_unwired_jarvis_is_offline_to_notes(self) -> None:
        jarvis = Jarvis()
        self._acquire(jarvis)
        assert not jarvis.can_do("manage notes")

    def test_create_and_read_round_trips(self) -> None:
        jarvis = Jarvis(notes_store=_FakeNotesStore())  # type: ignore[arg-type]
        note = jarvis.create_note(title="ideas", body="remember this")
        assert note.id
        assert jarvis.get_note(note.id).body == "remember this"
        titles = [n.title for n in jarvis.list_notes()]
        assert titles[-1] == "ideas"

    def test_update_and_delete(self) -> None:
        store = _FakeNotesStore()
        jarvis = Jarvis(notes_store=store)  # type: ignore[arg-type]
        note = jarvis.create_note(title="a", body="b")
        jarvis.update_note(note.id, title="a2", body="b2", tags=("x",))
        assert jarvis.get_note(note.id).title == "a2"
        jarvis.delete_note(note.id)
        assert store.deleted == [note.id]

    def test_wiring_a_store_at_runtime_updates_can_do(self) -> None:
        jarvis = Jarvis()
        self._acquire(jarvis)
        assert not jarvis.can_do("manage notes")
        jarvis.set_notes_store(_FakeNotesStore())  # type: ignore[arg-type]
        assert jarvis.can_do("manage notes")
        jarvis.set_notes_store(None)
        assert not jarvis.can_do("manage notes")

    def test_methods_raise_clearly_when_offline(self) -> None:
        jarvis = Jarvis()
        with pytest.raises(RuntimeError, match="notes capability"):
            jarvis.list_notes()
