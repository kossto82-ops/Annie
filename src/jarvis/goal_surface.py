"""Goal methods: mark reached, sub-goals, progress, help, stuck goals.

The Jarvis class retains thin delegator methods that forward here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.domain.entities.belief import Belief
from jarvis.domain.value_objects.goal import Goal

if TYPE_CHECKING:
    from jarvis.jarvis import Jarvis


class GoalSurface:
    """Goal tracking surface."""

    def __init__(self, jarvis: Jarvis) -> None:
        self._jarvis = jarvis

    def mark_goal_reached(self, goal: Goal, reached: bool = True) -> Belief:
        from jarvis.goals import mark_goal_reached as _mark_goal_reached_fn
        return _mark_goal_reached_fn(self._jarvis, goal, reached)

    def sub_goals(self, parent: str) -> tuple[str, ...]:
        from jarvis.goals import sub_goals as _sub_goals_fn
        return _sub_goals_fn(self._jarvis, parent)

    def _first_unreached_part(self, parent: str) -> str | None:
        from jarvis.goals import _first_unreached_part as _fun
        return _fun(self._jarvis, parent)

    def goal_progress(self, parent: str) -> tuple[int, int]:
        from jarvis.goals import goal_progress as _goal_progress_fn
        return _goal_progress_fn(self._jarvis, parent)

    def receive_help(self, goal: Goal, helpful: bool = True) -> Belief:
        from jarvis.goals import receive_help as _receive_help_fn
        return _receive_help_fn(self._jarvis, goal, helpful)

    def belief_about_goal(self, goal: Goal | str) -> Belief | None:
        from jarvis.goals import belief_about_goal as _belief_about_goal_fn
        return _belief_about_goal_fn(self._jarvis, goal)

    @staticmethod
    def _goal_statement(goal_statement: str) -> str:
        from jarvis.goals import _goal_statement as _goal_statement_fn
        return _goal_statement_fn(goal_statement)

    def _is_stuck_goal(self, goal_statement: str) -> bool:
        from jarvis.goals import is_stuck_goal as _is_stuck_goal_fn
        return _is_stuck_goal_fn(self._jarvis, goal_statement)

    def _is_open_stuck_goal(self, goal_statement: str) -> bool:
        from jarvis.goals import is_open_stuck_goal as _is_open_stuck_goal_fn
        return _is_open_stuck_goal_fn(self._jarvis, goal_statement)

    def _is_exhausted_stuck_goal(self, goal_statement: str) -> bool:
        from jarvis.goals import is_exhausted_stuck_goal as _is_exhausted_stuck_goal_fn
        return _is_exhausted_stuck_goal_fn(self._jarvis, goal_statement)

    def _reachability_note(self, goal_statement: str) -> str:
        from jarvis.introspection import _reachability_note as _fun
        return _fun(self._jarvis, goal_statement)

    def _progress_note(self, goal_statement: str) -> str:
        from jarvis.introspection import _progress_note as _fun
        return _fun(self._jarvis, goal_statement)

    def recurring_goals(self) -> tuple[tuple[str, int], ...]:
        from jarvis.domain.services.goal_reflection import recurring_goals
        return recurring_goals(self._jarvis.episodes.history())

    def reflection_effort(self, goal_statement: str) -> int:
        from jarvis.domain.services.goal_reflection import reflection_effort
        return reflection_effort(self._jarvis.episodes.history(), goal_statement)

    def stuck_goals(self) -> tuple[str, ...]:
        from jarvis.goals import stuck_goals as _stuck_goals_fn
        return _stuck_goals_fn(self._jarvis)

    def ask_for_help(self) -> str | None:
        from jarvis.goals import ask_for_help as _ask_for_help_fn
        return _ask_for_help_fn(self._jarvis)
