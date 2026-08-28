"""Behavioural tests for source-based evidence weighting (Vision §11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.evidence_weighting import (
    DEFAULT_WEIGHTING,
    DecayingWeightingPolicy,
    SourceWeightingPolicy,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _ev(source: EvidenceSource, weight: float = 0.8) -> Evidence:
    return Evidence(content="observation", source=source, weight=Confidence(weight))


def _aged_ev(age: timedelta, weight: float = 1.0) -> Evidence:
    return Evidence(
        content="observation",
        source=EvidenceSource.USER_STATEMENT,  # factor 1.0 -> base == raw weight
        weight=Confidence(weight),
        observed_at=_NOW - age,
    )


class TestDefaultPolicy:
    def test_explicit_confirmation_outweighs_an_isolated_observation(self) -> None:
        # Same raw weight, different source -> different contribution (Vision §11).
        confirmed = DEFAULT_WEIGHTING.effective_weight(_ev(EvidenceSource.USER_STATEMENT))
        observed = DEFAULT_WEIGHTING.effective_weight(_ev(EvidenceSource.DIRECT_OBSERVATION))
        assert confirmed > observed

    def test_repeated_behaviour_outweighs_a_single_observation(self) -> None:
        repeated = DEFAULT_WEIGHTING.effective_weight(_ev(EvidenceSource.REPEATED_BEHAVIOR))
        observed = DEFAULT_WEIGHTING.effective_weight(_ev(EvidenceSource.DIRECT_OBSERVATION))
        assert repeated > observed

    def test_effective_weight_scales_the_raw_weight(self) -> None:
        # USER_STATEMENT factor is 1.0, so effective == raw for that source.
        assert DEFAULT_WEIGHTING.effective_weight(
            _ev(EvidenceSource.USER_STATEMENT, 0.6)
        ) == 0.6

    def test_effective_weight_never_exceeds_the_raw_weight(self) -> None:
        for source in EvidenceSource:
            effective = DEFAULT_WEIGHTING.effective_weight(_ev(source, 1.0))
            assert 0.0 < effective <= 1.0


class TestCustomPolicy:
    def test_a_custom_policy_changes_the_contribution(self) -> None:
        sceptical = SourceWeightingPolicy(factors={EvidenceSource.USER_STATEMENT: 0.2})
        assert sceptical.effective_weight(_ev(EvidenceSource.USER_STATEMENT, 1.0)) == 0.2

    def test_unlisted_source_falls_back_to_a_default_factor(self) -> None:
        policy = SourceWeightingPolicy(factors={EvidenceSource.USER_STATEMENT: 1.0})
        # DIRECT_OBSERVATION not listed -> fallback, still a positive contribution.
        assert 0.0 < policy.effective_weight(_ev(EvidenceSource.DIRECT_OBSERVATION, 1.0)) < 1.0


class TestDecayingPolicy:
    def _policy(self) -> DecayingWeightingPolicy:
        return DecayingWeightingPolicy(now=lambda: _NOW, half_life=timedelta(days=30))

    def test_fresh_evidence_is_not_decayed(self) -> None:
        assert self._policy().effective_weight(_aged_ev(timedelta(0))) == pytest.approx(1.0)

    def test_one_half_life_old_evidence_counts_half(self) -> None:
        weight = self._policy().effective_weight(_aged_ev(timedelta(days=30)))
        assert weight == pytest.approx(0.5)

    def test_two_half_lives_old_evidence_counts_a_quarter(self) -> None:
        weight = self._policy().effective_weight(_aged_ev(timedelta(days=60)))
        assert weight == pytest.approx(0.25)

    def test_older_evidence_always_counts_less_than_newer(self) -> None:
        policy = self._policy()
        recent = policy.effective_weight(_aged_ev(timedelta(days=1)))
        old = policy.effective_weight(_aged_ev(timedelta(days=90)))
        assert old < recent

    def test_future_dated_evidence_is_not_boosted(self) -> None:
        # Clock skew must never make evidence count for *more* than its base weight.
        weight = self._policy().effective_weight(_aged_ev(timedelta(days=-5)))
        assert weight == pytest.approx(1.0)

    def test_decay_composes_over_the_base_source_policy(self) -> None:
        # INFERENCE base factor is 0.2; one half-life old halves it to 0.1.
        evidence = Evidence(
            content="a guess",
            source=EvidenceSource.INFERENCE,
            weight=Confidence(1.0),
            observed_at=_NOW - timedelta(days=30),
        )
        assert self._policy().effective_weight(evidence) == pytest.approx(0.1)

    def test_a_non_positive_half_life_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            DecayingWeightingPolicy(now=lambda: _NOW, half_life=timedelta(0))
