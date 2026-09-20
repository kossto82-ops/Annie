"""SqliteBeliefStore: a BeliefRepository on a real database (Vision §3, D10).

The repository contract says *store the evidence, never a truth flag*: this
store keeps each belief as a JSON payload in a SQLite table keyed by its
statement, and rehydrates on load exactly like the JSON store -- confidence and
stability are re-derived from the recorded evidence on every read, never
persisted as an assertion (Vision §10, §22).

Unlike the file store, persistence is a real transactional commit (SQLite's
durability, not an atomic file dance). Live belief objects are cached in memory
so that, within a session, retrieval returns the same object and evidence
accumulates -- the same session semantics as the in-memory and JSON stores. The
weighting policy is not stored; a reloaded belief derives weight with the
configured policy.

The table name is validated against a fixed whitelist, so the caller's choice of
*which* belief table (beliefs / companion / actions / reversibility / goals /
subgoals / needs) can never shape the SQL.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from jarvis.domain.entities.belief import Belief
from jarvis.domain.repositories.belief_repository import belief_registry
from jarvis.domain.services.evidence_weighting import (
    DEFAULT_WEIGHTING,
    EvidenceWeightingPolicy,
)
from jarvis.infrastructure.json_belief_store import (
    deserialise_belief,
    serialise_belief,
)

_BELIEF_TABLES = frozenset(
    {"beliefs", "companion", "actions", "reversibility", "goals", "subgoals", "needs"}
)


class SqliteBeliefStore:
    """A belief store in a SQLite table, keyed by statement, rehydrated from evidence."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        table: str = "beliefs",
        weighting_policy: EvidenceWeightingPolicy | None = None,
    ) -> None:
        if table not in _BELIEF_TABLES:
            raise ValueError(f"unknown belief table {table!r}")
        self._conn = connection
        self._table = table
        self._weighting_policy = weighting_policy or DEFAULT_WEIGHTING
        self._by_statement: dict[str, Belief] = {}
        self._ensure_schema()
        self._load()

    def get_by_topic(self, topic: str) -> Belief | None:
        return belief_registry(self._by_statement.values()).get(topic)

    def get_by_statement(self, statement: str) -> Belief | None:
        return self._by_statement.get(statement)

    def save(self, belief: Belief) -> None:
        self._retire_superseded_row(belief)
        self._by_statement[belief.statement] = belief
        payload = json.dumps(serialise_belief(belief), separators=(",", ":"))
        self._conn.execute(
            f'INSERT INTO "{self._table}" (statement, payload) VALUES (?, ?) '
            f"ON CONFLICT(statement) DO UPDATE SET payload = excluded.payload",
            (belief.statement, payload),
        )
        self._conn.commit()

    def _retire_superseded_row(self, belief: Belief) -> None:
        """When a revision changes a belief's statement, retire the row that
        still holds the old stance (same belief ``id``, older statement).

        Keeping both rows would let temporal resolution retreat after a restart:
        the superseded text would rehydrate as a parallel trait. The revised
        row moves to its new statement key instead.
        """
        for statement, candidate in list(self._by_statement.items()):
            if candidate.id == belief.id and statement != belief.statement:
                del self._by_statement[statement]
                self._conn.execute(
                    f'DELETE FROM "{self._table}" WHERE statement = ?', (statement,)
                )
                return

    def all_beliefs(self) -> tuple[Belief, ...]:
        return tuple(self._by_statement.values())

    def beliefs_formed_between(
        self, start: datetime, end: datetime
    ) -> tuple[Belief, ...]:
        return tuple(
            b for b in self._by_statement.values()
            if start <= b.formed_at <= end
        )

    def beliefs_about(self, subject_pattern: str) -> tuple[Belief, ...]:
        pattern_lower = subject_pattern.lower()
        return tuple(
            b for b in self._by_statement.values()
            if pattern_lower in b.statement.lower()
        )

    def forget(self, statement: str) -> bool:
        if statement not in self._by_statement:
            return False
        del self._by_statement[statement]
        self._conn.execute(
            f'DELETE FROM "{self._table}" WHERE statement = ?', (statement,)
        )
        self._conn.commit()
        return True

    def _ensure_schema(self) -> None:
        self._conn.execute(
            f'CREATE TABLE IF NOT EXISTS "{self._table}" '
            "(statement TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )

    def _load(self) -> None:
        rows: list[tuple[Any, ...]] = self._conn.execute(
            f'SELECT payload FROM "{self._table}"'
        ).fetchall()
        for (payload,) in rows:
            belief = deserialise_belief(json.loads(payload), self._weighting_policy)
            self._by_statement[belief.statement] = belief