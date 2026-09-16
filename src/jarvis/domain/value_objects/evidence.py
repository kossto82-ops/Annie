"""Evidence: an immutable record of something observed that bears on a belief.

Evidence is a value object -- a fact that was observed does not change once
recorded (Vision §8, §22: memory preserves experience). Each piece carries its
own provenance and a weight describing how strongly it bears on a belief, plus
whether it *supports* or *contradicts* that belief. Contradiction is not an
error to be hidden; it is information (Vision §18).

``provenance`` is optional structured origin for *externally gathered* claims
(URL, provider/backend, retrieved_at): it keeps "where did this come from and
when" recoverable after the claim enters a belief, without flattening it into
narration text (Vision §8). Internal/companion evidence carries ``None`` and is
unchanged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence

if TYPE_CHECKING:
    from jarvis.domain.value_objects.evidence_provenance import EvidenceProvenance


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class Evidence:
    """A single, immutable piece of evidence bearing on a belief."""

    content: str
    source: EvidenceSource
    weight: Confidence
    supports: bool = True
    is_neutral: bool = False
    context: str | None = None
    provenance: EvidenceProvenance | None = None
    observed_at: datetime = field(default_factory=_now)
    id: str = field(default_factory=_new_id)

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise ValueError("Evidence requires non-empty content")
        # Zero-weight evidence bears on nothing and would only add noise.
        if self.weight.value <= 0.0:
            raise ValueError("Evidence must carry a positive weight")

    @property
    def contradicts(self) -> bool:
        return not self.supports
