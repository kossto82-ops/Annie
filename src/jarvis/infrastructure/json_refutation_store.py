"""File-backed RefutationRepository (survives a restart, Vision §3, §21).

Persists the reflective cycle's counterexamples to a JSON file so a hypothesis
Jarvis has dethroned stays dethroned across restarts. Pairs are stored as a list
of ``[observation, belief statement]`` entries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonRefutationStore:
    """Refuted (observation, belief) pairs persisted to a JSON file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._pairs: set[tuple[str, str]] = set()
        self._load()

    def add(self, observation: str, belief_statement: str) -> None:
        self._pairs.add((observation, belief_statement))
        self._flush()

    def all(self) -> frozenset[tuple[str, str]]:
        return frozenset(self._pairs)

    def _load(self) -> None:
        if not self._path.exists():
            return
        raw: Any = json.loads(self._path.read_text(encoding="utf-8"))
        self._pairs = {(entry[0], entry[1]) for entry in raw}

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [[observation, belief] for observation, belief in sorted(self._pairs)]
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
