"""ExecutiveController -- the orchestrator of a single cognitive episode.

The controller decides *which cognitive operation happens next* and drives the
episode through its lifecycle. It is an orchestrator, not a God Object: the
cognitive substance lives in the domain (the episode's working belief and its
evidence-derived confidence), not in the controller.

What matters here is that the *decision depends on the epistemology*. With no
evidence the controller does not fabricate an answer -- it reports insufficient
evidence (Vision §37). Confidence, derived from evidence, decides whether the
conclusion is grounded, tentative, or withheld.
"""

from __future__ import annotations

from collections.abc import Iterable

from jarvis.domain.aggregates.cognitive_episode import CognitiveEpisode
from jarvis.domain.entities.belief import Belief
from jarvis.domain.repositories.belief_repository import BeliefRepository
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.nervous_system.nervous_system import NervousSystem

# Below this evidence-derived confidence, a conclusion is not asserted as grounded
# (D14). A defensible midpoint of [0, 1]; revisited when reflection/attention need it.
GROUNDED_CONFIDENCE_THRESHOLD = 0.5


def working_statement(trigger: str) -> str:
    """The statement of the belief an episode reasons toward for ``trigger``.

    Deterministic, so the same trigger retrieves the same belief across episodes.
    """
    return f"Working conclusion about: {trigger}"


class ExecutiveController:
    """Coordinates the cognitive lifecycle of one episode at a time."""

    def __init__(
        self, nervous_system: NervousSystem, beliefs: BeliefRepository
    ) -> None:
        self._nervous_system = nervous_system
        self._beliefs = beliefs

    def run(
        self, episode: CognitiveEpisode, evidence: Iterable[Evidence] = ()
    ) -> CognitiveEpisode:
        """Drive ``episode`` to COMPLETED, grounding its decision in evidence.

        A belief already held about this trigger is retrieved and evolved, giving
        continuity across episodes (Vision §3); otherwise a fresh one is formed.
        """
        self._flush(episode)  # dispatch EpisodeStarted recorded at construction

        episode.begin_reasoning()
        belief = self._resolve_working_belief(episode)
        for piece in evidence:
            episode.observe(piece)
        self._beliefs.save(belief)
        self._flush(episode)  # dispatch evidence/belief events

        episode.begin_reflecting()
        self._reflect(belief)
        self._flush(episode)

        episode.begin_deciding()
        decision = self._decide(episode.trigger, belief)
        self._flush(episode)

        episode.complete(decision)
        self._flush(episode)  # dispatch EpisodeCompleted

        return episode

    # -- cognitive steps -----------------------------------------------------

    def _resolve_working_belief(self, episode: CognitiveEpisode) -> Belief:
        statement = working_statement(episode.trigger)
        remembered = self._beliefs.get_by_statement(statement)
        if remembered is not None:
            episode.adopt_working_belief(remembered)
            return remembered
        return episode.form_working_belief(statement)

    def _reflect(self, belief: Belief) -> None:
        # Reflection has no observable output yet; a later increment turns this
        # into a genuine review of the reasoning behind ``belief``.
        _ = belief

    def _decide(self, trigger: str, belief: Belief) -> str:
        confidence = belief.confidence.value
        if confidence <= 0.0:
            return (
                f"Insufficient evidence to conclude about: {trigger} "
                f"(confidence {confidence:.2f})."
            )
        if confidence < GROUNDED_CONFIDENCE_THRESHOLD:
            return (
                f"Tentative, low-confidence view about: {trigger} "
                f"(confidence {confidence:.2f}); more evidence needed."
            )
        return (
            f"Concluded about: {trigger} (confidence {confidence:.2f}), "
            f"grounded in {len(belief.evidence)} piece(s) of evidence."
        )

    # -- event plumbing ------------------------------------------------------

    def _flush(self, episode: CognitiveEpisode) -> None:
        for event in episode.pull_events():
            self._nervous_system.publish(event)
        self._nervous_system.dispatch()
