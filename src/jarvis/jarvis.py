"""The Jarvis entry point.

``Jarvis.think(trigger)`` runs a complete cognitive lifecycle over a trigger and
returns the resulting episode. The nervous system is exposed so callers can
subscribe to cognitive events *before* thinking begins.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from jarvis.domain.aggregates.cognitive_episode import CognitiveEpisode
from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.aggregates.hypothesis_set import HypothesisSet
from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.repositories.belief_repository import BeliefRepository
from jarvis.domain.repositories.episode_repository import EpisodeRepository
from jarvis.domain.services.curiosity import wonder
from jarvis.domain.services.self_observation import (
    observe_evidence_habit,
    observe_overconfidence,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.curiosity_impulse import CuriosityImpulse
from jarvis.domain.value_objects.deliberation import Deliberation
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.evidence_request import EvidenceRequest
from jarvis.executive.executive_controller import ExecutiveController
from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore
from jarvis.infrastructure.in_memory_episode_store import InMemoryEpisodeStore
from jarvis.nervous_system.nervous_system import NervousSystem
from jarvis.observability.episode_trace import EpisodeTrace


class Jarvis:
    """A long-term cognitive companion (first vertical slice)."""

    def __init__(
        self,
        nervous_system: NervousSystem | None = None,
        beliefs: BeliefRepository | None = None,
        episodes: EpisodeRepository | None = None,
        companion_store: BeliefRepository | None = None,
    ) -> None:
        self.nervous_system = nervous_system or NervousSystem()
        self.beliefs: BeliefRepository = beliefs or InMemoryBeliefStore()
        self.episodes: EpisodeRepository = episodes or InMemoryEpisodeStore()
        self.companion = CompanionModel(companion_store or InMemoryBeliefStore())
        self._trace = EpisodeTrace()
        self.nervous_system.subscribe(CognitiveEvent, self._trace.handle)
        self._executive = ExecutiveController(
            self.nervous_system, self.beliefs, self.episodes, self.companion
        )

    def think(
        self, trigger: str, evidence: Iterable[Evidence] = ()
    ) -> CognitiveEpisode:
        """Run a cognitive episode for ``trigger``, grounded in ``evidence``.

        With no evidence the episode completes with an honest "insufficient
        evidence" conclusion rather than a fabricated answer (Vision §37).
        """
        episode = CognitiveEpisode(trigger=trigger)
        return self._executive.run(episode, evidence)

    def observe_self(self) -> Belief | None:
        """Look back over past episodes and form a belief about Jarvis's own
        tendencies (Vision §6, §31), or None if there is too little history.

        The self-belief is grounded in the episode history and revisable like any
        other belief -- it is not a fixed personality trait.
        """
        return observe_evidence_habit(self.episodes.history())

    def observe_overconfidence(self) -> Belief | None:
        """A belief about whether Jarvis concludes confidently on thin evidence
        (Vision §6, §11), or None if there is too little grounded history.
        """
        return observe_overconfidence(self.episodes.history())

    def self_beliefs(self) -> tuple[Belief, ...]:
        """Every self-tendency Jarvis currently holds about its own cognition
        (Vision §6): the ones it has enough history to judge.
        """
        candidates = (self.observe_self(), self.observe_overconfidence())
        return tuple(belief for belief in candidates if belief is not None)

    def feel_curious(self) -> CuriosityImpulse | None:
        """Decide whether any known self-tendency is worth investigating (Vision §16).

        Considers Jarvis's whole self-model and raises an impulse for the most
        confident weakness worth acting on -- a recommendation, not an action, or
        None if nothing is confident enough (Vision §28).
        """
        by_confidence = sorted(
            self.self_beliefs(), key=lambda belief: belief.confidence.value, reverse=True
        )
        for belief in by_confidence:
            impulse = wonder(belief)
            if impulse is not None:
                return impulse
        return None

    def pursue(self, impulse: CuriosityImpulse) -> CognitiveEpisode:
        """Run a self-triggered episode for a curiosity impulse (Vision §16, §31).

        This is the first episode Jarvis initiates on its own rather than in
        response to the companion; it is marked with a CURIOSITY origin.
        """
        episode = CognitiveEpisode(trigger=impulse.trigger, origin=TriggerOrigin.CURIOSITY)
        return self._executive.run(episode)

    def consider(
        self, observation: str, options: Mapping[str, Sequence[Evidence]]
    ) -> Deliberation:
        """Weigh competing explanations for ``observation`` (Vision §17).

        ``options`` maps each candidate explanation to the evidence bearing on it.
        Returns the current ranking and the leading explanation -- or, when the
        top two are tied, no leader and a request for evidence that would decide.
        """
        hypotheses = HypothesisSet(observation=observation)
        for statement, evidences in options.items():
            hypothesis = hypotheses.propose(statement)
            for piece in evidences:
                hypotheses.add_evidence(hypothesis.id, piece)
        for event in hypotheses.pull_events():
            self.nervous_system.publish(event)
        self.nervous_system.dispatch()

        ranking = tuple((h.statement, h.confidence.value) for h in hypotheses.ranked())
        leader = hypotheses.leading()
        if leader is None:
            request = EvidenceRequest(
                question=observation,
                statement="competing explanations remain undecided",
                confidence=Confidence.none(),
                needed=(
                    "evidence that distinguishes the competing explanations for: "
                    f"{observation}"
                ),
            )
            return Deliberation(
                observation=observation,
                leading=None,
                confidence=Confidence.none(),
                ranking=ranking,
                evidence_request=request,
            )
        return Deliberation(
            observation=observation,
            leading=leader.statement,
            confidence=leader.confidence,
            ranking=ranking,
            evidence_request=None,
        )

    def trace_of(self, episode: CognitiveEpisode) -> tuple[CognitiveEvent, ...]:
        """The ordered cognitive events of ``episode`` -- its decision provenance
        (Vision §26): started, the evidence and belief changes, then completed.
        """
        return self._trace.for_correlation(episode.id)

    def observe_companion(self, trait: str, evidence: Evidence) -> Belief:
        """Record an observation about the companion and evolve Jarvis's model of
        them (Vision §5). Returns the (revisable) belief; its events flow through
        the nervous system.
        """
        belief = self.companion.observe(trait, evidence)
        for event in self.companion.pull_events():
            self.nervous_system.publish(event)
        self.nervous_system.dispatch()
        return belief
