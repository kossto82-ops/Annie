"""SQLite-backed ConversationRepository.

Stores conversation turns in a SQLite table with timestamps and intent,
supporting temporal queries and subject-based search.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from jarvis.domain.conversation.intent import ConversationIntent
from jarvis.domain.value_objects.persisted_turn import PersistedTurn


def _serialise_turn(turn: PersistedTurn) -> dict[str, Any]:
    return {
        "turn_id": turn.turn_id,
        "speaker": turn.speaker,
        "text": turn.text,
        "timestamp": turn.timestamp.isoformat(),
        "intent": turn.intent.value if turn.intent is not None else None,
    }


def _deserialise_turn(data: dict[str, Any]) -> PersistedTurn:
    intent = None
    if data.get("intent") is not None:
        intent = ConversationIntent(data["intent"])
    return PersistedTurn(
        speaker=data["speaker"],
        text=data["text"],
        timestamp=datetime.fromisoformat(data["timestamp"]),
        intent=intent,
        turn_id=data["turn_id"],
    )


class SqliteConversationStore:
    """A conversation store backed by SQLite."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._turns: list[PersistedTurn] = []
        self._ensure_schema()
        self._load()

    def record_turn(self, turn: PersistedTurn) -> None:
        self._turns.append(turn)
        payload = json.dumps(_serialise_turn(turn), separators=(",", ":"))
        self._conn.execute(
            "INSERT INTO conversation_turns (turn_id, payload) VALUES (?, ?) "
            "ON CONFLICT(turn_id) DO UPDATE SET payload = excluded.payload",
            (turn.turn_id, payload),
        )
        self._conn.commit()

    def recent_turns(self, limit: int = 20) -> tuple[PersistedTurn, ...]:
        return tuple(self._turns[-limit:])

    def turns_in_range(
        self, start: datetime, end: datetime
    ) -> tuple[PersistedTurn, ...]:
        return tuple(
            t for t in self._turns
            if start <= t.timestamp <= end
        )

    def turns_about(
        self, subject: str, limit: int = 10
    ) -> tuple[PersistedTurn, ...]:
        subject_lower = subject.lower()
        matches = [
            t for t in self._turns
            if subject_lower in t.text.lower()
        ]
        return tuple(matches[-limit:])

    def _ensure_schema(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS conversation_turns "
            "(turn_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_turns_timestamp "
            "ON conversation_turns(turn_id)"
        )
        self._conn.commit()

    def _load(self) -> None:
        for row in self._conn.execute(
            "SELECT payload FROM conversation_turns"
        ):
            self._turns.append(_deserialise_turn(json.loads(row[0])))
