"""Self-observation and introspection — Jarvis observing its own cognition.

Functions that derive self-knowledge from episode history, action learning,
and current state.  Every self-belief is *derived* from evidence, never
asserted — exactly like world beliefs (Vision §6, §31).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.services.action_advisor import recommend as recommend_stance
from jarvis.domain.services.goal_reflection import recurring_goals, reflection_effort
from jarvis.domain.services.self_observation import (
    observe_evidence_habit,
)
from jarvis.domain.services.self_observation import (
    observe_overconfidence as _observe_overconfidence_svc,
)
from jarvis.domain.services.self_observation import (
    observe_prediction_accuracy as _observe_prediction_accuracy_svc,
)
from jarvis.domain.value_objects.state_summary import LearnedAction, StateSummary

if TYPE_CHECKING:
    from jarvis.jarvis import Jarvis

# The internal identity prefix for a capability need belief (Odysseus).
_NEED_PREFIX = "I need the ability to: "


# ---------------------------------------------------------------------------
# Self-observation
# ---------------------------------------------------------------------------


def observe_self(jarvis: Jarvis):
    """Form a belief about Jarvis's own tendencies from episode history (Vision §6, §31).

    Returns ``None`` if there is too little history.  The self-belief is
    grounded in the episode history and revisable like any other belief.
    """
    return observe_evidence_habit(
        jarvis.episodes.history(),
        knobs=jarvis._knobs,
        policy=jarvis._default_belief_policy,
    )


def observe_oc(jarvis: Jarvis):
    """A belief about whether Jarvis concludes confidently on thin evidence (Vision §6, §11).

    Returns ``None`` if there is too little grounded history.
    """
    return _observe_overconfidence_svc(
        jarvis.episodes.history(),
        knobs=jarvis._knobs,
        policy=jarvis._default_belief_policy,
    )


def observe_prediction_accuracy(jarvis: Jarvis):
    """A belief about whether Jarvis mispredicts its actions' outcomes (Vision §31).

    Returns ``None`` if it has judged too few kinds of action.
    """
    return _observe_prediction_accuracy_svc(
        jarvis.actions.all_beliefs(),
        knobs=jarvis._knobs,
        policy=jarvis._default_belief_policy,
    )


def self_beliefs(jarvis: Jarvis):
    """Every self-tendency Jarvis currently holds about its own cognition (Vision §6).

    The ones it has enough history to judge.
    """
    candidates = (
        observe_self(jarvis),
        observe_oc(jarvis),
        observe_prediction_accuracy(jarvis),
    )
    return tuple(belief for belief in candidates if belief is not None)


# ---------------------------------------------------------------------------
# Goal helpers used by introspect
# ---------------------------------------------------------------------------


def _goal_statement(goal_statement: str) -> str:
    return f"The goal '{goal_statement}' is reachable"


def _belief_about_goal(jarvis: Jarvis, goal_statement: str):
    """What Jarvis has learned about whether a goal of this kind is reachable."""
    return jarvis._goals.get_by_statement(_goal_statement(goal_statement))


def _reachability_note(jarvis: Jarvis, goal_statement: str) -> str:
    """A truthful annotation of what Jarvis has learned about reaching a goal."""
    belief = _belief_about_goal(jarvis, goal_statement)
    if belief is None:
        return ""
    confidence = belief.confidence.value
    if confidence >= 0.5:
        return f" — I have learned I can reach this (confidence {confidence:.2f})"
    note = f" — I have not reliably reached this yet (confidence {confidence:.2f})"
    effort = reflection_effort(jarvis.episodes.history(), goal_statement)
    if effort > 0:
        times = "time" if effort == 1 else "times"
        note += f", and have turned it over {effort} {times}"
    return note


def _progress_note(jarvis: Jarvis, goal_statement: str) -> str:
    """A truthful annotation of how many of a goal's known parts are reached."""
    reached, known = _goal_progress(jarvis, goal_statement)
    if known == 0:
        return ""
    return f" ({reached} of {known} parts reached)"


def _goal_progress(jarvis: Jarvis, parent: str) -> tuple[int, int]:
    """How far along a decomposed goal is, as ``(parts reached, parts known)``."""
    suffix = f"' is a part of '{parent}'"
    children = [
        belief
        for belief in jarvis._subgoals.all_beliefs()
        if belief.statement.endswith(suffix)
    ]
    reached = sum(1 for belief in children if belief.explain().supporting)
    return (reached, len(children))


# ---------------------------------------------------------------------------
# Action summary helper
# ---------------------------------------------------------------------------


def _action_description(statement: str) -> str:
    return statement.removeprefix(
        "My predictions about the action '"
    ).removesuffix("' hold")


