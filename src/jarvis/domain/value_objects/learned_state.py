"""LearnedState: the persisted trace of how experience retuned cognition.

When self-observation (or meta-observation) justifies a threshold change, the
adaptation writes through to a store as a ``LearnedState``: the adapted knobs,
the human-readable reason, and when it happened. A fresh Jarvis rehydrates the
knobs from it, so learning survives restarts instead of evaporating with the
process.

Only *justified* adaptations are stored -- the adaptation functions decide
when evidence warrants a change (bounded steps, habit-confidence gates,
drift back to baseline); this object is the durable record, never a second
decision-maker. ``CognitiveKnobs`` validates the values, so a corrupt or
hostile store entry cannot smuggle an out-of-range threshold in: loaders must
treat validation failure as "no learned state".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from jarvis.domain.value_objects.cognitive_knobs import CognitiveKnobs


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class LearnedState:
    """Adapted cognition thresholds plus why they changed and when."""

    knobs: CognitiveKnobs
    reason: str
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.reason or not self.reason.strip():
            raise ValueError("LearnedState requires a non-empty reason")
