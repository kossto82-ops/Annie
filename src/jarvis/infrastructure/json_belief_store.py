"""File-backed implementation of :class:`BeliefRepository` (Vision §3, §21).

Gives Jarvis continuity across restarts: beliefs are serialised to a JSON file
*with their evidence and provenance*, and rehydrated on load. Memory is not truth
(Vision §22): only the evidence is stored -- confidence and stability are
re-derived from it when a belief is read back, never persisted as an assertion.

Live belief objects are cached in memory so that, within a session, retrieval
returns the same object and evidence accumulates (as with the in-memory store).
The weighting policy is not serialised; a reloaded belief uses the default.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _serialise_evidence(evidence: Evidence) -> dict[str, Any]:
    return {
        "content": evidence.content,
        "source": evidence.source.value,
        "weight": evidence.weight.value,
        "supports": evidence.supports,
        "context": evidence.context,
        "observed_at": evidence.observed_at.isoformat(),
        "id": evidence.id,
    }


def _deserialise_evidence(data: dict[str, Any]) -> Evidence:
    return Evidence(
        content=data["content"],
        source=EvidenceSource(data["source"]),
        weight=Confidence(data["weight"]),
        supports=data["supports"],
        context=data["context"],
        observed_at=datetime.fromisoformat(data["observed_at"]),
        id=data["id"],
    )


def _serialise_belief(belief: Belief) -> dict[str, Any]:
    return {
        "statement": belief.statement,
        "id": belief.id,
        "formed_at": belief.formed_at.isoformat(),
        "evidence": [_serialise_evidence(e) for e in belief.evidence],
    }


def _deserialise_belief(data: dict[str, Any]) -> Belief:
    return Belief(
        statement=data["statement"],
        id=data["id"],
        formed_at=datetime.fromisoformat(data["formed_at"]),
        _evidence=[_deserialise_evidence(e) for e in data["evidence"]],
    )


class JsonBeliefStore:
    """A belief store persisted to a JSON file, keyed by statement."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._by_statement: dict[str, Belief] = {}
        self._load()

    def get_by_statement(self, statement: str) -> Belief | None:
        return self._by_statement.get(statement)

    def save(self, belief: Belief) -> None:
        self._by_statement[belief.statement] = belief
        self._flush()

    def all_beliefs(self) -> tuple[Belief, ...]:
        return tuple(self._by_statement.values())

    def _load(self) -> None:
        if not self._path.exists():
            return
        raw: Any = json.loads(self._path.read_text(encoding="utf-8"))
        for entry in raw:
            belief = _deserialise_belief(entry)
            self._by_statement[belief.statement] = belief

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [_serialise_belief(b) for b in self._by_statement.values()]
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
