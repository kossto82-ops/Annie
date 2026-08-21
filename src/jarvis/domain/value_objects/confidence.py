"""Confidence: an immutable degree of belief in the interval [0.0, 1.0].

Confidence is a value object: it has no identity, it is defined solely by its
magnitude, and it is immutable. Invalid magnitudes are *rejected*, never
silently clamped -- an out-of-range value signals a defect in the caller, and
hiding it would let a belief become stronger (or weaker) than intended.

It is a :class:`UnitInterval`, but a *distinct type* from other unit-interval
magnitudes so confidence is never confused with temporal stability (Vision §10).
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.value_objects.unit_interval import UnitInterval


@dataclass(frozen=True, slots=True)
class Confidence(UnitInterval):
    """A degree of belief between 0.0 (no confidence) and 1.0 (certainty)."""

    @classmethod
    def none(cls) -> Confidence:
        """No confidence at all."""
        return cls(0.0)

    @classmethod
    def certain(cls) -> Confidence:
        """Full confidence."""
        return cls(1.0)

    def is_stronger_than(self, other: Confidence) -> bool:
        return self.value > other.value
