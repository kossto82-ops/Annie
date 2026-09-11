"""Cognitive cycle — thinking, perceiving, reflecting, hypothesising, acting.

The core loop that runs episodes, manages energy, and drives the reflective
cycle (Connect → Reflect → Hypothesise → Challenge → Learn → Act).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING

from jarvis.domain.aggregates.cognitive_episode import CognitiveEpisode
from jarvis.domain.conversation.conversation_context import Turn
from jarvis.domain.enums.attention import Attention
from jarvis.domain.enums.deliberation_value import DeliberationValue
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.association import find_connections
from jarvis.domain.services.hypothesis_generation import generate_hypotheses
from jarvis.domain.services.reflection import find_reflections
from jarvis.domain.value_objects.challenge import Challenge as ChallengeVO
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.connection import Connection
from jarvis.domain.value_objects.deliberation import Deliberation
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.goal import Goal
from jarvis.domain.value_objects.reflection import Reflection
from jarvis.domain.value_objects.reflective_cycle import ReflectiveCycle
from jarvis.executive.executive_controller import working_statement

if TYPE_CHECKING:
    from jarvis.domain.entities.belief import Belief
    from jarvis.domain.value_objects.action_recommendation import ActionRecommendation
    from jarvis.domain.value_objects.challenge import Challenge
    from jarvis.domain.value_objects.hypothesis_set import HypothesisSet
    from jarvis.jarvis import Jarvis


# ---------------------------------------------------------------------------
# Energy management
# ---------------------------------------------------------------------------


def charge(jarvis: Jarvis, attention: Attention) -> None:
    """Charge an episode's cognitive cost (Vision §15) and update the budget."""
    cost = jarvis._energy_costs.for_attention(attention)
    jarvis._energy_spent += cost
    if jarvis._energy_budget is not None:
        jarvis._energy_available = max(0, jarvis._energy_available - cost)


def should_conserve(jarvis: Jarvis) -> bool:
    """True when the budget is low enough that a full episode should be avoided."""
    return (
        jarvis._energy_budget is not None
        and jarvis._energy_available < jarvis._energy_costs.full
    )


def energy_spent(jarvis: Jarvis) -> int:
    """Total cognitive energy spent so far (Vision §15)."""
    return jarvis._energy_spent


def energy_remaining(jarvis: Jarvis) -> int | None:
    """Current energy left in the recoverable budget (Vision §15), or None."""
    return jarvis._energy_available if jarvis._energy_budget is not None else None


def is_conserving(jarvis: Jarvis) -> bool:
    """True when Jarvis is low enough on energy to answer briefly to conserve."""
    return should_conserve(jarvis)


def rest(jarvis: Jarvis) -> None:
    """Restore energy to full (Vision §15)."""
    if jarvis._energy_budget is not None:
        jarvis._energy_available = jarvis._energy_budget


def set_energy_budget(jarvis: Jarvis, budget: int | None) -> None:
    """Set (or clear) the recoverable energy budget at runtime (Vision §15, §40)."""
    jarvis._energy_budget = budget
    jarvis._energy_available = budget if budget is not None else 0


# ---------------------------------------------------------------------------
# Core cognitive functions
# ---------------------------------------------------------------------------


def think(
    jarvis: Jarvis,
    trigger: str,
    evidence: Iterable[Evidence] = (),
    goal: Goal | None = None,
    conversation: tuple[Turn, ...] = (),
    value: DeliberationValue | None = None,
) -> CognitiveEpisode:
    """Run a cognitive episode for ``trigger``, grounded in ``evidence``."""
    episode = CognitiveEpisode(trigger=trigger, goal=goal)
    return run_episode(jarvis, episode, evidence, conversation=conversation, value=value)


def run_episode(
    jarvis: Jarvis,
    episode: CognitiveEpisode,
    evidence: Iterable[Evidence] = (),
    conversation: tuple[Turn, ...] = (),
    value: DeliberationValue | None = None,
) -> CognitiveEpisode:
    """Run an episode through the executive and charge its cognitive cost."""
    depth = jarvis._deliberation_value if value is None else value
    result = jarvis._executive.run(
        episode,
        evidence,
        conserve=should_conserve(jarvis),
        conversation=conversation,
        value=depth,
    )
    charge(jarvis, episode.attention)
    return result


def perceive(
    jarvis: Jarvis,
    observation: str,
    trigger: str | None = None,
    goal: Goal | None = None,
) -> CognitiveEpisode:
    """Perceive a raw observation and reason over what it yields (Vision §32, §8)."""
    evidence = jarvis._perception.perceive(observation)
    return think(jarvis, trigger or observation, evidence=evidence, goal=goal)


def perceive_all(
    jarvis: Jarvis,
    observations: Iterable[str],
    trigger: str | None = None,
    goal: Goal | None = None,
) -> CognitiveEpisode:
    """Perceive a stream of observations and reason over all of it at once."""
    seen = list(observations)
    evidence = tuple(
        piece for observation in seen for piece in jarvis._perception.perceive(observation)
    )
    resolved = trigger if trigger is not None else (seen[0] if seen else "")
    return think(jarvis, resolved, evidence=evidence, goal=goal)


