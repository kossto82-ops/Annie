"""File-backed implementation of :class:`EpisodeRepository` (Vision §3, §21).

Persists the episode history to a JSON file so Jarvis's record of its own past
cognition survives a restart. Records are immutable snapshots; the file keeps
them in the order they occurred.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.infrastructure.atomic_write import atomic_write_text


def serialise_record(record: EpisodeRecord) -> dict[str, Any]:
    return {
        "episode_id": record.episode_id,
        "trigger": record.trigger,
        "decision": record.decision,
        "working_belief_id": record.working_belief_id,
        "outcome": record.outcome.value,
        "conclusion_confidence": record.conclusion_confidence.value,
        "conclusion_stability": record.conclusion_stability.value,
        "origin": record.origin.value,
        "kind": record.kind.value,
        "goal": record.goal,
        "belief_formed_at": (
            record.belief_formed_at.isoformat() if record.belief_formed_at is not None else None
        ),
        "belief_confidence_at_end": (
            record.belief_confidence_at_end.value
            if record.belief_confidence_at_end is not None
            else None
        ),
        "recorded_at": record.recorded_at.isoformat(),
        "record_id": record.record_id,
    }


def deserialise_record(data: dict[str, Any]) -> EpisodeRecord:
    belief_formed_at = None
    if data.get("belief_formed_at") is not None:
        belief_formed_at = datetime.fromisoformat(data["belief_formed_at"])
    belief_confidence_at_end = None
    if data.get("belief_confidence_at_end") is not None:
        belief_confidence_at_end = Confidence(data["belief_confidence_at_end"])
    return EpisodeRecord(
        episode_id=data["episode_id"],
        trigger=data["trigger"],
        decision=data["decision"],
        working_belief_id=data["working_belief_id"],
        outcome=EpisodeState(data["outcome"]),
        conclusion_confidence=Confidence(data["conclusion_confidence"]),
        conclusion_stability=TemporalStability(data["conclusion_stability"]),
        origin=TriggerOrigin(data["origin"]),
        kind=EpisodeKind(data["kind"]),
        goal=data.get("goal"),
        belief_formed_at=belief_formed_at,
        belief_confidence_at_end=belief_confidence_at_end,
        recorded_at=datetime.fromisoformat(data["recorded_at"]),
        record_id=data["record_id"],
    )


class JsonEpisodeStore:
    """An ordered episode store persisted to a JSON file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._records: list[EpisodeRecord] = []
        self._load()

    def record(self, record: EpisodeRecord) -> None:
        self._records.append(record)
        self._flush()

    def history(self) -> tuple[EpisodeRecord, ...]:
        return tuple(self._records)

    def history_in_range(
        self, start: datetime, end: datetime
    ) -> tuple[EpisodeRecord, ...]:
        return tuple(
            r for r in self._records
            if start <= r.recorded_at <= end
        )

    def history_about(
        self, subject: str, start: datetime | None = None, end: datetime | None = None
    ) -> tuple[EpisodeRecord, ...]:
        subject_lower = subject.lower()
        results = []
        for r in self._records:
            if subject_lower not in r.trigger.lower():
                continue
            if start is not None and r.recorded_at < start:
                continue
            if end is not None and r.recorded_at > end:
                continue
            results.append(r)
        return tuple(results)

    def _load(self) -> None:
        if not self._path.exists():
            return
        raw: Any = json.loads(self._path.read_text(encoding="utf-8"))
        self._records = [deserialise_record(entry) for entry in raw]

    def _flush(self) -> None:
        payload = [serialise_record(r) for r in self._records]
        atomic_write_text(self._path, json.dumps(payload, indent=2))
