"""Confidence: an immutable degree of belief in the interval [0.0, 1.0].

Confidence is a value object: it has no identity, it is defined solely by its
magnitude, and it is immutable. Invalid magnitudes are *rejected*, never
silently clamped -- an out-of-range value signals a defect in the caller, and
hiding it would let a belief become stronger (or weaker) than intended.
"""

from __future__ import annotations

from dataclasses import dataclass

_MINIMUM = 0.0
_MAXIMUM = 1.0


@dataclass(frozen=True, slots=True)
class Confidence:
    """A degree of belief between 0.0 (no confidence) and 1.0 (certainty)."""

    value: float

    def __post_init__(self) -> None:
        # bool is a subclass of int; a truthy/falsy flag is not a confidence.
        if self.value is True or self.value is False:
            raise TypeError("Confidence must be a real number, not a bool")
        if self.value != self.value:  # NaN is never equal to itself
            raise ValueError("Confidence must not be NaN")
        # A non-numeric value makes the range comparison raise TypeError, which
        # is the correct signal for a mistyped caller.
        if not _MINIMUM <= self.value <= _MAXIMUM:
            raise ValueError(
                f"Confidence must be within [{_MINIMUM}, {_MAXIMUM}], got {self.value}"
            )

    @classmethod
    def none(cls) -> Confidence:
        """No confidence at all."""
        return cls(_MINIMUM)

    @classmethod
    def certain(cls) -> Confidence:
        """Full confidence."""
        return cls(_MAXIMUM)

    def is_stronger_than(self, other: Confidence) -> bool:
        return self.value > other.value
