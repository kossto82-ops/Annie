"""How much a piece of evidence actually counts, given where it came from.

Not all evidence is equal (Vision §11): explicit confirmation from the companion
should weigh strongly, repeated behaviour more than a one-off, and a lone
observation weakly. This policy turns an evidence's *raw* weight into an
*effective* weight by scaling it with a per-source factor. The raw weight and
source are never mutated -- provenance stays intact; only the contribution to
confidence changes.

The policy is a domain service and is injectable, so a different epistemic
stance can be supplied (e.g. a more sceptical Jarvis) without touching beliefs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.evidence import Evidence

# Explicit confirmation strongest; repeated behaviour above an isolated
# observation (Vision §11). Factors are tunable and live in one place (D19).
_DEFAULT_FACTORS: Mapping[EvidenceSource, float] = {
    EvidenceSource.USER_STATEMENT: 1.0,
    EvidenceSource.REPEATED_BEHAVIOR: 0.8,
    EvidenceSource.ACTION_OUTCOME: 0.7,
    EvidenceSource.SYSTEM_OBSERVATION: 0.6,
    EvidenceSource.EXTERNAL_SOURCE: 0.5,
    EvidenceSource.DIRECT_OBSERVATION: 0.5,
    # A reasoned guess is the weakest evidence: it holds a belief only faintly until
    # something real (a companion confirmation) is added (Vision §37, §38).
    EvidenceSource.INFERENCE: 0.2,
}
_UNKNOWN_FACTOR = 0.5


class EvidenceWeightingPolicy(Protocol):
    """Decides how much a piece of evidence contributes to a conclusion."""

    def effective_weight(self, evidence: Evidence) -> float:
        """Return the [0, 1] contribution of ``evidence`` after source weighting."""
        ...


def _default_factors() -> Mapping[EvidenceSource, float]:
    return _DEFAULT_FACTORS


@dataclass(frozen=True, slots=True)
class SourceWeightingPolicy:
    """Scales an evidence's raw weight by a factor chosen from its source."""

    factors: Mapping[EvidenceSource, float] = field(default_factory=_default_factors)

    def effective_weight(self, evidence: Evidence) -> float:
        factor = self.factors.get(evidence.source, _UNKNOWN_FACTOR)
        return evidence.weight.value * factor


DEFAULT_WEIGHTING = SourceWeightingPolicy()


@dataclass(frozen=True, slots=True)
class DecayingWeightingPolicy:
    """Fades an evidence's contribution as it ages -- forgetting (Vision §10, §22).

    Confidence counts evidence, but evidence should not count *forever*: a belief
    sustained only by stale observations ought to weaken until something recent
    renews it. This policy composes over a ``base`` (source) policy and multiplies its
    contribution by a recency factor that halves every ``half_life``. So a piece of
    evidence one half-life old counts half as much, two half-lives old a quarter, and
    so on -- asymptotically to zero but never negative.

    The evidence itself is never mutated (provenance stays intact, Vision §8); only its
    *contribution* fades, exactly as source weighting only scales the contribution. The
    clock is injected, so the domain stays deterministic and offline-testable, and this
    policy is opt-in -- :data:`DEFAULT_WEIGHTING` does not decay, so nothing forgets
    unless a decaying policy is explicitly wired in.
    """

    now: Callable[[], datetime]
    half_life: timedelta = timedelta(days=30)
    base: EvidenceWeightingPolicy = DEFAULT_WEIGHTING

    def __post_init__(self) -> None:
        if self.half_life.total_seconds() <= 0.0:
            raise ValueError("half_life must be a positive duration")

    def effective_weight(self, evidence: Evidence) -> float:
        base_weight = self.base.effective_weight(evidence)
        age_seconds = (self.now() - evidence.observed_at).total_seconds()
        if age_seconds <= 0.0:
            # Just-observed (or future-dated, e.g. clock skew) evidence does not decay.
            return base_weight
        recency = 0.5 ** (age_seconds / self.half_life.total_seconds())
        return base_weight * recency
