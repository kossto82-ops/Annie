"""SqliteRefutationStore: a RefutationRepository on a real database (Vision §3, §21, D10).

The reflective cycle's counterexamples are memory like any other: a hypothesis
Jarvis has dethroned must stay dethroned across a restart. Each refuted
``(observation, belief statement)`` pair is a committed SQLite row; the pair is
the primary key, so re-refuting the same observation is idempotent.
"""

from __future__ import annotations

import sqlite3


class SqliteRefutationStore:
    """Refuted (observation, belief) pairs persisted in a SQLite table."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._pairs: set[tuple[str, str]] = set()
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS refutations ("
            "observation TEXT NOT NULL, "
            "belief TEXT NOT NULL, "
            "PRIMARY KEY (observation, belief))"
        )
        self._load()

    def add(self, observation: str, belief_statement: str) -> None:
        self._pairs.add((observation, belief_statement))
        self._conn.execute(
            "INSERT OR IGNORE INTO refutations (observation, belief) VALUES (?, ?)",
            (observation, belief_statement),
        )
        self._conn.commit()

    def all(self) -> frozenset[tuple[str, str]]:
        return frozenset(self._pairs)

    def _load(self) -> None:
        rows = self._conn.execute(
            "SELECT observation, belief FROM refutations"
        ).fetchall()
        self._pairs = {(observation, belief) for observation, belief in rows}