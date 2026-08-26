"""Tests for cognitive energy: an episode has a cost (Vision §15, §14)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis import Jarvis
from jarvis.domain.enums.attention import Attention
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.energy_costs import EnergyCosts
from jarvis.domain.value_objects.evidence import Evidence

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _spread_grounding() -> list[Evidence]:
    # Two strong, well-spread pieces: grounds the belief so a re-ask is BRIEF.
    return [
        Evidence(
            content="r1",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(0.9),
            observed_at=_EPOCH,
        ),
        Evidence(
            content="r2",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(0.9),
            observed_at=_EPOCH + timedelta(days=40),
        ),
    ]


class TestEnergy:
    def test_a_fresh_jarvis_has_spent_nothing(self) -> None:
        assert Jarvis().energy_spent() == 0

    def test_a_full_episode_costs_more_than_a_brief_one(self) -> None:
        jarvis = Jarvis()
        full = jarvis.think("is the plan sound?", evidence=_spread_grounding())
        after_full = jarvis.energy_spent()
        brief = jarvis.think("is the plan sound?")  # confident + no new evidence -> BRIEF
        brief_cost = jarvis.energy_spent() - after_full

        assert full.attention is Attention.FULL
        assert brief.attention is Attention.BRIEF
        assert after_full > brief_cost  # the FULL episode cost more

    def test_spent_energy_accumulates_across_episodes(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a")
        one = jarvis.energy_spent()
        jarvis.think("b")
        assert jarvis.energy_spent() == one * 2  # two FULL episodes

    def test_costs_are_configurable(self) -> None:
        jarvis = Jarvis(energy_costs=EnergyCosts(full=10, brief=2))
        jarvis.think("a")  # a FULL episode
        assert jarvis.energy_spent() == 10

    def test_energy_shows_in_the_state_summary(self) -> None:
        jarvis = Jarvis()
        assert jarvis.state_summary().energy_spent == 0
        jarvis.think("a")
        assert jarvis.state_summary().energy_spent == jarvis.energy_spent()


class TestEnergyBudget:
    def test_no_budget_means_no_conserving_and_full_episodes(self) -> None:
        jarvis = Jarvis()
        assert jarvis.energy_remaining() is None
        assert jarvis.is_conserving() is False
        assert jarvis.think("a novel question").attention is Attention.FULL

    def test_a_low_budget_makes_a_normally_full_episode_run_briefly(self) -> None:
        jarvis = Jarvis(energy_budget=2)  # below the full cost of 3
        assert jarvis.is_conserving() is True
        episode = jarvis.think("a novel question")  # would be FULL, but conserve
        assert episode.attention is Attention.BRIEF
        assert jarvis.energy_remaining() == 1  # charged the BRIEF cost

    def test_an_ample_budget_keeps_episodes_full(self) -> None:
        jarvis = Jarvis(energy_budget=100)
        assert jarvis.is_conserving() is False
        assert jarvis.think("a novel question").attention is Attention.FULL

    def test_conserving_does_not_drop_new_evidence(self) -> None:
        # Even low on energy, an episode with new evidence stays FULL to observe it.
        jarvis = Jarvis(energy_budget=1)
        from jarvis.domain.enums.evidence_source import EvidenceSource

        piece = Evidence(
            content="a reason",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(0.9),
        )
        episode = jarvis.think("is it so?", evidence=[piece])
        assert episode.attention is Attention.FULL

    def test_rest_restores_energy_and_ends_conserving(self) -> None:
        jarvis = Jarvis(energy_budget=3)
        jarvis.think("a")  # spends toward the budget
        jarvis.think("b")
        assert jarvis.is_conserving() is True  # depleted below full cost
        jarvis.rest()
        assert jarvis.energy_remaining() == 3
        assert jarvis.is_conserving() is False

    def test_conserving_is_announced_in_introspection(self) -> None:
        jarvis = Jarvis(energy_budget=1)
        assert "thinking briefly to conserve" in jarvis.introspect()
