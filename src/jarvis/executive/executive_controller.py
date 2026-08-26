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

from collections.abc import Iterable, Mapping, Sequence

from jarvis.domain.aggregates.cognitive_episode import CognitiveEpisode
from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.aggregates.hypothesis_set import HypothesisSet
from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.attention import Attention
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.repositories.belief_repository import BeliefRepository
from jarvis.domain.repositories.episode_repository import EpisodeRepository
from jarvis.domain.services.self_observation import (
    observe_evidence_habit,
    observe_overconfidence,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.deliberation import Deliberation
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.evidence_request import EvidenceRequest
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.nervous_system.nervous_system import NervousSystem

# Below this evidence-derived confidence, a conclusion is not asserted as grounded
# (D14). A defensible midpoint of [0, 1]; revisited when reflection/attention need it.
GROUNDED_CONFIDENCE_THRESHOLD = 0.5

# A grounded conclusion resting on evidence with little temporal spread may be
# overfitting to a recent burst (Vision §11); below this stability it is flagged.
LOW_STABILITY_THRESHOLD = 0.2

# When Jarvis holds a self-belief this confident that it concludes without enough
# evidence, it changes how it handles an ungrounded question (Vision §20 learning).
# This is not a fixed mode: it appears only while the self-belief is confident and
# fades as the habit stops recurring.
LEARNED_HABIT_THRESHOLD = 0.5


# The internal identity prefix for a working conclusion. It disambiguates working
# beliefs from other belief kinds and keeps retrieval deterministic (D17) — but it is
# machine bookkeeping, never shown to the companion (use `subject_of` at the surface).
_WORKING_PREFIX = "Working conclusion about: "


def working_statement(trigger: str) -> str:
    """The statement of the belief an episode reasons toward for ``trigger``.

    Deterministic, so the same trigger retrieves the same belief across episodes.
    """
    return f"{_WORKING_PREFIX}{trigger}"


def subject_of(statement: str) -> str:
    """The natural subject behind a working-conclusion statement, for display.

    Strips the internal `_WORKING_PREFIX` so the surface can name what a belief is
    *about* in the companion's own words, never the machine label. A statement without
    the prefix (a self-tendency, a companion trait) is returned unchanged.
    """
    return statement.removeprefix(_WORKING_PREFIX)


def _assess_attention(belief: Belief, *, given_new_evidence: bool) -> Attention:
    """Decide how much reasoning a trigger warrants (Vision §14).

    A belief already held confidently, with no new evidence to integrate, is
    answered briefly; anything else gets full reasoning.
    """
    already_known = belief.confidence.value >= GROUNDED_CONFIDENCE_THRESHOLD
    if already_known and not given_new_evidence:
        return Attention.BRIEF
    return Attention.FULL


class ExecutiveController:
    """Coordinates the cognitive lifecycle of one episode at a time."""

    def __init__(
        self,
        nervous_system: NervousSystem,
        beliefs: BeliefRepository,
        episodes: EpisodeRepository,
        companion: CompanionModel,
    ) -> None:
        self._nervous_system = nervous_system
        self._beliefs = beliefs
        self._episodes = episodes
        self._companion = companion

    def run(
        self,
        episode: CognitiveEpisode,
        evidence: Iterable[Evidence] = (),
        *,
        conserve: bool = False,
    ) -> CognitiveEpisode:
        """Drive ``episode`` to COMPLETED, grounding its decision in evidence.

        A belief already held about this trigger is retrieved and evolved, giving
        continuity across episodes (Vision §3); otherwise a fresh one is formed.
        Attention (Vision §14) routes the depth: a confidently-known trigger with
        no new evidence is answered briefly, skipping the deeper integration.

        ``conserve`` (Vision §15): when energy is low, a would-be FULL episode that
        carries no new evidence is answered briefly instead of running the full
        lifecycle -- but only then, since dropping to BRIEF while new evidence is
        present would discard that evidence. It economises, it never loses input.
        """
        pieces = list(evidence)
        self._flush(episode)  # dispatch EpisodeStarted recorded at construction

        episode.begin_reasoning()
        belief = self._resolve_working_belief(episode)
        attention = _assess_attention(belief, given_new_evidence=bool(pieces))
        if conserve and attention is Attention.FULL and not pieces:
            attention = Attention.BRIEF
        episode.attend(attention)
        if episode.attention is Attention.FULL:
            self._seed_from_companion(episode)
            for piece in pieces:
                episode.observe(piece)
        self._beliefs.save(belief)
        self._flush(episode)  # dispatch evidence/belief events

        episode.begin_reflecting()
        if episode.attention is Attention.FULL:
            self._reflect(belief)
        self._flush(episode)

        episode.begin_deciding()
        decision = self._decide(episode.trigger, belief, episode.attention)
        if episode.goal is not None:
            # Provenance: what this episode was toward (Vision §26).
            decision = f"Toward '{episode.goal.statement}': {decision}"
        self._maybe_request_evidence(episode, belief)
        self._flush(episode)

        episode.complete(decision)
        self._flush(episode)  # dispatch EpisodeCompleted

        self._remember(episode, belief, decision)
        return episode

    def deliberate(
        self, observation: str, options: Mapping[str, Sequence[Evidence]]
    ) -> Deliberation:
        """Weigh competing explanations as a first-class episode (Vision §17).

        Runs the episode lifecycle, routes each option's evidence to a
        HypothesisSet (correlated to the episode so it is traceable), records the
        episode in memory as a DELIBERATION, and returns the outcome.
        """
        episode = CognitiveEpisode(trigger=observation)
        self._flush(episode)  # EpisodeStarted

        episode.begin_reasoning()
        hypotheses = HypothesisSet(observation=observation)
        for statement, evidences in options.items():
            hypothesis = hypotheses.propose(statement, correlation_id=episode.id)
            for piece in evidences:
                hypotheses.add_evidence(hypothesis.id, piece, correlation_id=episode.id)
        self._dispatch(hypotheses.pull_events())
        self._flush(episode)

        episode.begin_reflecting()
        self._flush(episode)
        episode.begin_deciding()

        ranking = tuple((h.statement, h.confidence.value) for h in hypotheses.ranked())
        leader = hypotheses.leading()
        if leader is None:
            decision = f"Competing explanations for: {observation} remain undecided."
            deliberation = Deliberation(
                observation=observation,
                leading=None,
                confidence=Confidence.none(),
                ranking=ranking,
                evidence_request=EvidenceRequest(
                    question=observation,
                    statement="competing explanations remain undecided",
                    confidence=Confidence.none(),
                    needed=(
                        "evidence that distinguishes the competing explanations for: "
                        f"{observation}"
                    ),
                ),
                episode_id=episode.id,
            )
        else:
            decision = (
                f"Most likely explanation for: {observation} is "
                f"'{leader.statement}' (confidence {leader.confidence.value:.2f})."
            )
            deliberation = Deliberation(
                observation=observation,
                leading=leader.statement,
                confidence=leader.confidence,
                ranking=ranking,
                evidence_request=None,
                episode_id=episode.id,
            )
        self._flush(episode)

        episode.complete(decision)
        self._flush(episode)  # EpisodeCompleted

        self._episodes.record(
            EpisodeRecord(
                episode_id=episode.id,
                trigger=observation,
                decision=decision,
                working_belief_id=leader.id if leader is not None else "",
                outcome=episode.state,
                conclusion_confidence=deliberation.confidence,
                conclusion_stability=TemporalStability.none(),
                origin=episode.origin,
                kind=EpisodeKind.DELIBERATION,
            )
        )
        return deliberation

    # -- cognitive steps -----------------------------------------------------

    def _resolve_working_belief(self, episode: CognitiveEpisode) -> Belief:
        statement = working_statement(episode.trigger)
        remembered = self._beliefs.get_by_statement(statement)
        if remembered is not None:
            episode.adopt_working_belief(remembered)
            return remembered
        return episode.form_working_belief(statement)

    def _seed_from_companion(self, episode: CognitiveEpisode) -> None:
        """If Jarvis already believes something relevant about the companion, feed
        it in as standing evidence (Vision §3, §5) -- provenance kept, not an
        override; new evidence in the episode can still outweigh it.
        """
        relevant = self._companion.relevant_to(episode.trigger)
        if relevant is None:
            return
        episode.observe(
            Evidence(
                content=(
                    f"I already believe about my companion: {relevant.statement} "
                    f"(confidence {relevant.confidence.value:.2f})"
                ),
                source=EvidenceSource.SYSTEM_OBSERVATION,
                weight=relevant.confidence,
            )
        )

    def _reflect(self, belief: Belief) -> None:
        # Reflection has no observable output yet; a later increment turns this
        # into a genuine review of the reasoning behind ``belief``.
        _ = belief

    def _decide(self, trigger: str, belief: Belief, attention: Attention) -> str:
        confidence = belief.confidence.value
        if attention is Attention.BRIEF:
            # Answered from existing understanding, not fresh grounding (Vision §14).
            return (
                f"From what I already understand about: {trigger} — I hold this "
                f"with confidence {confidence:.2f}."
            )
        if confidence <= 0.0:
            if self._recognises_evidence_habit():
                # Behaviour changed by a learned tendency (Vision §20), not a guess.
                return (
                    "I have learned that I tend to conclude without sufficient "
                    f"evidence, so rather than guess about: {trigger}, I am asking "
                    f"for evidence before concluding (confidence {confidence:.2f})."
                )
            return (
                f"Insufficient evidence to conclude about: {trigger} "
                f"(confidence {confidence:.2f})."
            )
        if confidence < GROUNDED_CONFIDENCE_THRESHOLD:
            return (
                f"Tentative, low-confidence view about: {trigger} "
                f"(confidence {confidence:.2f}); more evidence needed."
            )
        stability = belief.stability.value
        conclusion = (
            f"Concluded about: {trigger} (confidence {confidence:.2f}, "
            f"stability {stability:.2f}), grounded in {len(belief.evidence)} piece(s) of evidence."
        )
        if stability < LOW_STABILITY_THRESHOLD:
            if self._recognises_overconfidence():
                # Tempered by learned self-knowledge (Vision §20), not a generic warning.
                conclusion += (
                    " (I have learned I tend to be overconfident on thin evidence, "
                    "so I am holding this more tentatively.)"
                )
            else:
                conclusion += (
                    " (Caution: this rests on a narrow time window — "
                    "possible overfitting to recent events.)"
                )
        return conclusion

    def _maybe_request_evidence(self, episode: CognitiveEpisode, belief: Belief) -> None:
        """When a conclusion is not grounded, name the evidence it needs (Vision §37)."""
        if belief.confidence.value >= GROUNDED_CONFIDENCE_THRESHOLD:
            return
        episode.attach_evidence_request(
            EvidenceRequest(
                question=episode.trigger,
                statement=belief.statement,
                confidence=belief.confidence,
                needed=f"observations bearing on whether: {episode.trigger}",
            )
        )

    def _recognises_overconfidence(self) -> bool:
        """Does Jarvis currently, confidently, believe it over-trusts thin evidence?

        Derived from prior episodes each time (Vision §20), so it fades as grounded
        conclusions become better spread over time.
        """
        self_belief = observe_overconfidence(self._episodes.history())
        return (
            self_belief is not None
            and self_belief.confidence.value >= LEARNED_HABIT_THRESHOLD
        )

    def _recognises_evidence_habit(self) -> bool:
        """Does Jarvis currently, confidently, believe it under-evidences its conclusions?

        Derived from history each time, so it fades as the habit stops recurring.
        The current episode is not yet recorded, so this reflects only past cognition.
        """
        self_belief = observe_evidence_habit(self._episodes.history())
        return (
            self_belief is not None
            and self_belief.confidence.value >= LEARNED_HABIT_THRESHOLD
        )

    def _remember(self, episode: CognitiveEpisode, belief: Belief, decision: str) -> None:
        self._episodes.record(
            EpisodeRecord(
                episode_id=episode.id,
                trigger=episode.trigger,
                decision=decision,
                working_belief_id=belief.id,
                outcome=episode.state,
                conclusion_confidence=belief.confidence,
                conclusion_stability=belief.stability,
                origin=episode.origin,
                kind=EpisodeKind.CONCLUSION,
                goal=episode.goal.statement if episode.goal is not None else None,
            )
        )

    # -- event plumbing ------------------------------------------------------

    def _flush(self, episode: CognitiveEpisode) -> None:
        self._dispatch(episode.pull_events())

    def _dispatch(self, events: Sequence[CognitiveEvent]) -> None:
        for event in events:
            self._nervous_system.publish(event)
        self._nervous_system.dispatch()
