"""Action learning — declaring intentions, recording outcomes, deriving stances.

Jarvis learns about actions through expected-vs-actual outcomes (Vision §20,
§27).  Repeated matches build confidence; repeated mismatches erode it.
Reversibility is tracked separately so the autonomy policy can grade its
stance (Vision §28).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.events.action_events import ActionOutcomeRecorded
from jarvis.domain.services.action_advisor import recommend as recommend_stance
from jarvis.domain.value_objects.action import Action
from jarvis.domain.value_objects.action_recommendation import ActionRecommendation
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence

if TYPE_CHECKING:
    from jarvis.domain.entities.belief import Belief
    from jarvis.jarvis import Jarvis


# ---------------------------------------------------------------------------
# Statement formatters
# ---------------------------------------------------------------------------


def _action_statement(description: str) -> str:
    return f"My predictions about the action '{description}' hold"


def _action_description(statement: str) -> str:
    # Exact inverse of _action_statement (a controlled template, not free text).
    return statement.removeprefix(
        "My predictions about the action '"
    ).removesuffix("' hold")


def _reversibility_statement(description: str) -> str:
    return f"The action '{description}' is reversible"


# ---------------------------------------------------------------------------
# Core action functions
# ---------------------------------------------------------------------------


def act(
    description: str,
    expected: str,
    *,
    confidence: Confidence | None = None,
    reversible: bool = True,
) -> Action:
    """Declare an intention to act, with its expected outcome (Vision §27).

    This only *records* the intention -- it performs nothing in the world.
    Close the loop later with :func:`record_outcome`.
    """
    return Action(
        description=description,
        expected=expected,
        confidence=confidence or Confidence(0.5),
        reversible=reversible,
    )


def record_outcome(
    jarvis: Jarvis,
    action: Action,
    actual: str,
    met_expectation: bool,
) -> Belief:
    """Record what actually happened and learn from expected-vs-actual (Vision §20).

    The outcome becomes evidence for a belief about actions of this kind, so
    repeated matches build confidence and repeated mismatches erode it.
    """
    statement = _action_statement(action.description)
    belief = jarvis.actions.get_by_statement(statement) or jarvis._fresh_belief(statement)
    belief.add_evidence(
        Evidence(
            content=(
                f"acted '{action.description}': expected '{action.expected}', "
                f"got '{actual}'"
            ),
            source=EvidenceSource.ACTION_OUTCOME,
            weight=Confidence(1.0),
            supports=met_expectation,
        )
    )
    jarvis.actions.save(belief)
    _remember_reversibility(jarvis, action)
    for event in belief.pull_events():
        jarvis.nervous_system.publish(event)
    jarvis.nervous_system.publish(
        ActionOutcomeRecorded(
            action_id=action.id,
            description=action.description,
            met_expectation=met_expectation,
        )
    )
    jarvis.nervous_system.dispatch()
    return belief


def belief_about_action(jarvis: Jarvis, description: str) -> Belief | None:
    """What Jarvis believes about how actions of this kind turn out."""
    return jarvis.actions.get_by_statement(_action_statement(description))


def recommend_action(jarvis: Jarvis, action: Action) -> ActionRecommendation:
    """Recommend a stance toward ``action`` from experience (Vision §28).

    Suggests only a confidently-learned, reversible action; asks first when
    unproven or irreversible; withholds one the record contradicts.  It only
    recommends -- it performs nothing (autonomy is earned).
    """
    belief = belief_about_action(jarvis, action.description)
    return recommend_stance(belief, reversible=action.reversible)


# ---------------------------------------------------------------------------
# Reversibility tracking
# ---------------------------------------------------------------------------


def _remember_reversibility(jarvis: Jarvis, action: Action) -> None:
    statement = _reversibility_statement(action.description)
    belief = jarvis._reversibility.get_by_statement(statement) or jarvis._fresh_belief(
        statement
    )
    manner = "reversibly" if action.reversible else "irreversibly"
    belief.add_evidence(
        Evidence(
            content=f"acted '{action.description}' ({manner})",
            source=EvidenceSource.ACTION_OUTCOME,
            weight=Confidence(1.0),
            supports=action.reversible,
        )
    )
    belief.pull_events()  # bookkeeping belief -- its events are not dispatched
    jarvis._reversibility.save(belief)


def believed_reversible(jarvis: Jarvis, description: str) -> bool:
    """Whether Jarvis has learned this action kind is reversible."""
    belief = jarvis._reversibility.get_by_statement(
        _reversibility_statement(description)
    )
    return belief is not None and belief.confidence.value >= 0.5
