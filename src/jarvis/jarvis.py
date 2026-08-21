"""The Jarvis entry point.

``Jarvis.think(trigger)`` runs a complete cognitive lifecycle over a trigger and
returns the resulting episode. The nervous system is exposed so callers can
subscribe to cognitive events *before* thinking begins.
"""

from __future__ import annotations

from collections.abc import Iterable

from jarvis.domain.aggregates.cognitive_episode import CognitiveEpisode
from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.repositories.belief_repository import BeliefRepository
from jarvis.domain.repositories.episode_repository import EpisodeRepository
from jarvis.domain.services.curiosity import wonder
from jarvis.domain.services.self_observation import observe_evidence_habit
from jarvis.domain.value_objects.curiosity_impulse import CuriosityImpulse
from jarvis.domain.value_objects.evidence import Evidence
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

    def feel_curious(self) -> CuriosityImpulse | None:
        """Decide whether a known self-tendency is worth investigating (Vision §16).

        Returns a recommendation to pursue -- not an action taken -- or None if
        there is nothing confident enough to warrant it.
        """
        self_belief = self.observe_self()
        if self_belief is None:
            return None
        return wonder(self_belief)

    def pursue(self, impulse: CuriosityImpulse) -> CognitiveEpisode:
        """Run a self-triggered episode for a curiosity impulse (Vision §16, §31).

        This is the first episode Jarvis initiates on its own rather than in
        response to the companion; it is marked with a CURIOSITY origin.
        """
        episode = CognitiveEpisode(trigger=impulse.trigger, origin=TriggerOrigin.CURIOSITY)
        return self._executive.run(episode)

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
