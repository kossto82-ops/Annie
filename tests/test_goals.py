"""Tests for goals attached to episodes (Vision §12, §26)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis import Jarvis
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.goal_reflection import recurring_goals
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.goal import Goal
from jarvis.domain.value_objects.temporal_stability import TemporalStability


def _grounded_evidence() -> tuple[Evidence, ...]:
    """Two strong, well-spread supporting pieces: grounds a belief (confidence
    above the threshold) with enough temporal spread that the conclusion is not
    overconfident -- so the self-model stays quiet.
    """
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return (
        Evidence(
            content="a solid reason",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(0.9),
            observed_at=base,
        ),
        Evidence(
            content="a second solid reason later",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(0.9),
            observed_at=base + timedelta(days=40),
        ),
    )


class TestGoal:
    def test_requires_a_statement(self) -> None:
        with pytest.raises(ValueError):
            Goal(statement="  ")

    def test_may_carry_a_success_criterion(self) -> None:
        goal = Goal(statement="understand the problem", success_criterion="I can restate it")
        assert goal.success_criterion == "I can restate it"


class TestThinkWithAGoal:
    def test_an_episode_without_a_goal_has_none(self) -> None:
        assert Jarvis().think("a question").goal is None

    def test_a_goal_is_attached_to_the_episode(self) -> None:
        goal = Goal(statement="decide whether to refactor")
        episode = Jarvis().think("is the module too complex?", goal=goal)
        assert episode.goal is goal

    def test_the_decision_names_the_goal_when_present(self) -> None:
        goal = Goal(statement="decide whether to refactor")
        episode = Jarvis().think("is the module too complex?", goal=goal)
        assert episode.result is not None
        assert "decide whether to refactor" in episode.result

    def test_the_decision_is_unaffected_without_a_goal(self) -> None:
        episode = Jarvis().think("is the module too complex?")
        assert episode.result is not None
        assert "Toward" not in episode.result


class TestGoalIsRemembered:
    def test_a_goal_directed_episode_records_its_goal(self) -> None:
        jarvis = Jarvis()
        jarvis.think("is the module too complex?", goal=Goal(statement="decide to refactor"))
        record = jarvis.episodes.history()[-1]
        assert record.goal == "decide to refactor"

    def test_a_goal_less_episode_records_none(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a plain question")
        assert jarvis.episodes.history()[-1].goal is None


class TestRecurringGoals:
    def test_a_goal_pursued_repeatedly_is_surfaced_with_its_count(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="ship the parser")
        for question in ("is it too slow?", "is it too complex?", "is it well tested?"):
            jarvis.think(question, goal=goal)
        assert jarvis.recurring_goals() == (("ship the parser", 3),)

    def test_a_one_off_goal_does_not_recur(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a question", goal=Goal(statement="a passing thought"))
        jarvis.think("another", goal=Goal(statement="a passing thought"))
        assert jarvis.recurring_goals() == ()

    def test_goal_less_episodes_never_appear(self) -> None:
        jarvis = Jarvis()
        for _ in range(4):
            jarvis.think("a plain question")
        assert jarvis.recurring_goals() == ()

    def test_goals_are_ordered_by_descending_count(self) -> None:
        jarvis = Jarvis()
        for _ in range(3):
            jarvis.think("q", goal=Goal(statement="lesser"))
        for _ in range(5):
            jarvis.think("q", goal=Goal(statement="greater"))
        assert jarvis.recurring_goals() == (("greater", 5), ("lesser", 3))


class TestRecurringGoalsService:
    def test_self_directed_episodes_with_goals_are_ignored(self) -> None:
        def record(origin: TriggerOrigin) -> EpisodeRecord:
            return EpisodeRecord(
                episode_id="e",
                trigger="t",
                decision="d",
                working_belief_id="b",
                outcome=EpisodeState.COMPLETED,
                conclusion_confidence=Confidence(0.6),
                conclusion_stability=TemporalStability(0.5),
                origin=origin,
                kind=EpisodeKind.CONCLUSION,
                goal="a self goal",
            )

        history = [record(TriggerOrigin.CURIOSITY) for _ in range(4)]
        assert recurring_goals(history) == ()


class TestGoalReachability:
    def test_marking_a_goal_reached_forms_a_reachable_belief(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="ship the parser")
        assert jarvis.belief_about_goal(goal) is None
        belief = jarvis.mark_goal_reached(goal)
        assert belief.confidence.value > 0.0
        assert jarvis.belief_about_goal(goal) is belief

    def test_repeated_reaches_build_confidence_failures_erode_it(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="ship the parser")
        jarvis.mark_goal_reached(goal)
        jarvis.mark_goal_reached(goal)
        confident = jarvis.belief_about_goal(goal)
        assert confident is not None
        high = confident.confidence.value

        jarvis.mark_goal_reached(goal, reached=False)
        lowered = jarvis.belief_about_goal(goal)
        assert lowered is not None
        assert lowered.confidence.value < high

    def test_an_unmarked_goal_has_no_reachability_belief(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a question", goal=Goal(statement="never marked"))
        assert jarvis.belief_about_goal("never marked") is None

    def test_belief_about_goal_accepts_a_statement_string(self) -> None:
        jarvis = Jarvis()
        jarvis.mark_goal_reached(Goal(statement="ship the parser"))
        assert jarvis.belief_about_goal("ship the parser") is not None

    def test_reachability_survives_a_restart(self, tmp_path: Path) -> None:
        goal = Goal(statement="ship the parser")
        first = Jarvis.persistent(tmp_path)
        first.mark_goal_reached(goal)
        before = first.belief_about_goal(goal)
        assert before is not None

        restarted = Jarvis.persistent(tmp_path)
        after = restarted.belief_about_goal(goal)
        assert after is not None
        assert after.confidence.value == before.confidence.value


class TestRecurringGoalBecomesCuriosity:
    def test_a_recurring_goal_raises_curiosity_when_self_model_is_quiet(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="ship the parser")
        # Grounded, well-spread episodes keep the self-model quiet, so the
        # recurring goal is the most interesting remaining unknown.
        jarvis.think("is it correct?", evidence=_grounded_evidence(), goal=goal)
        jarvis.think("is it correct?", goal=goal)
        jarvis.think("is it correct?", goal=goal)
        assert jarvis.self_beliefs() == () or all(
            b.confidence.value == 0.0 for b in jarvis.self_beliefs()
        )
        impulse = jarvis.feel_curious()
        assert impulse is not None
        assert "ship the parser" in impulse.trigger
        assert impulse.prompted_by_belief_id is None

    def test_no_recurring_goal_raises_no_goal_curiosity(self) -> None:
        jarvis = Jarvis()
        # Same quiet self-model, but distinct goals -> nothing recurs.
        jarvis.think("is it correct?", evidence=_grounded_evidence(), goal=Goal(statement="alpha"))
        jarvis.think("is it correct?", goal=Goal(statement="beta"))
        jarvis.think("is it correct?", goal=Goal(statement="gamma"))
        assert jarvis.recurring_goals() == ()
        assert jarvis.feel_curious() is None

    def test_curiosity_prefers_a_goal_it_keeps_failing_to_reach(self) -> None:
        jarvis = Jarvis()
        reachable = Goal(statement="the easy goal")
        unreached = Goal(statement="the hard goal")
        # One grounded belief keeps the self-model quiet; both goals recur equally.
        jarvis.think("is it correct?", evidence=_grounded_evidence(), goal=reachable)
        for _ in range(2):
            jarvis.think("is it correct?", goal=reachable)
        for _ in range(3):
            jarvis.think("is it correct?", goal=unreached)
        # Two reaches ground the reachable goal above the threshold; the hard goal
        # is marked unreached, so it is the sharper tension.
        jarvis.mark_goal_reached(reachable)
        jarvis.mark_goal_reached(reachable)
        jarvis.mark_goal_reached(unreached, reached=False)

        impulse = jarvis.feel_curious()
        assert impulse is not None
        assert "the hard goal" in impulse.trigger
        assert "without reaching it" in impulse.trigger

    def test_curiosity_still_raises_a_reachable_recurring_goal(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="the easy goal")
        jarvis.think("is it correct?", evidence=_grounded_evidence(), goal=goal)
        for _ in range(2):
            jarvis.think("is it correct?", goal=goal)
        jarvis.mark_goal_reached(goal)
        jarvis.mark_goal_reached(goal)

        impulse = jarvis.feel_curious()
        assert impulse is not None
        assert "the easy goal" in impulse.trigger
        assert "without reaching it" not in impulse.trigger


class TestPursuingAGoalCuriosityRecordsIt:
    def test_pursuing_a_recurring_goal_impulse_records_the_episode_toward_it(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="the hard goal")
        jarvis.think("is it correct?", evidence=_grounded_evidence(), goal=goal)
        for _ in range(2):
            jarvis.think("is it correct?", goal=goal)
        jarvis.mark_goal_reached(goal, reached=False)

        impulse = jarvis.feel_curious()
        assert impulse is not None and impulse.goal == "the hard goal"
        jarvis.pursue(impulse)
        assert jarvis.episodes.history()[-1].goal == "the hard goal"

    def test_pursuing_a_self_tendency_impulse_records_no_goal(self) -> None:
        jarvis = Jarvis()
        # Ungrounded episodes make the evidence-habit self-belief confident, so
        # feel_curious raises a self-tendency impulse (which concerns no goal).
        for topic in ("a", "b", "c"):
            jarvis.think(f"q {topic}")
        impulse = jarvis.feel_curious()
        assert impulse is not None and impulse.goal is None
        jarvis.pursue(impulse)
        assert jarvis.episodes.history()[-1].goal is None