def _summarise_action(jarvis: Jarvis, statement: str, confidence: float) -> LearnedAction:
    description = _action_description(statement)
    return LearnedAction(
        description=description,
        confidence=confidence,
        stance=recommend_action_by_description(jarvis, description).stance,
    )


# ---------------------------------------------------------------------------
# recommend_action_by_description (used by _summarise_action and by the facade)
# ---------------------------------------------------------------------------


def recommend_action_by_description(jarvis: Jarvis, description: str):
    """Recommend a stance for a *remembered* kind of action (Vision §28)."""
    outcome = jarvis.actions.get_by_statement(_action_statement(description))
    reversible = _believed_reversible(jarvis, description)
    return recommend_stance(outcome, reversible=reversible)


def _action_statement(description: str) -> str:
    return f"My predictions about the action '{description}' hold"


def _believed_reversible(jarvis: Jarvis, description: str) -> bool:
    statement = _reversibility_statement(description)
    belief = jarvis._reversibility.get_by_statement(statement)
    return belief is not None and belief.confidence.value >= 0.5


def _reversibility_statement(description: str) -> str:
    return f"The action '{description}' is reversible"


# ---------------------------------------------------------------------------
# Introspection
# ---------------------------------------------------------------------------


def introspect(jarvis: Jarvis) -> str:
    """A plain-language account of who Jarvis is, assembled from real state.

    Personality emerges from the actual state, not a prompt (Vision §29).
    Every line traces to a real belief — nothing invented.
    """
    lines = ["This is what I currently understand about myself and my companion."]

    tendencies = [
        belief for belief in self_beliefs(jarvis) if belief.confidence.value > 0.0
    ]
    if tendencies:
        lines.append("About myself:")
        for belief in sorted(
            tendencies, key=lambda b: b.confidence.value, reverse=True
        ):
            lines.append("  - " + belief.explain().narrate())
    else:
        lines.append(
            "About myself: I have not yet noticed any consistent tendencies."
        )

    companion = jarvis.companion.summarise()
    if companion:
        lines.append("About my companion:")
        lines.extend("  - " + line for line in companion)
    else:
        lines.append("About my companion: I do not yet know much about them.")

    recurring = recurring_goals(jarvis.episodes.history())
    if recurring:
        lines.append("What I keep returning to:")
        for goal, count in recurring:
            lines.append(
                f"  - {goal} ({count} times)"
                f"{_reachability_note(jarvis, goal)}{_progress_note(jarvis, goal)}"
            )

    acquired = [
        capability
        for capability in jarvis._capabilities.all_capabilities()
        if capability.status is CapabilityStatus.ACQUIRED
    ]
    if acquired:
        lines.append("What I can now do:")
        for capability in acquired:
            lines.append(f"  - {capability.description}")

    episodes = len(jarvis.episodes.history())
    lines.append(
        f"This rests on {episodes} past episode(s); everything here is "
        "provisional and open to revision."
    )
    if jarvis.is_conserving():
        lines.append(
            "I am low on energy right now, so I am thinking briefly to conserve."
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# State summary
# ---------------------------------------------------------------------------


def state_summary(jarvis: Jarvis) -> StateSummary:
    """A compact, immutable snapshot of everything Jarvis currently holds.

    Every field traces to real state (Vision §21).
    """
    return StateSummary(
        episode_count=len(jarvis.episodes.history()),
        self_tendencies=tuple(
            (belief.statement, belief.confidence.value)
            for belief in self_beliefs(jarvis)
            if belief.confidence.value > 0.0
        ),
        companion_traits=tuple(
            (belief.statement, belief.confidence.value)
            for belief in jarvis.companion.beliefs()
        ),
        learned_actions=tuple(
            _summarise_action(jarvis, belief.statement, belief.confidence.value)
            for belief in jarvis.actions.all_beliefs()
        ),
        recurring_goals=recurring_goals(jarvis.episodes.history()),
        energy_spent=jarvis._energy_spent,
        capabilities=tuple(
            (capability.name, capability.status.value)
            for capability in jarvis._capabilities.all_capabilities()
        ),
        capability_needs=tuple(
            (statement.removeprefix(_NEED_PREFIX), confidence.value)
            for statement, confidence in _capability_needs(jarvis)
        ),
    )


def _capability_needs(jarvis: Jarvis):
    """The capability needs Jarvis has recognised, with derived confidence."""
    needs = [
        (belief.statement, belief.confidence)
        for belief in jarvis._needs.all_beliefs()
    ]
    needs.sort(key=lambda pair: pair[1].value, reverse=True)
    return tuple(needs)