def consider(
    jarvis: Jarvis,
    observation: str,
    options: Mapping[str, Sequence[Evidence]],
    value: DeliberationValue | None = None,
) -> Deliberation:
    """Weigh competing explanations for ``observation`` (Vision §17)."""
    depth = jarvis._deliberation_value if value is None else value
    deliberation = jarvis._executive.deliberate(observation, options, value=depth)
    jarvis._charge(deliberation.attention)
    return deliberation


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------


def connections(jarvis: Jarvis) -> tuple[Connection, ...]:
    """The belief network's strongest connections (Vision §31)."""
    return find_connections(list(jarvis.beliefs.all_beliefs()))


def related_beliefs_fn(jarvis: Jarvis, trigger: str) -> tuple[Connection, ...]:
    """Beliefs connected to ``trigger`` in the belief network."""
    statement = working_statement(trigger)
    return tuple(
        connection
        for connection in find_connections(list(jarvis.beliefs.all_beliefs()))
        if connection.involves(statement)
    )


# ---------------------------------------------------------------------------
# Reflective cycle
# ---------------------------------------------------------------------------


def reflect(jarvis: Jarvis) -> tuple[Reflection, ...]:
    """Look across the belief web and notice load-bearing observations."""
    return find_reflections(list(jarvis.beliefs.all_beliefs()), jarvis._refutations.all())


def hypothesise(jarvis: Jarvis) -> HypothesisSet | None:
    """Brew a hypothesis from reflection (Vision §17, §31), or None."""
    hypotheses = generate_hypotheses(reflect(jarvis))
    if hypotheses is not None:
        hypotheses.pull_events()
    return hypotheses


def challenge(jarvis: Jarvis) -> Challenge | None:
    """Name what would refute the leading hypothesis (Vision §11, §17, §37)."""
    hypotheses = hypothesise(jarvis)
    if hypotheses is None:
        return None
    leading = hypotheses.leading()
    if leading is None:
        return None
    finding = reflect(jarvis)[0]
    target = finding.beliefs[0]
    falsifier = (
        f'if "{target}" would still hold without "{finding.observation}", '
        "then it is not the common cause after all."
    )
    return ChallengeVO(
        hypothesis=leading.statement,
        observation=finding.observation,
        falsifier=falsifier,
        beliefs=finding.beliefs,
        confidence=leading.confidence,
        stability=leading.stability,
    )


def learn_from_reflection(jarvis: Jarvis) -> Belief | None:
    """Adopt a reflective insight that survived challenge as a belief."""
    hypotheses = hypothesise(jarvis)
    if hypotheses is None:
        return None
    leading = hypotheses.leading()
    if (
        leading is None
        or "common cause" not in leading.statement
        or leading.confidence.value < jarvis._knobs.insight_confidence
    ):
        return None
    finding = reflect(jarvis)[0]
    evidence = [
        Evidence(
            content=f"a belief rests on it: {statement}",
            source=EvidenceSource.SYSTEM_OBSERVATION,
            weight=Confidence(1.0),
        )
        for statement in finding.beliefs
    ]
    return think(
        jarvis,
        _insight_trigger(finding.observation),
        evidence=evidence,
    ).working_belief


def _insight_trigger(observation: str) -> str:
    return f'"{observation}" is a common cause behind several of my beliefs'


def act_on_insight(jarvis: Jarvis) -> ActionRecommendation | None:
    """Let a learned insight reach behaviour (Vision §27, §28, §31)."""
    from jarvis.actions import recommend_action as _recommend_action
    from jarvis.domain.value_objects.action import Action as ActionVO
    for finding in reflect(jarvis):
        statement = working_statement(_insight_trigger(finding.observation))
        belief = jarvis.beliefs.get_by_statement(statement)
        if belief is not None and belief.confidence.value >= jarvis._knobs.insight_confidence:
            action = ActionVO(
                description=f'verify that "{finding.observation}" still holds',
                expected="the observation is confirmed",
                confidence=belief.confidence,
                reversible=True,
            )
            return _recommend_action(jarvis, action)
    return None


def reflect_cycle(jarvis: Jarvis) -> ReflectiveCycle:
    """Run the whole reflective cycle once and report what it produced."""
    conns = connections(jarvis)
    reflections = reflect(jarvis)
    reflection = reflections[0] if reflections else None
    hypotheses = hypothesise(jarvis)
    leading = hypotheses.leading() if hypotheses is not None else None
    chal = challenge(jarvis)
    learned = learn_from_reflection(jarvis)
    action = act_on_insight(jarvis)
    capability_proposals = tuple(
        cap.name for cap in jarvis.auto_scout_gaps()
    )
    return ReflectiveCycle(
        connections=conns,
        reflection=reflection,
        hypothesis=leading.statement if leading is not None else None,
        challenge=chal,
        learned=learned.statement if learned is not None else None,
        action=action,
        capability_proposals=capability_proposals,
    )


def refute(jarvis: Jarvis, observation: str, belief_statement: str) -> None:
    """Record that a belief would hold *without* an observation."""
    jarvis._refutations.add(observation, belief_statement)
