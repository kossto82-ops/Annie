"""File-backed implementation of :class:`ConversationRepository` (Vision §3).

Persists conversation turns to a JSON file with crash-safe atomic writes, so
short-term dialogue context can be rehydrated after a restart. A missing file
reads as empty; a corrupt file also reads as empty (recovery, not a crash).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from jarvis.domain.conversation.intent import ConversationIntent
from jarvis.domain.value_objects.persisted_turn import PersistedTurn
from jarvis.infrastructure.atomic_write import atomic_write_text


def serialise_turn(turn: PersistedTurn) -> dict[str, Any]:
    return {
        "speaker": turn.speaker,
        "text": turn.text,
        "timestamp": turn.timestamp.isoformat(),
        "intent": turn.intent.value if turn.intent is not None else None,
        "turn_id": turn.turn_id,
    }


def deserialise_turn(data: dict[str, Any]) -> PersistedTurn | None:
    """Rebuild a turn, or None when the record is malformed (recovery)."""
    try:
        text = data["text"]
        speaker = data["speaker"]
        if not isinstance(text, str) or not text.strip():
            return None
        if speaker not in ("companion", "jarvis"):
            return None
        intent_raw = data.get("intent")
        intent = ConversationIntent(intent_raw) if intent_raw is not None else None
        return PersistedTurn(
            speaker=speaker,
            text=text,
            timestamp=datetime.fromisoformat(data["timestamp"]),
            intent=intent,
            turn_id=str(data.get("turn_id") or ""),
        )
    except (KeyError, TypeError, ValueError):
        return None


class JsonConversationStore:
    """Conversation turns persisted to a JSON file, oldest first."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._turns: list[PersistedTurn] = []
        self._load()

    def record_turn(self, turn: PersistedTurn) -> None:
        self._turns.append(turn)
        self._flush()

    def recent_turns(self, limit: int = 20) -> tuple[PersistedTurn, ...]:
        return tuple(self._turns[-limit:])

    def turns_in_range(
        self, start: datetime, end: datetime
    ) -> tuple[PersistedTurn, ...]:
        return tuple(t for t in self._turns if start <= t.timestamp <= end)

    def turns_about(
        self, subject: str, limit: int = 10
    ) -> tuple[PersistedTurn, ...]:
        subject_lower = subject.lower()
        matches = [t for t in self._turns if subject_lower in t.text.lower()]
        return tuple(matches[-limit:])

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw: Any = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, list):
            return
        for entry in cast(list[Any], raw):
            if isinstance(entry, dict):
                turn = deserialise_turn(cast(dict[str, Any], entry))
                if turn is not None:
                    self._turns.append(turn)

    def _flush(self) -> None:
        atomic_write_text(
            self._path, json.dumps([serialise_turn(t) for t in self._turns])
        )
