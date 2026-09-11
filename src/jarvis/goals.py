"""Goal tracking — recording outcomes, decomposing structure, learning reachability.

Goals are asserted by the companion and learned through outcomes (Vision §26).
Jarvis tracks reachability beliefs and goal decomposition (parts), and learns
from the companion's help on stuck goals (Vision §18).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.goal_reflection import (
    recurring_goals,
    reflection_effort,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.goal import Goal

if TYPE_CHECKING:
    from jarvis.domain.entities.belief import Belief
    from jarvis.jarvis import Jarvis


# ---------------------------------------------------------------------------
# Statement formatters
# ---------------------------------------------------------------------------


def _goal_statement(goal_statement: str) -> str:
    return f"The goal '{goal_statement}' is reachable"


def _subgoal_statement(parent: str, child: str) -> str:
    return f"The goal '{child}' is a part of '{parent}'"


# ---------------------------------------------------------------------------
# Core goal functions
# ---------------------------------------------------------------------------


def mark_goal_reached(jarvis: Jarvis, goal: Goal, reached: bool = True) -> Belief:
    """Record that a goal was (or was not) reached, and learn from it (Vision §26, §27).

    The companion asserts the outcome -- Jarvis does not evaluate the goal's
    ``success_criterion`` itself yet.
    """
    statement = _goal_statement(goal.statement)
    belief = jarvis._goals.get_by_statement(statement) or jarvis._fresh_belief(statement)
    outcome = "reached" if reached else "not reached"
    belief.add_evidence(
        Evidence(
            content=f"goal '{goal.statement}' was {outcome}",
            source=EvidenceSource.ACTION_OUTCOME,
            weight=Confidence(1.0),
            supports=reached,
            context=goal.success_criterion,
        )
    )
    jarvis._goals.save(belief)
    for event in belief.pull_events():
        jarvis.nervous_system.publish(event)
    jarvis.nervous_system.dispatch()

    if goal.part_of is not None:
        _credit_parent(jarvis, goal.part_of, goal.statement, reached)
    return belief


def _credit_parent(jarvis: Jarvis, parent: str, child: str, reached: bool) -> None:
    statement = _goal_statement(parent)
    belief = jarvis._goals.get_by_statement(statement) or jarvis._fresh_belief(statement)
    outcome = "reached" if reached else "not reached"
    belief.add_evidence(
        Evidence(
            content=f"its part '{child}' was {outcome}",
            source=EvidenceSource.DIRECT_OBSERVATION,
            weight=Confidence(1.0),
            supports=reached,
        )
    )
    jarvis._goals.save(belief)
    for event in belief.pull_events():
        jarvis.nervous_system.publish(event)
    jarvis.nervous_system.dispatch()
    _record_subgoal_link(jarvis, parent, child, reached)


def _record_subgoal_link(jarvis: Jarvis, parent: str, child: str, reached: bool) -> None:
    """Make the parent→child structure queryable (Vision §26)."""
    statement = _subgoal_statement(parent, child)
    belief = jarvis._subgoals.get_by_statement(statement) or jarvis._fresh_belief(statement)
    outcome = "reached" if reached else "not reached"
    belief.add_evidence(
        Evidence(
            content=f"'{child}' was {outcome}",
            source=EvidenceSource.DIRECT_OBSERVATION,
            weight=Confidence(1.0),
            supports=reached,
        )
    )
    belief.pull_events()
    jarvis._subgoals.save(belief)


def sub_goals(jarvis: Jarvis, parent: str) -> tuple[str, ...]:
    """The parts recorded for ``parent`` (Vision §26), in the order first seen."""
    prefix = "The goal '"
    suffix = f"' is a part of '{parent}'"
    return tuple(
        belief.statement[len(prefix) : -len(suffix)]
        for belief in jarvis._subgoals.all_beliefs()
        if belief.statement.endswith(suffix)
    )


def _first_unreached_part(jarvis: Jarvis, parent: str) -> str | None:
    """The first recorded part of ``parent`` never yet reached, or None."""
    prefix = "The goal '"
    suffix = f"' is a part of '{parent}'"
    for belief in jarvis._subgoals.all_beliefs():
        if belief.statement.endswith(suffix) and not belief.explain().supporting:
            return belief.statement[len(prefix) : -len(suffix)]
    return None


def goal_progress(jarvis: Jarvis, parent: str) -> tuple[int, int]:
    """How far along a decomposed goal is, as ``(parts reached, parts known)`` (Vision §26)."""
    suffix = f"' is a part of '{parent}'"
    children = [
        belief
        for belief in jarvis._subgoals.all_beliefs()
        if belief.statement.endswith(suffix)
    ]
    reached = sum(1 for belief in children if belief.explain().supporting)
    return (reached, len(children))


def receive_help(jarvis: Jarvis, goal: Goal, helpful: bool = True) -> Belief:
    """Take in the companion's guidance on a goal and learn from it (Vision §18, §26)."""
    statement = _goal_statement(goal.statement)
    belief = jarvis._goals.get_by_statement(statement) or jarvis._fresh_belief(statement)
    outcome = "helped" if helpful else "did not help"
    belief.add_evidence(
        Evidence(
            content=f"the companion's guidance on '{goal.statement}' {outcome}",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(1.0),
            supports=helpful,
            context=goal.success_criterion,
        )
    )
    jarvis._goals.save(belief)
    for event in belief.pull_events():
        jarvis.nervous_system.publish(event)
    jarvis.nervous_system.dispatch()

    jarvis._record_companion(
        "is helpful when I am stuck",
        Evidence(
            content=f"the companion's guidance on '{goal.statement}' {outcome}",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(1.0),
            supports=helpful,
        ),
    )

    if helpful:
        part = _first_unreached_part(jarvis, goal.statement)
        if part is not None:
            _credit_helped_part(jarvis, goal.statement, part)
    return belief


