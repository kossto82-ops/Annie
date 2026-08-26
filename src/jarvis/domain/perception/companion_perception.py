"""CompanionPerceptionSource: reading what an utterance reveals about the companion.

The ordinary `PerceptionSource` reads an observation into evidence about *the world*
— claims Jarvis forms beliefs about. But a companion also needs a *relational* channel:
what does what the person just said reveal about *them* (Vision §5)? That is a different
question with a different shape — it yields observations keyed to a companion *trait*,
each carrying evidence — so it gets its own seam.

The Vision §38 boundary is the same and non-negotiable: a source here may *extract
candidate observations about the companion*, it never decides. Each observation folds
into an ordinary, revisable `Belief` in the companion model, whose confidence is still
derived from evidence and which the companion can later contradict (Vision §5, §18).

Producing nothing is honest (Vision §37): an utterance that reveals nothing about the
person leaves the model untouched rather than inventing a trait.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from jarvis.domain.value_objects.evidence import Evidence


@dataclass(frozen=True, slots=True)
class CompanionObservation:
    """One thing an utterance reveals about the companion: a trait + its evidence.

    ``trait`` is a short, third-person description of the person ("is learning Spanish")
    that keys the belief in the companion model; ``evidence`` is what grounds it, exactly
    like any other evidence (weight, polarity, provenance).
    """

    trait: str
    evidence: Evidence


@runtime_checkable
class CompanionPerceptionSource(Protocol):
    """Reads an utterance into zero or more observations about the companion."""

    def read_companion(self, utterance: str) -> tuple[CompanionObservation, ...]:
        """Return what ``utterance`` reveals about the companion — empty when nothing."""
        ...
