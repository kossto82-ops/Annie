"""SQLite implementation of :class:`LearnedStateRepository` (D10).

Keeps the latest justified knob adaptation in a single-row ``learned_state``
table inside the shared ``jarvis.db``, so database-backed Jarvis gets the
same learning continuity as the JSON twin, transactionally. Corrupt rows read
as "nothing learned", like the JSON store.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from jarvis.domain.value_objects.cognitive_knobs import CognitiveKnobs
from jarvis.domain.value_objects.learned_state import LearnedState


class SqliteLearnedStateStore:
    """The latest knob adaptation in the shared database."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS learned_state ("
            "id INTEGER PRIMARY KEY CHECK (id = 1), "
            "grounded_confidence REAL NOT NULL, "
            "insight_confidence REAL NOT NULL, "
            "max_goal_reflections INTEGER NOT NULL, "
            "reason TEXT NOT NULL, "
            "updated_at TEXT NOT NULL)"
        )

    def load(self) -> LearnedState | None:
        row = self._conn.execute(
            "SELECT grounded_confidence, insight_confidence, max_goal_reflections,"
            " reason, updated_at FROM learned_state WHERE id = 1"
        ).fetchone()
        if row is None:
            return None
        try:
            knobs = CognitiveKnobs(
                grounded_confidence=float(row[0]),
                insight_confidence=float(row[1]),
                max_goal_reflections=int(row[2]),
            )
            reason = row[3]
            if not isinstance(reason, str) or not reason.strip():
                return None
            return LearnedState(
                knobs=knobs, reason=reason, updated_at=datetime.fromisoformat(row[4])
            )
        except (TypeError, ValueError):
            return None

    def save(self, state: LearnedState) -> None:
        self._conn.execute(
            "INSERT INTO learned_state (id, grounded_confidence, insight_confidence,"
            " max_goal_reflections, reason, updated_at)"
            " VALUES (1, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET grounded_confidence = excluded.grounded_confidence,"
            " insight_confidence = excluded.insight_confidence,"
            " max_goal_reflections = excluded.max_goal_reflections,"
            " reason = excluded.reason, updated_at = excluded.updated_at",
            (
                state.knobs.grounded_confidence,
                state.knobs.insight_confidence,
                state.knobs.max_goal_reflections,
                state.reason,
                state.updated_at.isoformat(),
            ),
        )
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM learned_state WHERE id = 1")
        self._conn.commit()
