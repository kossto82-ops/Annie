"""Tests for goals attached to episodes (Vision §12, §26)."""

from __future__ import annotations

import pytest

from jarvis import Jarvis
from jarvis.domain.value_objects.goal import Goal


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
