"""Tests for Reflect: noticing load-bearing observations (Vision §19, §31)."""

from __future__ import annotations

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _ev(content: str) -> Evidence:
    return Evidence(
        content=content,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(0.9),
    )


class TestReflect:
    def test_an_observation_grounding_two_beliefs_is_noticed(self) -> None:
        jarvis = Jarvis()
        shared = "the client moved the deadline up"
        jarvis.think("is the schedule at risk?", evidence=[_ev(shared)])
        jarvis.think("should we cut scope?", evidence=[_ev(shared)])

        findings = jarvis.reflect()
        assert len(findings) == 1
        assert findings[0].observation == shared
        assert findings[0].load == 2
        assert set(findings[0].beliefs) == {
            "Working conclusion about: is the schedule at risk?",
            "Working conclusion about: should we cut scope?",
        }

    def test_isolated_beliefs_yield_no_reflection(self) -> None:
        jarvis = Jarvis()
        jarvis.think("q1", evidence=[_ev("observation A")])
        jarvis.think("q2", evidence=[_ev("observation B")])
        assert jarvis.reflect() == ()

    def test_an_evidence_free_belief_contributes_nothing(self) -> None:
        jarvis = Jarvis()
        jarvis.think("grounded twice", evidence=[_ev("shared")])
        jarvis.think("also grounded", evidence=[_ev("shared")])
        jarvis.think("empty")  # no evidence
        findings = jarvis.reflect()
        assert len(findings) == 1
        assert findings[0].load == 2

    def test_the_most_load_bearing_observation_comes_first(self) -> None:
        jarvis = Jarvis()
        heavy = "the API changed"
        light = "the logo is blue"
        jarvis.think("a", evidence=[_ev(heavy)])
        jarvis.think("b", evidence=[_ev(heavy)])
        jarvis.think("c", evidence=[_ev(heavy)])
        jarvis.think("d", evidence=[_ev(light)])
        jarvis.think("e", evidence=[_ev(light)])

        findings = jarvis.reflect()
        assert findings[0].observation == heavy and findings[0].load == 3
        assert findings[1].observation == light and findings[1].load == 2

    def test_a_reflection_can_describe_itself(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a", evidence=[_ev("the API changed")])
        jarvis.think("b", evidence=[_ev("the API changed")])
        described = jarvis.reflect()[0].describe()
        assert "the API changed" in described
        assert "load-bearing" in described


class TestHypothesise:
    def test_a_load_bearing_observation_brews_a_hypothesis(self) -> None:
        jarvis = Jarvis()
        cause = "the client moved the deadline up"
        jarvis.think("is the schedule at risk?", evidence=[_ev(cause)])
        jarvis.think("should we cut scope?", evidence=[_ev(cause)])

        hypotheses = jarvis.hypothesise()
        assert hypotheses is not None
        leading = hypotheses.leading()
        assert leading is not None
        assert cause in leading.statement
        assert "common cause" in leading.statement
        assert leading.confidence.value > 0.0

    def test_the_common_cause_leads_over_the_coincidence_null(self) -> None:
        jarvis = Jarvis()
        cause = "the API changed"
        for question in ("a", "b", "c"):
            jarvis.think(question, evidence=[_ev(cause)])

        hypotheses = jarvis.hypothesise()
        assert hypotheses is not None
        leading = hypotheses.leading()
        assert leading is not None and "common cause" in leading.statement
        # Seeded with one piece of evidence per belief resting on the observation.
        assert len(leading.evidence) == 3

    def test_nothing_load_bearing_yields_no_hypothesis(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a", evidence=[_ev("observation A")])
        jarvis.think("b", evidence=[_ev("observation B")])
        assert jarvis.hypothesise() is None

    def test_more_beliefs_on_the_observation_make_a_more_confident_hypothesis(self) -> None:
        two = Jarvis()
        two.think("a", evidence=[_ev("X")])
        two.think("b", evidence=[_ev("X")])
        three = Jarvis()
        three.think("a", evidence=[_ev("X")])
        three.think("b", evidence=[_ev("X")])
        three.think("c", evidence=[_ev("X")])

        two_leading = two.hypothesise().leading()  # type: ignore[union-attr]
        three_leading = three.hypothesise().leading()  # type: ignore[union-attr]
        assert two_leading is not None and three_leading is not None
        assert three_leading.confidence.value > two_leading.confidence.value


class TestChallenge:
    def _with_hypothesis(self) -> Jarvis:
        jarvis = Jarvis()
        cause = "the client moved the deadline up"
        for question in ("is the schedule at risk?", "should we cut scope?", "is morale ok?"):
            jarvis.think(question, evidence=[_ev(cause)])
        return jarvis

    def test_challenge_names_a_concrete_falsifier(self) -> None:
        jarvis = self._with_hypothesis()
        challenge = jarvis.challenge()
        assert challenge is not None
        assert "the client moved the deadline up" in challenge.observation
        assert "common cause" in challenge.hypothesis
        assert "would still hold without" in challenge.falsifier

    def test_no_hypothesis_means_no_challenge(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a", evidence=[_ev("observation A")])
        jarvis.think("b", evidence=[_ev("observation B")])
        assert jarvis.challenge() is None

    def test_refuting_a_belief_removes_it_from_the_pattern(self) -> None:
        jarvis = self._with_hypothesis()
        assert jarvis.reflect()[0].load == 3
        jarvis.refute(
            "the client moved the deadline up",
            "Working conclusion about: is morale ok?",
        )
        assert jarvis.reflect()[0].load == 2

    def test_refuting_enough_beliefs_dethrones_the_hypothesis(self) -> None:
        jarvis = self._with_hypothesis()
        observation = "the client moved the deadline up"
        jarvis.refute(observation, "Working conclusion about: is morale ok?")
        jarvis.refute(observation, "Working conclusion about: should we cut scope?")
        # Only one belief left on the observation — no longer a shared pattern.
        assert jarvis.reflect() == ()
        assert jarvis.hypothesise() is None
        assert jarvis.challenge() is None


class TestLearnFromReflection:
    def _with_hypothesis(self) -> Jarvis:
        jarvis = Jarvis()
        cause = "the client moved the deadline up"
        for question in ("is the schedule at risk?", "should we cut scope?", "is morale ok?"):
            jarvis.think(question, evidence=[_ev(cause)])
        return jarvis

    def test_a_surviving_hypothesis_is_adopted_as_a_belief(self) -> None:
        jarvis = self._with_hypothesis()
        belief = jarvis.learn_from_reflection()
        assert belief is not None
        assert "the client moved the deadline up" in belief.statement
        assert "common cause" in belief.statement
        assert belief.confidence.value >= 0.5

    def test_the_adopted_belief_enters_the_belief_web(self) -> None:
        jarvis = self._with_hypothesis()
        before = len(list(jarvis.beliefs.all_beliefs()))
        jarvis.learn_from_reflection()
        after = list(jarvis.beliefs.all_beliefs())
        assert len(after) == before + 1
        assert any("common cause" in b.statement for b in after)

    def test_a_dethroned_hypothesis_is_not_learned(self) -> None:
        jarvis = self._with_hypothesis()
        observation = "the client moved the deadline up"
        jarvis.refute(observation, "Working conclusion about: is morale ok?")
        jarvis.refute(observation, "Working conclusion about: should we cut scope?")
        assert jarvis.learn_from_reflection() is None

    def test_nothing_load_bearing_learns_nothing(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a", evidence=[_ev("observation A")])
        jarvis.think("b", evidence=[_ev("observation B")])
        assert jarvis.learn_from_reflection() is None


class TestReflectCycle:
    def _with_hypothesis(self) -> Jarvis:
        jarvis = Jarvis()
        cause = "the client moved the deadline up"
        for question in ("is the schedule at risk?", "should we cut scope?", "is morale ok?"):
            jarvis.think(question, evidence=[_ev(cause)])
        return jarvis

    def test_one_call_runs_every_stage(self) -> None:
        jarvis = self._with_hypothesis()
        result = jarvis.reflect_cycle()
        assert result.reflection is not None
        assert result.hypothesis is not None and "common cause" in result.hypothesis
        assert result.challenge is not None
        assert result.learned is not None and "common cause" in result.learned
        assert result.produced_insight is True
        # The learned belief is now part of the web.
        assert any("common cause" in b.statement for b in jarvis.beliefs.all_beliefs())

    def test_an_isolated_web_yields_an_empty_cycle(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a", evidence=[_ev("observation A")])
        jarvis.think("b", evidence=[_ev("observation B")])
        result = jarvis.reflect_cycle()
        assert result.reflection is None
        assert result.hypothesis is None
        assert result.challenge is None
        assert result.learned is None
        assert result.produced_insight is False

    def test_a_dethroned_hypothesis_reports_no_learning(self) -> None:
        jarvis = self._with_hypothesis()
        observation = "the client moved the deadline up"
        jarvis.refute(observation, "Working conclusion about: is morale ok?")
        jarvis.refute(observation, "Working conclusion about: should we cut scope?")
        result = jarvis.reflect_cycle()
        assert result.reflection is None
        assert result.learned is None
        assert result.produced_insight is False


class TestCuriosityWantsToReflect:
    def _with_pattern(self) -> Jarvis:
        jarvis = Jarvis()
        cause = "the client moved the deadline up"
        for question in ("is the schedule at risk?", "should we cut scope?"):
            jarvis.think(question, evidence=[_ev(cause)])
        return jarvis

    def test_an_unmined_pattern_makes_jarvis_curious_to_reflect(self) -> None:
        jarvis = self._with_pattern()
        impulse = jarvis.feel_curious()
        assert impulse is not None
        assert impulse.reflect_on == "the client moved the deadline up"
        assert "Reflect on" in impulse.trigger

    def test_an_isolated_web_raises_no_reflect_impulse(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a", evidence=[_ev("observation A")])
        jarvis.think("b", evidence=[_ev("observation B")])
        impulse = jarvis.feel_curious()
        assert impulse is None or impulse.reflect_on is None

    def test_pursuing_the_impulse_runs_the_cycle_and_quiets_it(self) -> None:
        jarvis = self._with_pattern()
        impulse = jarvis.feel_curious()
        assert impulse is not None and impulse.reflect_on is not None

        jarvis.pursue(impulse)
        # The pattern is now mined into a belief; curiosity no longer wants it.
        assert any(
            "is a common cause" in belief.statement
            for belief in jarvis.beliefs.all_beliefs()
        )
        again = jarvis.feel_curious()
        assert again is None or again.reflect_on is None


class TestActOnInsight:
    def _with_learned_insight(self) -> Jarvis:
        jarvis = Jarvis()
        cause = "the client moved the deadline up"
        for question in ("is the schedule at risk?", "should we cut scope?", "is morale ok?"):
            jarvis.think(question, evidence=[_ev(cause)])
        jarvis.learn_from_reflection()
        return jarvis

    def test_a_learned_insight_recommends_verifying_the_observation(self) -> None:
        from jarvis.domain.enums.action_stance import ActionStance

        jarvis = self._with_learned_insight()
        recommendation = jarvis.act_on_insight()
        assert recommendation is not None
        # A brand-new verify action is asked-first (autonomy is earned).
        assert recommendation.stance is ActionStance.ASK_FIRST

    def test_no_learned_insight_recommends_nothing(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a", evidence=[_ev("observation A")])
        jarvis.think("b", evidence=[_ev("observation B")])
        assert jarvis.act_on_insight() is None

    def test_an_unmined_pattern_alone_recommends_nothing(self) -> None:
        # A load-bearing pattern that has not yet been learned is not yet actionable.
        jarvis = Jarvis()
        cause = "a shared observation"
        jarvis.think("a", evidence=[_ev(cause)])
        jarvis.think("b", evidence=[_ev(cause)])
        assert jarvis.reflect() != ()
        assert jarvis.act_on_insight() is None
