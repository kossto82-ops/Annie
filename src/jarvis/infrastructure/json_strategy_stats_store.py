"""File-backed implementation of :class:`StrategyStatsRepository`.

Keeps the last 100 retrieval outcomes in one JSON file
(``retrieval_strategy.json``) with crash-safe atomic writes. A missing or
unreadable record reads as "nothing recorded" (validation failure is
recovery, not a crash -- a poisoned record must never wedge a restart).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from jarvis.domain.value_objects.retrieval_strategy import (
    RetrievalStrategy,
    RetrievalStrategyStats,
    StrategyOutcome,
)
from jarvis.infrastructure.atomic_write import atomic_write_text


def serialise_strategy_stats(stats: RetrievalStrategyStats) -> dict[str, Any]:
    return {
        "outcomes": [
            {"strategy": outcome.strategy.value, "success": outcome.success, "query": outcome.query}
            for outcome in stats.outcomes
        ]
    }


def deserialise_strategy_stats(data: dict[str, Any]) -> RetrievalStrategyStats | None:
    """Rebuild the record, or None when it fails validation (recovery)."""
    raw_outcomes = data.get("outcomes")
    if not isinstance(raw_outcomes, list):
        return None
    raw_list = cast(list[Any], raw_outcomes)
    outcomes: list[StrategyOutcome] = []
    for raw_item in raw_list:
        if not isinstance(raw_item, dict):
            return None
        item = cast(dict[str, Any], raw_item)
        raw_strategy = item.get("strategy")
        try:
            strategy = RetrievalStrategy(raw_strategy)
        except (TypeError, ValueError):
            return None
        success = item.get("success")
        if not isinstance(success, bool):
            return None
        query = item.get("query", "")
        if not isinstance(query, str) or not isinstance(raw_strategy, str):
            return None
        outcomes.append(StrategyOutcome(strategy=strategy, success=success, query=query))
    return RetrievalStrategyStats(outcomes=tuple(outcomes))


class JsonStrategyStatsStore:
    """The bounded retrieval-strategy record, persisted to a JSON file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> RetrievalStrategyStats | None:
        if not self._path.exists():
            return None
        try:
            raw: Any = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        return deserialise_strategy_stats(cast(dict[str, Any], raw))

    def save(self, stats: RetrievalStrategyStats) -> None:
        atomic_write_text(self._path, json.dumps(serialise_strategy_stats(stats)))

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()