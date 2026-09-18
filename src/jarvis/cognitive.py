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
from jarvis.domain.repositories.belief_repository import resolve_belief_for
from jarvis.domain.services.association import find_connections
from jarvis.domain.services.hypothesis_generation import generate_hypotheses
from jarvis.domain.services.reflection import find_reflections
from jarvis.domain.value_objects.challenge import Challenge as ChallengeVO
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.connection import Connection
from jarvis.domain.value_objects.deliberation import Deliberation
from jarvis.domain.value_objects.energy_costs import EnergyCosts
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.goal import Goal
from jarvis.domain.value_objects.reflection import Reflection
from jarvis.domain.value_objects.reflective_cycle import ReflectiveCycle
from jarvis.executive.executive_controller import working_statement

if TYPE_CHECKING:
    from jarvis.domain.aggregates.hypothesis_set import HypothesisSet
    from jarvis.domain.entities.belief import Belief
    from jarvis.domain.value_objects.action_recommendation import ActionRecommendation
    from jarvis.domain.value_objects.challenge import Challenge
    from jarvis.jarvis import Jarvis


# ---------------------------------------------------------------------------
# Energy management
# ---------------------------------------------------------------------------


class EnergyLedger:
    """Session-scoped cognitive-energy accounting (Vision §15).

    One object owns the four numbers -- price list, cumulative spend, optional
    budget and what is left of it -- so cognition, the surface and any future
    adaptation all read and mutate the same state instead of four loose
    attributes on the composition root. Behaviour is identical to the former
    inline accounting: charging accumulates spend and drains the available
    budget, ``rest()`` refills it without forgiving past spend, and ``None``
    budget means unconstrained (``remaining()`` is ``None``).
    """

    def __init__(
        self, costs: EnergyCosts | None = None, budget: int | None = None
    ) -> None:
        self.costs = costs or EnergyCosts()
        self.budget = budget
        self.spent = 0
        self.available = budget if budget is not None else 0

    def charge(self, attention: Attention) -> None:
        """Charge one episode's cognitive cost and update the budget."""
        cost = self.costs.for_attention(attention)
        self.spent += cost
        if self.budget is not None:
            self.available = max(0, self.available - cost)

    def should_conserve(self) -> bool:
        """True when the budget is low enough that a full episode should be avoided."""
        return self.budget is not None and self.available < self.costs.full

    def remaining(self) -> int | None:
        """Current energy left in the recoverable budget, or None when unbudgeted."""
        return self.available if self.budget is not None else None

    def rest(self) -> None:
        """Restore energy to full (Vision §15)."""
        if self.budget is not None:
            self.available = self.budget

    def set_budget(self, budget: int | None) -> None:
        """Set (or clear) the recoverable energy budget at runtime."""
        self.budget = budget
        self.available = budget if budget is not None else 0


def charge(jarvis: Jarvis, attention: Attention) -> None:
    """Charge an episode's cognitive cost (Vision §15) and update the budget."""
    jarvis.energy.charge(attention)


def should_conserve(jarvis: Jarvis) -> bool:
    """True when the budget is low enough that a full episode should be avoided."""
    return jarvis.energy.should_conserve()


def energy_spent(jarvis: Jarvis) -> int:
    """Total cognitive energy spent so far (Vision §15)."""
    return jarvis.energy.spent


def energy_remaining(jarvis: Jarvis) -> int | None:
    """Current energy left in the recoverable budget (Vision §15), or None."""
    return jarvis.energy.remaining()


def is_conserving(jarvis: Jarvis) -> bool:
    """True when Jarvis is low enough on energy to answer briefly to conserve."""
    return should_conserve(jarvis)


def rest(jarvis: Jarvis) -> None:
    """Restore energy to full (Vision §15)."""
    jarvis.energy.rest()


def set_energy_budget(jarvis: Jarvis, budget: int | None) -> None:
    """Set (or clear) the recoverable energy budget at runtime (Vision §15, §40)."""
    jarvis.energy.set_budget(budget)


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
    depth = jarvis.deliberation_value() if value is None else value
    result = jarvis.executive.run(
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
    evidence = jarvis.perception.perceive(observation)
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
        piece for observation in seen for piece in jarvis.perception.perceive(observation)
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
    depth = jarvis.deliberation_value() if value is None else value
    deliberation = jarvis.executive.deliberate(observation, options, value=depth)
    charge(jarvis, deliberation.attention)
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
    return find_reflections(list(jarvis.beliefs.all_beliefs()), jarvis.refutations.all())


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
        or leading.confidence.value < jarvis.knobs().insight_confidence
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
        belief = resolve_belief_for(
            jarvis.beliefs, _insight_trigger(finding.observation)
        )
        if belief is not None and belief.confidence.value >= jarvis.knobs().insight_confidence:
            action = ActionVO(
                description=f'verify that "{finding.observation}" still holds',
                expected="the observation is confirmed",
                confidence=belief.confidence,
                reversible=True,
            )
            return _recommend_action(jarvis, action)
    return None


def reflect_cycle(jarvis: Jarvis) -> ReflectiveCycle:
    """Run the reflective cycle once, gating each stage on something worth pursuing.

    Reflect always runs; hypothesise needs reflections, challenge needs a
    leading hypothesis, and learn needs a raised challenge (each would
    otherwise recompute the previous stage just to return None). Act, gap
    scouting and consolidation are maintenance with their own internal guards
    and always run. ``path`` records what actually executed, so idleness is
    observable, not claimed.
    """
    path = ["connect", "reflect"]
    conns = connections(jarvis)
    reflections = reflect(jarvis)
    reflection = reflections[0] if reflections else None
    hypotheses = None
    leading = None
    chal = None
    learned = None
    if reflections:
        hypotheses = hypothesise(jarvis)
        path.append("hypothesise")
        leading = hypotheses.leading() if hypotheses is not None else None
        if leading is not None:
            chal = challenge(jarvis)
            path.append("challenge")
            learned = learn_from_reflection(jarvis)
            path.append("learn")
    action = act_on_insight(jarvis)
    path.append("act")
    capability_proposals = tuple(
        cap.name for cap in jarvis.auto_scout_gaps()
    )
    path.append("scout")
    return ReflectiveCycle(
        connections=conns,
        reflection=reflection,
        hypothesis=leading.statement if leading is not None else None,
        challenge=chal,
        learned=learned.statement if learned is not None else None,
        action=action,
        capability_proposals=capability_proposals,
        path=tuple(path),
    )


def refute(jarvis: Jarvis, observation: str, belief_statement: str) -> None:
    """Record that a belief would hold *without* an observation."""
    jarvis.refutations.add(observation, belief_statement)
