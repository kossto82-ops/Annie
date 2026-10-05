"""TemporalStabilityProfile: the tunable knobs behind temporal stability.

Stability answers "how steadily has this been supported over time?" as a
derived [0, 1] axis, deliberately distinct from ``Confidence`` (Vision §10,
D32). The classic answer is purely *span*-based: support spread over time,
``span / (span + reference)``, where a single moment (or a single observation)
reads zero. This profile keeps that span term always on and adds two *opt-in*
enrichments -- both default off, so a bare profile reproduces the classic
span-only answer exactly (Vision §11 anti-overfit narration unchanged):

* ``count_sensitivity`` -- repeated support beyond the two observations needed
  for span lifts stability: each additional observation closes a fraction of
  the remaining distance to 1, asymptotically (a habit is steadier than two
  isolated moments).

* ``recency_half_life`` -- a stale latest observation fades the whole term by
  an exponential half-life: what was spread out once, long ago, is less
  "steadily still supported". Just-observed (or future-dated, e.g. clock skew)
  evidence does not fade.

The clock is injected (default real UTC), so the domain stays deterministic and
offline-testable. D32 deferred count/recency to the opt-in decay policy; that
still covers the *confidence* axis (``DecayingWeightingPolicy``, Vision §10,
§22), while this profile covers the *stability* axis (Increment 185, D36).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


def _utc_now() -> datetime:
    """The default "now" for recency decay — real UTC, swap-injectable."""
    return datetime.now(tz=UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class TemporalStabilityProfile:
    """How temporal stability is derived, within [0, 1] (Vision §10, §11, D36).

    ``now`` is an injectable clock (used only when ``recency_half_life`` is set).
    ``reference`` is the span that reads exactly 0.5 (``span / (span + reference)``).
    ``low_threshold`` is the caution cut-off below which narrations flag a narrow
    time window (the classic ``LOW_STABILITY_THRESHOLD``, unchanged).
    ``count_sensitivity`` in (0, 1] turns on the count lift; a non-None positive
    ``recency_half_life`` turns on the recency fade. Both default off.
    """

    now: Callable[[], datetime] = _utc_now
    reference: timedelta = timedelta(days=30)
    low_threshold: float = 0.2
    count_sensitivity: float = 0.0
    recency_half_life: timedelta | None = None

    def __post_init__(self) -> None:
        if self.reference <= timedelta(0):
            raise ValueError("reference must be a positive duration")
        if not 0.0 <= self.low_threshold <= 1.0:
            raise ValueError("low_threshold must be within [0, 1]")
        if not 0.0 <= self.count_sensitivity <= 1.0:
            raise ValueError("count_sensitivity must be within [0, 1]")
        if self.recency_half_life is not None and self.recency_half_life <= timedelta(0):
            raise ValueError("recency_half_life must be a positive duration")


# The canonical profile: span-only, exactly the pre-Increment-185 behaviour, so a
# plain Jarvis computes identical stability numbers to before.
DEFAULT_STABILITY_PROFILE = TemporalStabilityProfile()