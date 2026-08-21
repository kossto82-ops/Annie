"""TemporalStability: how *steadily over time* a belief has been supported.

This is a deliberately separate value object from ``Confidence`` (Vision §10):
they are different dimensions and must behave differently. Confidence answers
"how strong is the evidence right now?"; stability answers "how spread out over
time is that support?". A belief can be highly confident yet unstable (a single
recent burst of evidence) -- exactly the situation Jarvis must treat with caution
to avoid overfitting to isolated events (Vision §11).

Like ``Confidence`` it is an immutable magnitude in [0, 1] that rejects invalid
input rather than clamping. The two share validation shape but not identity; a
common ``UnitInterval`` base is a candidate only once a third such type appears
(rule of three).
"""

from __future__ import annotations

from dataclasses import dataclass

_MINIMUM = 0.0
_MAXIMUM = 1.0


@dataclass(frozen=True, slots=True)
class TemporalStability:
    """How steady a belief's support has been over time, in [0.0, 1.0]."""

    value: float

    def __post_init__(self) -> None:
        if self.value is True or self.value is False:
            raise TypeError("TemporalStability must be a real number, not a bool")
        if self.value != self.value:  # NaN
            raise ValueError("TemporalStability must not be NaN")
        if not _MINIMUM <= self.value <= _MAXIMUM:
            raise ValueError(
                f"TemporalStability must be within [{_MINIMUM}, {_MAXIMUM}], got {self.value}"
            )

    @classmethod
    def none(cls) -> TemporalStability:
        """No temporal stability (e.g. a single-moment belief)."""
        return cls(_MINIMUM)

    def is_more_stable_than(self, other: TemporalStability) -> bool:
        return self.value > other.value
