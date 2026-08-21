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

from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.temporal_stability import TemporalStability


def _serialise_record(record: EpisodeRecord) -> dict[str, Any]:
    return {
        "episode_id": record.episode_id,
        "trigger": record.trigger,
        "decision": record.decision,
        "working_belief_id": record.working_belief_id,
        "outcome": record.outcome.value,
        "conclusion_confidence": record.conclusion_confidence.value,
        "conclusion_stability": record.conclusion_stability.value,
        "origin": record.origin.value,
        "recorded_at": record.recorded_at.isoformat(),
        "record_id": record.record_id,
    }


def _deserialise_record(data: dict[str, Any]) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id=data["episode_id"],
        trigger=data["trigger"],
        decision=data["decision"],
        working_belief_id=data["working_belief_id"],
        outcome=EpisodeState(data["outcome"]),
        conclusion_confidence=Confidence(data["conclusion_confidence"]),
        conclusion_stability=TemporalStability(data["conclusion_stability"]),
        origin=TriggerOrigin(data["origin"]),
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

    def _load(self) -> None:
        if not self._path.exists():
            return
        raw: Any = json.loads(self._path.read_text(encoding="utf-8"))
        self._records = [_deserialise_record(entry) for entry in raw]

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [_serialise_record(r) for r in self._records]
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
