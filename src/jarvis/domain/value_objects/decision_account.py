"""DecisionAccount: a grounded answer to "why did we decide this?".

Built from persisted episode records, never fabricated. Recorded history
(the decision text, the confidence at the time, the evidence snapshot, the
reflect note) is reported *as recorded*; the live view (confidence now,
whether Jarvis would decide the same today) is re-derived from the current
belief. Alternatives and unrecorded assumptions are not reconstructed:
absence is honest, not an oversight to paper over.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from jarvis.domain.value_objects.episode_record import EvidenceSnapshot


@dataclass(frozen=True, slots=True)
class DecisionAccount:
    """What was decided, why, on what evidence -- and whether it still holds."""

    subject: str
    decision: str  # the recorded decision text
    decided_at: datetime
    confidence_then: float  # recorded conclusion confidence
    evidence_then: tuple[EvidenceSnapshot, ...]  # recorded evidence snapshot
    reflection_note: str | None  # recorded reflect-stage assessment
    confidence_now: float | None  # live belief re-derived (None: no current view)
    same_today: bool | None  # current support meets recorded support (None: undecidable)
