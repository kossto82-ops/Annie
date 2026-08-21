"""UnitInterval: the shared shape of an immutable magnitude in [0.0, 1.0].

Several domain magnitudes -- confidence, temporal stability -- are real numbers
bounded to [0, 1] that reject invalid input rather than clamping. This base holds
exactly that validation. Subclasses stay *distinct types* on purpose (a
Confidence is not a TemporalStability, Vision §10), so the two epistemic axes can
never be conflated; the base only removes the duplicated validation.
"""

from __future__ import annotations

from dataclasses import dataclass

_MINIMUM = 0.0
_MAXIMUM = 1.0


@dataclass(frozen=True, slots=True)
class UnitInterval:
    """An immutable real number in [0.0, 1.0]."""

    value: float

    def __post_init__(self) -> None:
        if self.value is True or self.value is False:
            raise TypeError(f"{type(self).__name__} must be a real number, not a bool")
        if self.value != self.value:  # NaN is never equal to itself
            raise ValueError(f"{type(self).__name__} must not be NaN")
        if not _MINIMUM <= self.value <= _MAXIMUM:
            raise ValueError(
                f"{type(self).__name__} must be within [{_MINIMUM}, {_MAXIMUM}], "
                f"got {self.value}"
            )