def _credit_helped_part(jarvis: Jarvis, parent: str, part: str) -> None:
    statement = _goal_statement(part)
    belief = jarvis._goals.get_by_statement(statement) or jarvis._fresh_belief(statement)
    belief.add_evidence(
        Evidence(
            content=f"the companion's guidance helped reach the part '{part}'",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(1.0),
            supports=True,
        )
    )
    jarvis._goals.save(belief)
    for event in belief.pull_events():
        jarvis.nervous_system.publish(event)
    jarvis.nervous_system.dispatch()
    _record_subgoal_link(jarvis, parent, part, True)


def belief_about_goal(jarvis: Jarvis, goal: Goal | str) -> Belief | None:
    """What Jarvis has learned about whether a goal is reachable (Vision §26)."""
    statement = goal.statement if isinstance(goal, Goal) else goal
    return jarvis._goals.get_by_statement(_goal_statement(statement))


def is_stuck_goal(jarvis: Jarvis, goal_statement: str) -> bool:
    """True when Jarvis has *learned* this goal is not reliably reachable."""
    belief = belief_about_goal(jarvis, goal_statement)
    return belief is not None and belief.confidence.value < 0.5


def is_open_stuck_goal(jarvis: Jarvis, goal_statement: str) -> bool:
    """A stuck goal still worth wondering about."""
    effort = reflection_effort(jarvis.episodes.history(), goal_statement)
    return (
        is_stuck_goal(jarvis, goal_statement)
        and effort < jarvis._knobs.max_goal_reflections
    )


def is_exhausted_stuck_goal(jarvis: Jarvis, goal_statement: str) -> bool:
    """A stuck goal wondered about enough for now."""
    effort = reflection_effort(jarvis.episodes.history(), goal_statement)
    return (
        is_stuck_goal(jarvis, goal_statement)
        and effort >= jarvis._knobs.max_goal_reflections
    )


def stuck_goals(jarvis: Jarvis) -> tuple[str, ...]:
    """Goals Jarvis has given up wondering about alone (Vision §16, §37)."""
    return tuple(
        goal
        for goal, _ in recurring_goals(jarvis.episodes.history())
        if is_exhausted_stuck_goal(jarvis, goal)
    )


def ask_for_help(jarvis: Jarvis) -> str | None:
    """A spoken request for help with the most stuck goal, or None (Vision §18, §37)."""
    stuck = stuck_goals(jarvis)
    if not stuck:
        return None
    goal = stuck[0]
    part = _first_unreached_part(jarvis, goal)
    if part is not None:
        reached, known = goal_progress(jarvis, goal)
        detail = (
            f"I keep returning to {goal} — I've reached {reached} of {known} parts "
            f"but can't get past '{part}'"
        )
    else:
        detail = f"I keep returning to {goal} but haven't found how to reach it"
    helpful = jarvis.companion.belief_about("is helpful when I am stuck")
    if helpful is not None and helpful.confidence.value >= 0.5:
        return f"You've helped me get unstuck before — {detail}; can you help again?"
    return f"{detail} on my own — can you help?"
