"""SQLite implementation of :class:`StrategyStatsRepository` (D10).

Keeps the bounded retrieval-strategy record in a ``retrieval_strategy_outcomes``
table inside the shared ``jarvis.db``, so database-backed Jarvis keeps its
routing evidence across restarts transactionally. ``save`` rewrites the table
to match the caller's record exactly; corrupt rows read as nothing recorded.
"""

from __future__ import annotations

import sqlite3

from jarvis.domain.value_objects.retrieval_strategy import (
    RetrievalStrategy,
    RetrievalStrategyStats,
    StrategyOutcome,
)

_CAPACITY = 100


class SqliteStrategyStatsStore:
    """The bounded retrieval-strategy record in the shared database."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS retrieval_strategy_outcomes ("
            "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
            "strategy TEXT NOT NULL, "
            "success INTEGER NOT NULL, "
            "query TEXT NOT NULL)"
        )

    def load(self) -> RetrievalStrategyStats | None:
        rows = self._conn.execute(
            "SELECT strategy, success, query FROM retrieval_strategy_outcomes"
            " ORDER BY seq DESC LIMIT ?",
            (_CAPACITY,),
        ).fetchall()
        if not rows:
            return None
        outcomes: list[StrategyOutcome] = []
        for row in reversed(rows):
            try:
                strategy = RetrievalStrategy(row[0])
            except (TypeError, ValueError):
                continue
            success = row[1]
            if not isinstance(success, int) or success not in (0, 1):
                continue
            query = row[2]
            if not isinstance(query, str):
                continue
            outcomes.append(
                StrategyOutcome(strategy=strategy, success=bool(success), query=query)
            )
        return RetrievalStrategyStats(outcomes=tuple(outcomes))

    def save(self, stats: RetrievalStrategyStats) -> None:
        self._conn.execute("DELETE FROM retrieval_strategy_outcomes")
        self._conn.executemany(
            "INSERT INTO retrieval_strategy_outcomes (strategy, success, query)"
            " VALUES (?, ?, ?)",
            [
                (outcome.strategy.value, int(outcome.success), outcome.query)
                for outcome in stats.outcomes
            ],
        )
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM retrieval_strategy_outcomes")
        self._conn.commit()