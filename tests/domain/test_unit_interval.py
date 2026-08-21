"""Tests for the shared UnitInterval base and its distinct subtypes."""

from __future__ import annotations

import pytest

from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.domain.value_objects.unit_interval import UnitInterval


class TestSharedValidation:
    @pytest.mark.parametrize("factory", [Confidence, TemporalStability])
    @pytest.mark.parametrize("bad", [-0.1, 1.1])
    def test_out_of_range_is_rejected_for_every_subtype(
        self, factory: type[UnitInterval], bad: float
    ) -> None:
        with pytest.raises(ValueError):
            factory(bad)

    @pytest.mark.parametrize("factory", [Confidence, TemporalStability])
    def test_nan_is_rejected(self, factory: type[UnitInterval]) -> None:
        with pytest.raises(ValueError):
            factory(float("nan"))

    @pytest.mark.parametrize("factory", [Confidence, TemporalStability])
    def test_bool_is_rejected(self, factory: type[UnitInterval]) -> None:
        with pytest.raises(TypeError):
            factory(True)  # type: ignore[arg-type]


class TestDistinctTypes:
    def test_both_are_unit_intervals(self) -> None:
        assert isinstance(Confidence(0.5), UnitInterval)
        assert isinstance(TemporalStability(0.5), UnitInterval)

    def test_confidence_and_stability_are_not_interchangeable(self) -> None:
        # Same magnitude, different axis -> never equal (Vision §10).
        assert Confidence(0.5) != TemporalStability(0.5)
        assert not isinstance(Confidence(0.5), TemporalStability)
