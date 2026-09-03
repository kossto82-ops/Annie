"""Tests for the file-backed notes adapter (LocalNotesStore, Odysseus #8).

Covers `LocalNotesStore` driving an injectable ``io`` transport (offline, D8):
list/get/create/update/delete/search, persistence across reloads, and the
`build_notes_store` factory's config opt-in.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from jarvis.domain.retrieval.notes_store import NotesStore
from jarvis.infrastructure.notes_store import LocalNotesStore, build_notes_store


def _memory_io(store: dict[str, str]) -> Callable[[str, str, str], str]:
    """A fake filesystem in a dict: ``io`` behaves like read/write/delete."""

    def io(operation: str, path: str, content: str = "") -> str:
        if operation == "read":
            return store.get(path, "")
        if operation == "delete":
            store.pop(path, None)
            return ""
        store[path] = content
        return ""

    return io


class TestLocalNotesStore:
    def test_satisfies_the_notes_store_protocol(self) -> None:
        store = LocalNotesStore("/tmp", io=_memory_io({}))
        assert isinstance(store, NotesStore)

    def test_create_list_get_round_trip(self) -> None:
        backing: dict[str, str] = {}
        store = LocalNotesStore("/tmp", io=_memory_io(backing), id_factory=_ids())
        ids: list[str] = []
        for i in range(3):
            note = store.create_note(title=f"t{i}", body=f"b{i}", tags=(f"g{i}",))
            ids.append(note.id)
        assert [n.title for n in store.list_notes()] == ["t2", "t1", "t0"]
        assert store.get_note(ids[0]).body == "b0"

    def test_persists_across_new_instances(self) -> None:
        backing: dict[str, str] = {}
        first = LocalNotesStore("/tmp", io=_memory_io(backing), id_factory=_ids())
        first.create_note(title="persist me", body="hello")
        second = LocalNotesStore("/tmp", io=_memory_io(backing))
        notes = second.list_notes()
        assert len(notes) == 1
        assert notes[0].body == "hello"

    def test_update_changes_fields_and_preserves_created_at(self) -> None:
        backing: dict[str, str] = {}
        store = LocalNotesStore("/tmp", io=_memory_io(backing), id_factory=_ids())
        note = store.create_note(title="a", body="b", tags=("one",))
        updated = store.update_note(note.id, title="a2", body="b2", tags=("two",))
        assert updated.title == "a2"
        assert updated.created_at == note.created_at
        assert updated.updated_at >= note.updated_at
        assert store.get_note(note.id).tags == ("two",)

    def test_delete_removes_the_note(self) -> None:
        backing: dict[str, str] = {}
        store = LocalNotesStore("/tmp", io=_memory_io(backing), id_factory=_ids())
        note = store.create_note(title="gone", body="x")
        store.delete_note(note.id)
        assert store.list_notes() == ()
        with pytest.raises(KeyError):
            store.get_note(note.id)

    def test_search_filters_by_title_body_and_tags(self) -> None:
        backing: dict[str, str] = {}
        store = LocalNotesStore("/tmp", io=_memory_io(backing), id_factory=_ids())
        store.create_note(title="Shopping", body="milk and eggs", tags=("errands",))
        store.create_note(title="Ideas", body="nothing here", tags=())
        assert [n.title for n in store.search_notes("milk")] == ["Shopping"]
        assert [n.title for n in store.search_notes("errands")] == ["Shopping"]
        assert [n.title for n in store.search_notes("nothing here")] == ["Ideas"]
        assert store.search_notes("zzz") == ()

    def test_get_unknown_id_raises(self) -> None:
        store = LocalNotesStore("/tmp", io=_memory_io({}))
        with pytest.raises(KeyError):
            store.get_note("missing")


def _ids() -> Callable[[], str]:
    counter = iter("abcd")
    return lambda: next(counter)


class TestBuildNotesStore:
    def test_returns_none_without_directory_configuration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("JARVIS_NOTES_ROOT", raising=False)
        assert build_notes_store() is None

    def test_builds_a_wired_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("JARVIS_NOTES_ROOT", "/tmp/notes")
        store = build_notes_store()
        assert isinstance(store, LocalNotesStore)
