"""Tests for persistent conversation: PersistedTurn, stores, and ConversationContext integration."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from jarvis.domain.conversation.conversation_context import ConversationContext
from jarvis.domain.conversation.intent import ConversationIntent
from jarvis.domain.value_objects.persisted_turn import PersistedTurn
from jarvis.infrastructure.in_memory_conversation_store import InMemoryConversationStore
from jarvis.infrastructure.sqlite_conversation_store import SqliteConversationStore

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
_JAN_15 = datetime(2026, 1, 15, tzinfo=UTC)
_FEB_1 = datetime(2026, 2, 1, tzinfo=UTC)
_FEB_15 = datetime(2026, 2, 15, tzinfo=UTC)


def _turn(
    speaker: str = "companion",
    text: str = "hello",
    timestamp: datetime | None = None,
    intent: ConversationIntent | None = None,
) -> PersistedTurn:
    return PersistedTurn(
        speaker=speaker,
        text=text,
        timestamp=timestamp or _EPOCH,
        intent=intent,
    )


# --- PersistedTurn tests ---

class TestPersistedTurn:
    def test_requires_speaker_and_text(self) -> None:
        turn = _turn("companion", "hello")
        assert turn.speaker == "companion"
        assert turn.text == "hello"

    def test_assigned_turn_id_when_none(self) -> None:
        turn = _turn()
        assert turn.turn_id

    def test_uses_provided_turn_id(self) -> None:
        turn = PersistedTurn(speaker="companion", text="hi", turn_id="t1")
        assert turn.turn_id == "t1"

    def test_timestamp_default_now(self) -> None:
        turn = _turn()
        assert turn.timestamp is not None

    def test_intent_optional(self) -> None:
        turn = _turn(intent=ConversationIntent.GREETING)
        assert turn.intent == ConversationIntent.GREETING


# --- InMemoryConversationStore tests ---

class TestInMemoryConversationStore:
    def test_record_and_recent(self) -> None:
        store = InMemoryConversationStore()
        store.record_turn(_turn(text="hello"))
        store.record_turn(_turn(text="world"))
        turns = store.recent_turns()
        assert len(turns) == 2
        assert turns[0].text == "hello"
        assert turns[1].text == "world"

    def test_recent_with_limit(self) -> None:
        store = InMemoryConversationStore()
        store.record_turn(_turn(text="a"))
        store.record_turn(_turn(text="b"))
        store.record_turn(_turn(text="c"))
        turns = store.recent_turns(limit=2)
        assert len(turns) == 2
        assert turns[0].text == "b"

    def test_turns_in_range(self) -> None:
        store = InMemoryConversationStore()
        store.record_turn(_turn(text="jan", timestamp=_JAN_15))
        store.record_turn(_turn(text="feb", timestamp=_FEB_15))
        store.record_turn(_turn(text="mar", timestamp=datetime(2026, 3, 1, tzinfo=UTC)))
        turns = store.turns_in_range(_FEB_1, datetime(2026, 3, 1, tzinfo=UTC))
        assert len(turns) == 2

    def test_turns_about(self) -> None:
        store = InMemoryConversationStore()
        store.record_turn(_turn(text="dark mode config"))
        store.record_turn(_turn(text="dark mode toggle"))
        store.record_turn(_turn(text="light theme"))
        turns = store.turns_about("dark")
        assert len(turns) == 2


# --- SqliteConversationStore tests ---

class TestSqliteConversationStore:
    def _make_store(self) -> SqliteConversationStore:
        conn = sqlite3.connect(":memory:")
        return SqliteConversationStore(conn)

    def test_record_and_recent(self) -> None:
        store = self._make_store()
        store.record_turn(_turn(text="hello"))
        store.record_turn(_turn(text="world"))
        turns = store.recent_turns()
        assert len(turns) == 2

    def test_persistence(self) -> None:
        conn = sqlite3.connect(":memory:")
        store1 = SqliteConversationStore(conn)
        store1.record_turn(_turn(text="persisted"))
        store2 = SqliteConversationStore(conn)
        turns = store2.recent_turns()
        assert len(turns) == 1
        assert turns[0].text == "persisted"

    def test_turns_in_range(self) -> None:
        store = self._make_store()
        store.record_turn(_turn(text="jan", timestamp=_JAN_15))
        store.record_turn(_turn(text="feb", timestamp=_FEB_15))
        turns = store.turns_in_range(_FEB_1, datetime(2026, 3, 1, tzinfo=UTC))
        assert len(turns) == 1

    def test_turns_about(self) -> None:
        store = self._make_store()
        store.record_turn(_turn(text="dark mode config"))
        store.record_turn(_turn(text="light theme"))
        turns = store.turns_about("dark")
        assert len(turns) == 1


# --- ConversationContext integration tests ---

class TestConversationContextPersistence:
    def test_record_persists_to_repository(self) -> None:
        repo = InMemoryConversationStore()
        ctx = ConversationContext(repository=repo)
        ctx.record("companion", "hello")
        ctx.record("jarvis", "hi there")
        turns = repo.recent_turns()
        assert len(turns) == 2
        assert turns[0].speaker == "companion"
        assert turns[1].speaker == "jarvis"

    def test_record_with_intent(self) -> None:
        repo = InMemoryConversationStore()
        ctx = ConversationContext(repository=repo)
        ctx.record("companion", "hola", intent=ConversationIntent.GREETING)
        turns = repo.recent_turns()
        assert len(turns) == 1
        assert turns[0].intent == ConversationIntent.GREETING

    def test_no_repository_still_works(self) -> None:
        ctx = ConversationContext()
        ctx.record("companion", "hello")
        assert not ctx.is_empty()

    def test_empty_text_not_persisted(self) -> None:
        repo = InMemoryConversationStore()
        ctx = ConversationContext(repository=repo)
        ctx.record("companion", "   ")
        assert repo.recent_turns() == ()
