"""TemporalStability: how *steadily over time* a belief has been supported.

This is a deliberately separate value object from ``Confidence`` (Vision §10):
they are different dimensions and must behave differently. Confidence answers
"how strong is the evidence right now?"; stability answers "how spread out over
time is that support?". A belief can be highly confident yet unstable (a single
recent burst of evidence) -- exactly the situation Jarvis must treat with caution
to avoid overfitting to isolated events (Vision §11).

It shares the [0, 1] validation of :class:`UnitInterval` but is a distinct type,
so stability and confidence can never be conflated.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.value_objects.unit_interval import UnitInterval


@dataclass(frozen=True, slots=True)
class TemporalStability(UnitInterval):
    """How steady a belief's support has been over time, in [0.0, 1.0]."""

    @classmethod
    def none(cls) -> TemporalStability:
        """No temporal stability (e.g. a single-moment belief)."""
        return cls(0.0)

    def is_more_stable_than(self, other: TemporalStability) -> bool:
        return self.value > other.value
