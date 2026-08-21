"""Behavioural tests for source-based evidence weighting (Vision §11)."""

from __future__ import annotations

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.evidence_weighting import (
    DEFAULT_WEIGHTING,
    SourceWeightingPolicy,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _ev(source: EvidenceSource, weight: float = 0.8) -> Evidence:
    return Evidence(content="observation", source=source, weight=Confidence(weight))


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
