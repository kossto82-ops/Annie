"""Tests for goals attached to episodes (Vision §12, §26)."""

from __future__ import annotations

import pytest

from jarvis import Jarvis
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.goal_reflection import recurring_goals
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.goal import Goal
from jarvis.domain.value_objects.temporal_stability import TemporalStability


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
