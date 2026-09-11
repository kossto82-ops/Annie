"""Companion model — observing, perceiving, and explaining companion traits.

Jarvis builds a derived, revisable model of its companion from observations
(Vision §5). Each trait is a belief grounded in evidence: praise builds it,
denial contradicts it, and the companion can correct Jarvis honestly.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from jarvis.domain.events.belief_events import ContradictionDetected

if TYPE_CHECKING:
    from jarvis.domain.entities.belief import Belief
    from jarvis.domain.value_objects.evidence import Evidence
    from jarvis.jarvis import Jarvis


def observe_companion(jarvis: Jarvis, trait: str, evidence: Evidence) -> Belief:
    """Record an observation about the companion and evolve Jarvis's model of
    them (Vision §5). Returns the (revisable) belief; its events flow through
    the nervous system.
    """
    belief, _ = _record_companion(jarvis, trait, evidence)
    return belief


def perceive_about_companion(
    jarvis: Jarvis, trait: str, observation: str
) -> Belief | None:
    """Perceive an observation about the companion and let it shape the lasting
    model of them (Vision §5, §32), or None if nothing is perceived.
    """
    belief: Belief | None = None
    for piece in jarvis._perception.perceive(observation):
        belief = observe_companion(jarvis, trait, piece)
    return belief


def perceive_all_about_companion(
    jarvis: Jarvis, trait: str, observations: Iterable[str]
) -> Belief | None:
    """Perceive a stream of observations about the companion, folding each into
    the lasting model of them (Vision §5, §3), or None if nothing is perceived.
    """
    belief: Belief | None = None
    for observation in observations:
        perceived = perceive_about_companion(jarvis, trait, observation)
        if perceived is not None:
            belief = perceived
    return belief


def acknowledge_companion(
    jarvis: Jarvis, trait: str, evidence: Evidence
) -> str:
    """Record an observation and acknowledge it in conversation (Vision §18).

    When the observation contradicts a belief Jarvis actually held, it says
    so plainly -- the person has contradicted its model, and it holds the
    belief less firmly now. A first or consistent observation is just noted.
    """
    _, contradicted = _record_companion(jarvis, trait, evidence)
    if contradicted:
        return (
            f'You have contradicted what I believed about "{trait}". '
            "I may be wrong, so I am holding it less firmly now."
        )
    return f'Noted about "{trait}".'


def _record_companion(
    jarvis: Jarvis, trait: str, evidence: Evidence
) -> tuple[Belief, bool]:
    """Record evidence about a companion trait and dispatch events.

    Returns ``(belief, contradicted)`` where ``contradicted`` is True when
    the evidence contradicted an existing belief.
    """
    belief = jarvis.companion.observe(trait, evidence)
    events = jarvis.companion.pull_events()
    contradicted = any(isinstance(event, ContradictionDetected) for event in events)
    for event in events:
        jarvis.nervous_system.publish(event)
    jarvis.nervous_system.dispatch()
    return belief, contradicted


def explain_companion(jarvis: Jarvis, trait: str) -> str:
    """Explain *why* Jarvis believes ``trait`` about its companion (Vision §5, §8).

    Returns the belief's provenance narrated -- the evidence for and against
    it, its confidence, and, when contested, an honest "I may be wrong". If no
    such belief is held yet, says so plainly (Vision §37).
    """
    belief = jarvis.companion.belief_about(trait)
    if belief is None:
        return f'I don\'t hold a view on "{trait}" about my companion yet.'
    return belief.explain().narrate()


def note_companion(jarvis: Jarvis, utterance: str) -> tuple[Belief, ...]:
    """Learn about the companion from what they said (Vision §5, §38).

    The relational half of a conversation turn: the utterance is read into
    observations about the companion, and each folds into the derived, revisable
    belief about that trait -- so talking to Jarvis actually builds its model of
    *you*, not only beliefs about the world. Returns the companion beliefs that were
    touched (empty when the utterance revealed nothing, §37). It only *produces*
    evidence; confidence is still derived and the belief remains contradictable.
    """
    learned: list[Belief] = []
    for observation in jarvis._companion_perception.read_companion(utterance):
        belief, _ = _record_companion(jarvis, observation.trait, observation.evidence)
        learned.append(belief)
    return tuple(learned)
