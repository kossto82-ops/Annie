"""Behavioural tests for the Confidence value object."""

from __future__ import annotations

import dataclasses

import pytest

from jarvis.domain.value_objects.confidence import Confidence


class TestConstruction:
    @pytest.mark.parametrize("value", [0.0, 0.5, 1.0, 0, 1])
    def test_accepts_values_within_range(self, value: float) -> None:
        assert Confidence(value).value == value

    @pytest.mark.parametrize("value", [-0.0001, 1.0001, -1.0, 2.0, 100])
    def test_rejects_values_outside_range(self, value: float) -> None:
        with pytest.raises(ValueError):
            Confidence(value)

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError):
            Confidence(float("nan"))

    def test_rejects_bool_disguised_as_number(self) -> None:
        with pytest.raises(TypeError):
            Confidence(True)  # type: ignore[arg-type]

    def test_rejects_non_number(self) -> None:
        with pytest.raises(TypeError):
            Confidence("0.5")  # type: ignore[arg-type]


class TestImmutability:
    def test_cannot_reassign_value(self) -> None:
        confidence = Confidence(0.5)
        with pytest.raises(dataclasses.FrozenInstanceError):
            confidence.value = 0.9  # type: ignore[misc]

    def test_equal_by_value(self) -> None:
        assert Confidence(0.3) == Confidence(0.3)
        assert Confidence(0.3) != Confidence(0.4)


class TestSemantics:
    def test_none_and_certain_endpoints(self) -> None:
        assert Confidence.none().value == 0.0
        assert Confidence.certain().value == 1.0

    def test_is_stronger_than(self) -> None:
        assert Confidence(0.8).is_stronger_than(Confidence(0.2))
        assert not Confidence(0.2).is_stronger_than(Confidence(0.8))
        assert not Confidence(0.5).is_stronger_than(Confidence(0.5))
