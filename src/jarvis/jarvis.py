"""The Jarvis entry point.

``Jarvis.think(trigger)`` runs a complete cognitive lifecycle over a trigger and
returns the resulting episode. The nervous system is exposed so callers can
subscribe to cognitive events *before* thinking begins.
"""

from __future__ import annotations

from collections.abc import Iterable

from jarvis.domain.aggregates.cognitive_episode import CognitiveEpisode
from jarvis.domain.entities.belief import Belief
from jarvis.domain.repositories.belief_repository import BeliefRepository
from jarvis.domain.repositories.episode_repository import EpisodeRepository
from jarvis.domain.services.self_observation import observe_evidence_habit
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.executive.executive_controller import ExecutiveController
from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore
from jarvis.infrastructure.in_memory_episode_store import InMemoryEpisodeStore
from jarvis.nervous_system.nervous_system import NervousSystem


class Jarvis:
    """A long-term cognitive companion (first vertical slice)."""

    def __init__(
        self,
        nervous_system: NervousSystem | None = None,
        beliefs: BeliefRepository | None = None,
        episodes: EpisodeRepository | None = None,
    ) -> None:
        self.nervous_system = nervous_system or NervousSystem()
        self.beliefs: BeliefRepository = beliefs or InMemoryBeliefStore()
        self.episodes: EpisodeRepository = episodes or InMemoryEpisodeStore()
        self._executive = ExecutiveController(
            self.nervous_system, self.beliefs, self.episodes
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
