"""Memory consolidation: identify beliefs eligible for forgetting.

When a belief's effective confidence (with decay) falls below a threshold
and it has not been reinforced recently, it becomes a candidate for
forgetting. This gives the companion agency over what to retain (Vision §10).

The consolidation service does not delete anything -- it identifies
candidates and lets the companion decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from jarvis.domain.entities.belief import Belief
from jarvis.domain.services.evidence_weighting import (
    DecayingWeightingPolicy,
    EvidenceWeightingPolicy,
)

FORGETTABLE_THRESHOLD = 0.15
STALE_AFTER = timedelta(days=90)


@dataclass(frozen=True, slots=True)
class ForgettingCandidate:
    """A belief that may be worth forgetting."""

    belief: Belief
    effective_confidence: float
    last_reinforced: datetime | None
    reason: str


class BeliefLookup(Protocol):
    """Minimal interface for looking up beliefs."""

    def all_beliefs(self) -> tuple[Belief, ...]: ...


def identify_forgetting_candidates(
    beliefs: BeliefLookup,
    *,
    now: datetime | None = None,
    threshold: float = FORGETTABLE_THRESHOLD,
    stale_after: timedelta = STALE_AFTER,
    weighting_policy: EvidenceWeightingPolicy | None = None,
) -> list[ForgettingCandidate]:
    """Return beliefs whose effective confidence has faded below threshold.

    Uses the injected weighting policy (or the belief's own) to compute
    effective confidence. Beliefs with no evidence are also candidates.
    """
    now = now or datetime.now(tz=UTC)
    candidates: list[ForgettingCandidate] = []

    for belief in beliefs.all_beliefs():
        # Compute effective confidence with the policy (always a plain float:
        # Confidence has no ordering against floats, so unwrap it immediately).
        if isinstance(weighting_policy, DecayingWeightingPolicy):
            # Use the injected decaying policy
            effective = belief.confidence_with_policy(weighting_policy).value
        else:
            effective = belief.confidence.value

        # Find last reinforcement time
        last_reinforced = None
        for e in belief.evidence:
            if last_reinforced is None or e.observed_at > last_reinforced:
                last_reinforced = e.observed_at

        # Determine eligibility
        reason = ""
        if effective < threshold:
            reason = f"effective confidence {effective:.2f} below threshold {threshold}"
        elif last_reinforced is not None and (now - last_reinforced) > stale_after:
            reason = f"not reinforced for {(now - last_reinforced).days} days"
        elif len(belief.evidence) == 0:
            reason = "no evidence"

        if reason:
            candidates.append(
                ForgettingCandidate(
                    belief=belief,
                    effective_confidence=effective,
                    last_reinforced=last_reinforced,
                    reason=reason,
                )
            )

    # Sort by effective confidence (lowest first)
    candidates.sort(key=lambda c: c.effective_confidence)
    return candidates
