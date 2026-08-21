"""Behavioural tests for the Evidence value object."""

from __future__ import annotations

import dataclasses
from datetime import UTC

import pytest

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _evidence(**overrides: object) -> Evidence:
    defaults: dict[str, object] = {
        "content": "the user chose the simpler design",
        "source": EvidenceSource.DIRECT_OBSERVATION,
        "weight": Confidence(0.6),
    }
    defaults.update(overrides)
    return Evidence(**defaults)  # type: ignore[arg-type]


class TestConstruction:
    def test_supports_by_default(self) -> None:
        assert _evidence().supports is True
        assert _evidence().contradicts is False

    def test_can_be_contradicting(self) -> None:
        evidence = _evidence(supports=False)
        assert evidence.contradicts is True

    def test_records_when_it_was_observed(self) -> None:
        assert _evidence().observed_at.tzinfo == UTC

    def test_rejects_empty_content(self) -> None:
        with pytest.raises(ValueError):
            _evidence(content="   ")

    def test_rejects_zero_weight(self) -> None:
        with pytest.raises(ValueError):
            _evidence(weight=Confidence(0.0))


class TestImmutability:
    def test_is_frozen(self) -> None:
        evidence = _evidence()
        with pytest.raises(dataclasses.FrozenInstanceError):
            evidence.content = "changed"  # type: ignore[misc]
