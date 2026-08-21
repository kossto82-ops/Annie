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

from collections.abc import Mapping
from dataclasses import dataclass, field
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
