"""Behavioural tests for the TemporalStability value object."""

from __future__ import annotations

import dataclasses

import pytest

from jarvis.domain.value_objects.temporal_stability import TemporalStability


class TestConstruction:
    @pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
    def test_accepts_values_within_range(self, value: float) -> None:
        assert TemporalStability(value).value == value

    @pytest.mark.parametrize("value", [-0.1, 1.1])
    def test_rejects_values_outside_range(self, value: float) -> None:
        with pytest.raises(ValueError):
            TemporalStability(value)

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError):
            TemporalStability(float("nan"))

    def test_rejects_bool(self) -> None:
        with pytest.raises(TypeError):
            TemporalStability(True)  # type: ignore[arg-type]


class TestSemantics:
    def test_none_is_zero(self) -> None:
        assert TemporalStability.none().value == 0.0

    def test_is_more_stable_than(self) -> None:
        assert TemporalStability(0.8).is_more_stable_than(TemporalStability(0.2))
        assert not TemporalStability(0.2).is_more_stable_than(TemporalStability(0.8))

    def test_is_immutable(self) -> None:
        stability = TemporalStability(0.5)
        with pytest.raises(dataclasses.FrozenInstanceError):
            stability.value = 0.9  # type: ignore[misc]
