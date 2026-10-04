"""Tests for cognitive energy: an episode has a cost (Vision §15, §14)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis import Jarvis
from jarvis.domain.enums.attention import Attention
from jarvis.domain.enums.deliberation_value import DeliberationValue
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.energy_costs import EnergyCosts
from jarvis.domain.value_objects.energy_recovery import EnergyRecovery
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


class TestEnergyRecovery:
    """Wall-clock energy recovery closes a §15 leftover (Increment 184).

    With an ``EnergyRecovery`` profile and an injected clock, the budget refills
    linearly over quiet time, so conserving turns off on its own -- rest becomes
    optional, never automatic, and past spend is never forgiven.
    """

    def _wired(self, budget: int = 10, minutes: int = 120) -> tuple[Jarvis, dict[str, datetime]]:
        probe = {"current": _EPOCH}
        jarvis = Jarvis(
            energy_budget=budget,
            energy_recovery=EnergyRecovery(full_recovery_minutes=minutes),
            energy_clock=lambda: probe["current"],
        )
        return jarvis, probe

    def test_default_jarvis_has_no_recovery_profile(self) -> None:
        assert Jarvis().energy_recovery() is None

    def test_without_a_budget_recovery_is_inert(self) -> None:
        jarvis = Jarvis(energy_recovery=EnergyRecovery())
        assert jarvis.energy_remaining() is None
        assert jarvis.is_conserving() is False

    def test_recovery_refills_the_budget_over_time(self) -> None:
        jarvis, probe = self._wired()  # 10 budget over 120 minutes
        jarvis.think("a")  # a FULL episode spends 3
        assert jarvis.energy_remaining() == 7
        probe["current"] = _EPOCH + timedelta(minutes=30)  # 25% of the window
        assert jarvis.energy_remaining() == 9
        probe["current"] = _EPOCH + timedelta(minutes=60)  # enough to refill fully
        assert jarvis.energy_remaining() == 10

    def test_recovery_never_exceeds_the_budget(self) -> None:
        jarvis, probe = self._wired()
        jarvis.think("a")
        probe["current"] = _EPOCH + timedelta(hours=12)
        assert jarvis.energy_remaining() == 10

    def test_recovery_turns_off_conserving_on_its_own(self) -> None:
        jarvis, probe = self._wired(budget=6, minutes=2)
        jarvis.think("a")
        jarvis.think("b")  # two FULL episodes drain below the cost of one more
        assert jarvis.is_conserving() is True  # 0 < full cost 3
        probe["current"] = _EPOCH + timedelta(minutes=1)  # half the window back -> 3
        assert jarvis.is_conserving() is False

    def test_spent_history_never_rewinds_while_the_budget_recovers(self) -> None:
        jarvis, probe = self._wired()
        jarvis.think("a")
        before = jarvis.energy_spent()
        probe["current"] = _EPOCH + timedelta(hours=12)
        assert jarvis.energy_remaining() == 10  # budget fully back
        assert jarvis.energy_spent() == before  # cumulative spend is untouched

    def test_charge_after_recovery_does_not_double_count(self) -> None:
        jarvis, probe = self._wired()
        jarvis.think("a")  # 7 left
        probe["current"] = _EPOCH + timedelta(minutes=30)  # reading reconciles first
        assert jarvis.energy_remaining() == 9
        jarvis.think("b")  # charges from the reconciled 9 -> 6
        assert jarvis.energy_remaining() == 6

    def test_fractional_recovery_accumulates(self) -> None:
        jarvis, probe = self._wired(budget=10, minutes=60)  # 1 point per 6 minutes
        jarvis.think("a")  # 7 left
        probe["current"] = _EPOCH + timedelta(minutes=1)  # 1/6 of a point: held
        assert jarvis.energy_remaining() == 7
        probe["current"] = _EPOCH + timedelta(minutes=7)  # a whole point lands
        assert jarvis.energy_remaining() == 8

    def test_rest_resets_the_recovery_baseline(self) -> None:
        jarvis, probe = self._wired()
        jarvis.think("a")  # 7 left
        jarvis.rest()  # already full, so the refill must not keep growing or re-tick
        assert jarvis.energy_remaining() == 10
        probe["current"] = _EPOCH + timedelta(minutes=30)
        assert jarvis.energy_remaining() == 10

    def test_set_energy_recovery_swaps_the_profile_at_runtime(self) -> None:
        jarvis = Jarvis(energy_budget=10)
        assert jarvis.energy_recovery() is None
        jarvis.set_energy_recovery(EnergyRecovery(full_recovery_minutes=5))
        assert jarvis.energy_recovery() is not None
        jarvis.set_energy_recovery(None)
        assert jarvis.energy_recovery() is None


class TestDeliberationValue:
    def test_default_stance_is_normal(self) -> None:
        assert Jarvis().deliberation_value() is DeliberationValue.NORMAL

    def test_set_deliberation_value_swaps_the_stance(self) -> None:
        jarvis = Jarvis()
        jarvis.set_deliberation_value(DeliberationValue.CHEAP)
        assert jarvis.deliberation_value() is DeliberationValue.CHEAP

    def test_cheap_default_answers_a_novel_problem_briefly(self) -> None:
        # With no new evidence, a CHEAP deliberation shouldn't run the full lifecycle:
        # a simple problem should not trigger an unnecessarily expensive process.
        jarvis = Jarvis(deliberation_value=DeliberationValue.CHEAP)
        episode = jarvis.think("a novel question")
        assert episode.attention is Attention.BRIEF

    def test_cheap_default_never_drops_new_evidence(self) -> None:
        jarvis = Jarvis(deliberation_value=DeliberationValue.CHEAP)
        piece = Evidence(
            content="a reason",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(0.9),
        )
        episode = jarvis.think("is it so?", evidence=[piece])
        assert episode.attention is Attention.FULL

    def test_high_value_keeps_full_even_under_conserve(self) -> None:
        jarvis = Jarvis(energy_budget=2, deliberation_value=DeliberationValue.HIGH)
        assert jarvis.is_conserving() is True
        episode = jarvis.think("a novel question")
        assert episode.attention is Attention.FULL

    def test_a_percall_value_overrides_the_stance(self) -> None:
        jarvis = Jarvis(deliberation_value=DeliberationValue.CHEAP)
        episode = jarvis.think("a novel question", value=DeliberationValue.HIGH)
        assert episode.attention is Attention.FULL

    def test_a_cheap_deliberation_charges_brief_cost(self) -> None:
        jarvis = Jarvis()
        jarvis.consider(
            "is it so?",
            {
                "yes": [
                    Evidence(
                        content="e1",
                        source=EvidenceSource.USER_STATEMENT,
                        weight=Confidence(0.9),
                    )
                ]
            },
            value=DeliberationValue.CHEAP,
        )
        assert jarvis.energy_spent() == EnergyCosts().brief

    def test_a_high_value_deliberation_charges_full_cost(self) -> None:
        jarvis = Jarvis()
        jarvis.consider(
            "is it so?",
            {
                "yes": [
                    Evidence(
                        content="e1",
                        source=EvidenceSource.USER_STATEMENT,
                        weight=Confidence(0.9),
                    )
                ]
            },
            value=DeliberationValue.HIGH,
        )
        assert jarvis.energy_spent() == EnergyCosts().full

    def test_deliberation_records_the_charged_attention(self) -> None:
        jarvis = Jarvis()
        cheap = jarvis.consider(
            "is it so?",
            {"yes": []},
            value=DeliberationValue.CHEAP,
        )
        high = jarvis.consider(
            "is it so?",
            {"no": []},
            value=DeliberationValue.HIGH,
        )
        assert cheap.attention is Attention.BRIEF
        assert high.attention is Attention.FULL

    def test_state_summary_reports_nothing_new_for_energy(self) -> None:
        jarvis = Jarvis(deliberation_value=DeliberationValue.CHEAP)
        summary = jarvis.state_summary()
        assert summary.energy_spent == jarvis.energy_spent()
