"""A temporal-stability profile is injectable at the Jarvis root (Increment 185, D36).

The mirror of `test_weighting_policy.py` for the *stability* axis: the profile is
read-time (never persisted — it carries an injectable clock), defaults to `None`
(the classic span-only estimator), and governs every belief Jarvis creates on its
own — goals, actions, needs — plus companion traits, exactly like
`default_belief_policy`. Stored/reconstructed beliefs keep the profile they were
formed with, so nothing is silently re-derived.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.goal import Goal
from jarvis.domain.value_objects.temporal_stability_profile import (
    TemporalStabilityProfile,
)
from jarvis.jarvis import Jarvis

_NOW = datetime(2026, 3, 15, tzinfo=UTC)


def _profile(now: datetime = _NOW) -> TemporalStabilityProfile:
    return TemporalStabilityProfile(count_sensitivity=0.5, now=lambda: now)


def _evidence(days_ago: int) -> Evidence:
    return Evidence(
        content="a piece of evidence",
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(0.5),
        supports=True,
        observed_at=_NOW - timedelta(days=days_ago),
    )


def _varies_with_count(profile: TemporalStabilityProfile) -> bool:
    """True when count beyond the pair of observations moves the stability term."""
    pair = Jarvis(stability_profile=profile).fresh_belief("x")
    pair.add_evidence(_evidence(5))
    pair.add_evidence(_evidence(4))
    habit = Jarvis(stability_profile=profile).fresh_belief("y")
    for day in range(8, 4, -1):  # five observations, same one-day span
        habit.add_evidence(_evidence(day))
    return habit.stability.is_more_stable_than(pair.stability)


class TestRootStabilityProfile:
    def test_the_historical_default_is_unchanged(self) -> None:
        jarvis = Jarvis()
        assert jarvis.stability_profile() is None
        belief = jarvis.fresh_belief("the user prefers simplicity")
        assert belief.stability_profile is None
        # Span-only: two observations one day apart read 1/31.
        belief.add_evidence(_evidence(5))
        belief.add_evidence(_evidence(4))
        assert belief.stability.value == 1.0 / 31.0

    def test_an_injected_profile_governs_every_fresh_belief(self) -> None:
        profile = _profile()
        jarvis = Jarvis(stability_profile=profile)
        assert jarvis.stability_profile() == profile
        assert jarvis.fresh_belief("a fresh belief").stability_profile == profile
        assert _varies_with_count(profile)

        # Action learning flows through the same root default.
        intent = jarvis.act("tidy the room", "tidy")
        outcome = jarvis.record_outcome(intent, "tidy", True)
        assert outcome.stability_profile == profile

        # Goal reachability too.
        goal = jarvis.mark_goal_reached(Goal(statement="fetch water"))
        assert goal.stability_profile == profile

        # And companion traits through Jarvis.
        trait = jarvis.companion.observe("rises at dawn", _evidence(1))
        assert trait.stability_profile == profile

    def test_the_swap_applies_to_subsequent_creations_only(self) -> None:
        jarvis = Jarvis()
        first = jarvis.companion.observe("rises at dawn", _evidence(1))
        assert first.stability_profile is None

        profile = _profile()
        jarvis.set_stability_profile(profile)
        assert jarvis.stability_profile() == profile
        second = jarvis.companion.observe("reads at night", _evidence(1))
        assert second.stability_profile == profile
        # An existing belief is not silently re-derived.
        earlier = jarvis.companion.belief_about("rises at dawn")
        assert earlier is not None
        assert earlier.stability_profile is None

    def test_clearing_the_profile_restores_span_only(self) -> None:
        jarvis = Jarvis(stability_profile=_profile())
        jarvis.set_stability_profile(None)
        assert jarvis.stability_profile() is None
        belief = jarvis.fresh_belief("x")
        assert belief.stability_profile is None

    def test_persistent_boot_forwards_the_root_profile(self, tmp_path: Path) -> None:
        profile = _profile()
        jarvis = Jarvis.persistent(tmp_path, stability_profile=profile)
        assert jarvis.stability_profile() == profile
        belief = jarvis.fresh_belief("a fresh belief")
        assert belief.stability_profile == profile


class TestRootStabilityProfileValidation:
    def test_invalid_profiles_are_rejected_at_the_root(self) -> None:
        with pytest.raises(ValueError):
            TemporalStabilityProfile(count_sensitivity=2.0)