"""File-backed implementation of :class:`LearnedStateRepository`.

Keeps the latest justified knob adaptation in one JSON file
(``learned.json``) with crash-safe atomic writes. A missing file reads as
"nothing learned"; a corrupt or out-of-range file also reads as nothing
learned (validation failure is recovery, not a crash -- a poisoned or stale
record must never wedge a restart).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from jarvis.domain.value_objects.cognitive_knobs import CognitiveKnobs
from jarvis.domain.value_objects.learned_state import LearnedState
from jarvis.infrastructure.atomic_write import atomic_write_text


def serialise_learned_state(state: LearnedState) -> dict[str, Any]:
    return {
        "grounded_confidence": state.knobs.grounded_confidence,
        "insight_confidence": state.knobs.insight_confidence,
        "max_goal_reflections": state.knobs.max_goal_reflections,
        "reason": state.reason,
        "updated_at": state.updated_at.isoformat(),
    }


def deserialise_learned_state(data: dict[str, Any]) -> LearnedState | None:
    """Rebuild the record, or None when it fails validation (recovery)."""
    try:
        knobs = CognitiveKnobs(
            grounded_confidence=float(data["grounded_confidence"]),
            insight_confidence=float(data["insight_confidence"]),
            max_goal_reflections=int(data["max_goal_reflections"]),
        )
        reason = data["reason"]
        if not isinstance(reason, str) or not reason.strip():
            return None
        updated_at = datetime.fromisoformat(data["updated_at"])
    except (KeyError, TypeError, ValueError):
        return None
    try:
        return LearnedState(knobs=knobs, reason=reason, updated_at=updated_at)
    except ValueError:
        return None


class JsonLearnedStateStore:
    """The latest knob adaptation, persisted to a JSON file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> LearnedState | None:
        if not self._path.exists():
            return None
        try:
            raw: Any = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        return deserialise_learned_state(cast(dict[str, Any], raw))

    def save(self, state: LearnedState) -> None:
        atomic_write_text(self._path, json.dumps(serialise_learned_state(state)))

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()
