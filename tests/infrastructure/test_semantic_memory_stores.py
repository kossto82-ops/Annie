"""Tests for InMemorySemanticMemoryStore and SqliteSemanticMemoryStore."""

from __future__ import annotations

import sqlite3

import pytest

from jarvis.domain.entities.semantic_memory import SemanticMemory
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.in_memory_semantic_memory_store import InMemorySemanticMemoryStore
from jarvis.infrastructure.sqlite_semantic_memory_store import SqliteSemanticMemoryStore


def _mem(pattern: str, **kwargs) -> SemanticMemory:
    return SemanticMemory(pattern=pattern, **kwargs)


def _ev(content: str, supports: bool = True) -> Evidence:
    return Evidence(
        content=content,
        source=EvidenceSource.DIRECT_OBSERVATION,
        weight=Confidence(0.6),
        supports=supports,
    )


class TestInMemoryStore:
    def test_save_and_get_by_pattern(self) -> None:
        store = InMemorySemanticMemoryStore()
        sm = _mem("users prefer X")
        store.save(sm)
        assert store.get_by_pattern("users prefer X") is sm

    def test_get_by_id(self) -> None:
        store = InMemorySemanticMemoryStore()
        sm = _mem("test", id="m1")
        store.save(sm)
        assert store.get_by_id("m1") is sm

    def test_all_memories(self) -> None:
        store = InMemorySemanticMemoryStore()
        store.save(_mem("a"))
        store.save(_mem("b"))
        assert len(store.all_memories()) == 2

    def test_search_substring(self) -> None:
        store = InMemorySemanticMemoryStore()
        store.save(_mem("users prefer dark mode"))
        store.save(_mem("users prefer light mode"))
        store.save(_mem("something else entirely"))
        results = store.search("dark")
        assert len(results) == 1
        assert results[0].pattern == "users prefer dark mode"

    def test_search_orders_by_confidence(self) -> None:
        store = InMemorySemanticMemoryStore()
        sm1 = _mem("pattern A")
        sm1.add_evidence(_ev("one"))
        sm2 = _mem("pattern B")
        sm2.add_evidence(_ev("one"))
        sm2.add_evidence(_ev("two"))
        store.save(sm1)
        store.save(sm2)
        results = store.search("pattern")
        assert len(results) == 2
        # sm2 has more evidence so higher confidence
        assert results[0] is sm2

    def test_save_overwrites(self) -> None:
        store = InMemorySemanticMemoryStore()
        sm = _mem("test")
        store.save(sm)
        sm2 = _mem("test")
        store.save(sm2)
        assert store.get_by_pattern("test") is sm2


class TestSqliteStore:
    def _make_store(self) -> SqliteSemanticMemoryStore:
        conn = sqlite3.connect(":memory:")
        return SqliteSemanticMemoryStore(conn)

    def test_save_and_get_by_pattern(self) -> None:
        store = self._make_store()
        sm = _mem("users prefer X")
        store.save(sm)
        assert store.get_by_pattern("users prefer X") is sm

    def test_get_by_id(self) -> None:
        store = self._make_store()
        sm = _mem("test", id="m1")
        store.save(sm)
        assert store.get_by_id("m1") is sm

    def test_all_memories(self) -> None:
        store = self._make_store()
        store.save(_mem("a"))
        store.save(_mem("b"))
        assert len(store.all_memories()) == 2

    def test_search_substring(self) -> None:
        store = self._make_store()
        store.save(_mem("users prefer dark mode"))
        store.save(_mem("users prefer light mode"))
        results = store.search("dark")
        assert len(results) == 1

    def test_persistence_across_instances(self) -> None:
        conn = sqlite3.connect(":memory:")
        store1 = SqliteSemanticMemoryStore(conn)
        sm = _mem("persistent pattern")
        sm.add_evidence(_ev("evidence"))
        sm.pull_events()
        store1.save(sm)
        # New store on same connection
        store2 = SqliteSemanticMemoryStore(conn)
        assert store2.get_by_pattern("persistent pattern") is not None
        loaded = store2.get_by_pattern("persistent pattern")
        assert loaded is not None
        assert len(loaded.evidence) == 1

    def test_round_trip_preserves_evidence(self) -> None:
        conn = sqlite3.connect(":memory:")
        store1 = SqliteSemanticMemoryStore(conn)
        sm = _mem("test pattern")
        sm.add_evidence(_ev("support", supports=True))
        sm.add_evidence(_ev("contradict", supports=False))
        sm.pull_events()
        store1.save(sm)
        store2 = SqliteSemanticMemoryStore(conn)
        loaded = store2.get_by_pattern("test pattern")
        assert loaded is not None
        assert len(loaded.evidence) == 2
        assert loaded.reinforcement_count == 2
