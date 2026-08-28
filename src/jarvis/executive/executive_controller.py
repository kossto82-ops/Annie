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

import re
from collections.abc import Iterable, Mapping, Sequence

from jarvis.domain.aggregates.cognitive_episode import CognitiveEpisode
from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.aggregates.hypothesis_set import HypothesisSet
from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.attention import Attention
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.reasoning.reasoner import Reasoner
from jarvis.domain.repositories.belief_repository import BeliefRepository
from jarvis.domain.repositories.episode_repository import EpisodeRepository
from jarvis.domain.retrieval.memory_retriever import MemoryRetriever
from jarvis.domain.services.self_observation import (
    observe_evidence_habit,
    observe_overconfidence,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.deliberation import Deliberation
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.evidence_request import EvidenceRequest
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.nervous_system.nervous_system import NervousSystem

# Below this evidence-derived confidence, a conclusion is not asserted as grounded
# (D14). A defensible midpoint of [0, 1]; revisited when reflection/attention need it.
GROUNDED_CONFIDENCE_THRESHOLD = 0.5

# A grounded conclusion resting on evidence with little temporal spread may be
# overfitting to a recent burst (Vision §11); below this stability it is flagged.
LOW_STABILITY_THRESHOLD = 0.2

# A recalled memory must share at least this fraction of the query's words to be
# worth surfacing -- a deliberately conservative floor so a single common word
# ("the", "que") does not read as a relevant memory. Tunable; superseded once a
# semantic retriever can judge relevance by meaning rather than surface overlap.
_MIN_RECALL_RELEVANCE = 0.2

# At or above this recall relevance a memory answers the question well enough that
# Jarvis need not reason from scratch. The single source of truth for "strong recall",
# shared with the surface so the response stance and the reasoning gate agree.
STRONG_RECALL_RELEVANCE = 0.6

# When the companion asks about *themselves*, what Jarvis knows about them is fully
# relevant regardless of shared words ("who am I?" shares nothing with "is named
# Raúl"). Surface-token recall cannot bridge that, so a self-question consults the
# companion model directly. This is a bounded, tunable heuristic for *when to look
# there*, not a judgement of truth; a semantic retriever supersedes it (D11).
_WORD = re.compile(r"\w+")
_SELF_REFERENCE = frozenset(
    {"me", "mi", "mí", "yo", "soy", "mío", "mía", "conmigo", "my", "i", "myself", "mine"}
)
_QUESTION_CUES = frozenset(
    {
        "que", "qué", "cual", "cuál", "como", "cómo", "quien", "quién", "cuando",
        "cuándo", "donde", "dónde", "sabes", "conoces", "recuerdas", "what", "who",
        "how", "which", "when", "where", "do", "does", "did", "know", "remember",
    }
)
# How many companion traits to surface for a self-question -- the most confident few.
_MAX_SELF_QUESTION_TRAITS = 3


def _looks_like_self_question(text: str) -> bool:
    """True when the companion is asking Jarvis about the companion themselves."""
    tokens = set(_WORD.findall(text.lower()))
    is_question = text.strip().endswith("?") or bool(tokens & _QUESTION_CUES)
    return is_question and bool(tokens & _SELF_REFERENCE)


def remembered_inference(belief: Belief) -> Evidence | None:
    """The provisional answer Jarvis already reasoned for this belief, if any.

    The most recent supporting inference evidence -- what to surface (still framed as
    provisional) instead of re-asking the model, until the companion confirms it and it
    becomes an ordinary, grounded belief.
    """
    for piece in reversed(belief.evidence):
        if piece.source is EvidenceSource.INFERENCE and piece.supports:
            return piece
    return None

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
        memory_retriever: MemoryRetriever | None = None,
        reasoner: Reasoner | None = None,
    ) -> None:
        self._nervous_system = nervous_system
        self._beliefs = beliefs
        self._episodes = episodes
        self._companion = companion
        # Optional: surfaces relevant memories to *answer from*, distinct from the
        # evidence that grounds a belief (Vision §3, §22). Absent -> behaviour is
        # exactly as before recall existed.
        self._memory_retriever = memory_retriever
        # Optional: proposes a provisional answer when neither belief nor memory can
        # help (Vision §37). Absent -> an ungrounded, unremembered question stays an
        # honest "I don't have enough", exactly as before.
        self._reasoner = reasoner

    def set_reasoner(self, reasoner: Reasoner | None) -> None:
        """Swap the reasoner at runtime (matches the active provider, Vision §38)."""
        self._reasoner = reasoner

    def set_memory_retriever(self, retriever: MemoryRetriever | None) -> None:
        """Swap the memory retriever at runtime -- e.g. lexical -> embedding (D11)."""
        self._memory_retriever = retriever

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
            self._recall_into(episode)
            self._reason_into(episode, belief)
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

    def _recall_into(self, episode: CognitiveEpisode) -> None:
        """Surface memories bearing on the trigger, to answer from (Vision §3).

        Recalled context, not belief-evidence (Vision §22): it lets the surface
        answer from what Jarvis remembers instead of a blank "insufficient
        evidence", without touching the belief's derived confidence. The belief
        the episode is *currently* forming about this exact trigger is filtered
        out -- echoing it back as "memory" would be circular, not recall.
        """
        if self._memory_retriever is None:
            return
        relevant: list[RecalledMemory] = []
        seen: set[str] = set()
        # Results come ranked most-relevant first, so the first time a given content
        # appears is its strongest match; later duplicates (e.g. the same text held
        # both as a world belief and an episode) are dropped.
        for memory in self._memory_retriever.recall(episode.trigger):
            if memory.relevance < _MIN_RECALL_RELEVANCE:
                continue
            if self._is_about_current(memory, episode.trigger):
                continue
            key = memory.content.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            relevant.append(memory)
        # A question about the companion themselves is answered from the companion
        # model directly, since surface-token recall cannot bridge "who am I?" to a
        # trait like "is named Raúl" (Vision §5).
        if _looks_like_self_question(episode.trigger):
            for memory in self._companion_traits():
                key = memory.content.strip().lower()
                if key in seen:
                    continue
                seen.add(key)
                relevant.append(memory)
        if relevant:
            # Sort so the most relevant leads regardless of the order sources were
            # gathered in (companion traits carry full relevance to a self-question).
            relevant.sort(
                key=lambda m: (-m.relevance, -(m.source_confidence or 0.0), m.content)
            )
            episode.recall(tuple(relevant))

    def _reason_into(self, episode: CognitiveEpisode, belief: Belief) -> None:
        """Reason a provisional answer when belief and memory can't give one (§37).

        Only when the belief has no *real* support (an inference doesn't count) and no
        strong memory already answers the trigger, and Jarvis has not already reasoned
        this before -- so a remembered answer is recalled, never re-asked of the model
        (Vision §37). The reasoned answer is then remembered as the weakest, clearly
        sourced evidence, so it persists and can mature when the companion confirms it
        -- confidence stays derived and low (Vision §38, D3, D6).
        """
        if self._reasoner is None:
            return
        if self._has_real_support(belief):
            return
        recalled = episode.recalled_memories
        if recalled and recalled[0].relevance >= STRONG_RECALL_RELEVANCE:
            return
        if remembered_inference(belief) is not None:
            return  # already reasoned this — the answer is remembered, don't re-ask
        inference = self._reasoner.infer(episode.trigger, recalled)
        if inference is None:
            return
        episode.infer(inference)
        episode.observe(
            Evidence(
                content=inference.answer,
                source=EvidenceSource.INFERENCE,
                weight=Confidence(0.6),
                context="reasoned via the language model",
            )
        )

    @staticmethod
    def _has_real_support(belief: Belief) -> bool:
        """True when the belief rests on any non-inference evidence (Vision §37)."""
        return any(
            piece.source is not EvidenceSource.INFERENCE for piece in belief.evidence
        )

    def _companion_traits(self) -> list[RecalledMemory]:
        """What Jarvis knows about the companion, as recalled memories (most confident
        first) -- fully relevant to a question the companion asks about themselves.
        """
        traits = sorted(
            self._companion.beliefs(),
            key=lambda belief: belief.confidence.value,
            reverse=True,
        )
        return [
            RecalledMemory(
                content=belief.statement,
                kind=MemoryKind.COMPANION_TRAIT,
                provenance="companion trait",
                relevance=1.0,
                source_confidence=belief.confidence.value,
            )
            for belief in traits[:_MAX_SELF_QUESTION_TRAITS]
        ]

    @staticmethod
    def _is_about_current(memory: RecalledMemory, trigger: str) -> bool:
        """True when a recalled item just restates the episode's own trigger.

        Covers the just-formed belief AND a prior identical-question episode -- echoing
        either back as "memory" would be circular (e.g. re-asking the same question would
        recall itself instead of the answer Jarvis reasoned for it).
        """
        return (
            memory.kind in (MemoryKind.WORLD_BELIEF, MemoryKind.GOAL, MemoryKind.EPISODE)
            and memory.content.strip().lower() == trigger.strip().lower()
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
