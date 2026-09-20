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
from typing import Any, cast

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.repositories.belief_repository import belief_registry
from jarvis.domain.services.evidence_weighting import (
    DEFAULT_WEIGHTING,
    EvidenceWeightingPolicy,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.evidence_provenance import EvidenceProvenance
from jarvis.infrastructure.atomic_write import atomic_write_text


def _serialise_provenance(
    provenance: EvidenceProvenance | None,
) -> dict[str, Any] | None:
    if provenance is None:
        return None
    return {
        "provider": provenance.provider,
        "backend": provenance.backend,
        "channel": provenance.channel,
        "url": provenance.url,
        "retrieved_at": (
            provenance.retrieved_at.isoformat()
            if provenance.retrieved_at is not None
            else None
        ),
        "published_at": (
            provenance.published_at.isoformat()
            if provenance.published_at is not None
            else None
        ),
        "updated_at": (
            provenance.updated_at.isoformat()
            if provenance.updated_at is not None
            else None
        ),
    }


def _deserialise_provenance(data: object) -> EvidenceProvenance | None:
    if not isinstance(data, dict):
        return None
    raw = cast(dict[str, object], data)

    def _s(key: str) -> str | None:
        value = raw.get(key)
        return value if isinstance(value, str) else None

    return EvidenceProvenance(
        provider=_s("provider"),
        backend=_s("backend"),
        channel=_s("channel"),
        url=_s("url"),
        retrieved_at=_maybe_dt(raw.get("retrieved_at")),
        published_at=_maybe_dt(raw.get("published_at")),
        updated_at=_maybe_dt(raw.get("updated_at")),
    )


def _maybe_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _serialise_evidence(evidence: Evidence) -> dict[str, Any]:
    return {
        "content": evidence.content,
        "source": evidence.source.value,
        "weight": evidence.weight.value,
        "supports": evidence.supports,
        "is_neutral": evidence.is_neutral,
        "context": evidence.context,
        "provenance": _serialise_provenance(evidence.provenance),
        "observed_at": evidence.observed_at.isoformat(),
        "id": evidence.id,
    }


def _deserialise_evidence(data: dict[str, Any]) -> Evidence:
    return Evidence(
        content=data["content"],
        source=EvidenceSource(data["source"]),
        weight=Confidence(data["weight"]),
        supports=data["supports"],
        is_neutral=data.get("is_neutral", False),
        context=data["context"],
        provenance=_deserialise_provenance(data.get("provenance")),
        observed_at=datetime.fromisoformat(data["observed_at"]),
        id=data["id"],
    )


def serialise_belief(belief: Belief) -> dict[str, Any]:
    return {
        "statement": belief.statement,
        "id": belief.id,
        "formed_at": belief.formed_at.isoformat(),
        "evidence": [_serialise_evidence(e) for e in belief.evidence],
        "precedents": list(belief.precedents),
    }


def deserialise_belief(
    data: dict[str, Any], policy: EvidenceWeightingPolicy
) -> Belief:
    return Belief(
        statement=data["statement"],
        id=data["id"],
        formed_at=datetime.fromisoformat(data["formed_at"]),
        weighting_policy=policy,
        _evidence=[_deserialise_evidence(e) for e in data["evidence"]],
        precedents=list(data.get("precedents", [])),
    )


class JsonBeliefStore:
    """A belief store persisted to a JSON file, keyed by statement."""

    def __init__(
        self, path: str | Path, weighting_policy: EvidenceWeightingPolicy | None = None
    ) -> None:
        self._path = Path(path)
        # Rehydrated beliefs derive confidence with this policy. Default = no decay;
        # a decaying policy makes stale evidence fade after a restart (Vision §10, §22).
        self._weighting_policy = weighting_policy or DEFAULT_WEIGHTING
        self._by_statement: dict[str, Belief] = {}
        self._load()

    def get_by_topic(self, topic: str) -> Belief | None:
        return belief_registry(self._by_statement.values()).get(topic)

    def get_by_statement(self, statement: str) -> Belief | None:
        return self._by_statement.get(statement)

    def save(self, belief: Belief) -> None:
        self._retire_superseded_row(belief)
        self._by_statement[belief.statement] = belief
        self._flush()

    def _retire_superseded_row(self, belief: Belief) -> None:
        """When a revision changes a belief's statement, retire the row that
        still holds the old stance (same belief ``id``, older statement).

        Keeping both would let the superseded text resurrect as a parallel trait
        after a restart -- temporal resolution must survive persistence.
        """
        for statement, candidate in list(self._by_statement.items()):
            if candidate.id == belief.id and statement != belief.statement:
                del self._by_statement[statement]
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
        if statement in self._by_statement:
            del self._by_statement[statement]
            self._flush()
            return True
        return False

    def _load(self) -> None:
        if not self._path.exists():
            return
        raw: Any = json.loads(self._path.read_text(encoding="utf-8"))
        for entry in raw:
            belief = deserialise_belief(entry, self._weighting_policy)
            self._by_statement[belief.statement] = belief

    def _flush(self) -> None:
        payload = [serialise_belief(b) for b in self._by_statement.values()]
        atomic_write_text(self._path, json.dumps(payload, indent=2))
