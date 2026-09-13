"""CognitiveEpisode -- the fundamental unit of cognition and an aggregate root.

An episode is *not* a prompt/response pair. It is a bounded cognitive process
with a trigger, an explicit lifecycle, and a stream of events describing what
happened inside it. The episode owns its own state-machine invariants: only
legal transitions are permitted, and it records a domain event for the facts
that matter (started, completed).

An episode reasons toward *one* conclusion-model -- either a working :class:`Belief`
(conclusion shape) or a :class:`HypothesisSet` of competing explanations
(deliberation shape) -- held in a single slot. There is no second episode shape:
both conclusions ride the same lifecycle, the same event boundary, and the same
derived :attr:`~CognitiveEpisode.kind`. Deliberations are not a caller-painted
tag; they are structurally the same episode holding a set instead of a belief.

The aggregate does not publish its own events -- it collects them, and an
orchestrator (the executive controller) pulls and dispatches them. This keeps
the domain free of infrastructure coupling.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from jarvis.domain.aggregates.hypothesis_set import HypothesisSet
from jarvis.domain.entities.belief import Belief, BeliefExplanation
from jarvis.domain.enums.attention import Attention
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.events.episode_events import (
    EpisodeCompleted,
    EpisodeFailed,
    EpisodeReflected,
    EpisodeStarted,
)
from jarvis.domain.services.evidence_weighting import EvidenceWeightingPolicy
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.evidence_request import EvidenceRequest
from jarvis.domain.value_objects.goal import Goal
from jarvis.domain.value_objects.inference import Inference
from jarvis.domain.value_objects.recalled_memory import RecalledMemory


class InvalidStateTransition(RuntimeError):
    """Raised when an episode is asked to make an illegal state transition."""


# Legal forward transitions for the current slice. FAILED is reachable from any
# non-terminal state and is handled separately in :meth:`CognitiveEpisode.fail`.
_ALLOWED: dict[EpisodeState, frozenset[EpisodeState]] = {
    EpisodeState.CREATED: frozenset({EpisodeState.REASONING}),
    EpisodeState.REASONING: frozenset({EpisodeState.REFLECTING}),
    EpisodeState.REFLECTING: frozenset({EpisodeState.DECIDING}),
    EpisodeState.DECIDING: frozenset({EpisodeState.COMPLETED}),
    EpisodeState.COMPLETED: frozenset(),
    EpisodeState.FAILED: frozenset(),
}


def _new_episode_id() -> str:
    return str(uuid.uuid4())


def _empty_event_buffer() -> list[CognitiveEvent]:
    return []


@dataclass(slots=True, eq=False)
class CognitiveEpisode:
    """A single, bounded cognitive process."""

    trigger: str
    id: str = field(default_factory=_new_episode_id)
    state: EpisodeState = EpisodeState.CREATED
    result: str | None = None
    origin: TriggerOrigin = TriggerOrigin.COMPANION
    attention: Attention = Attention.FULL
    goal: Goal | None = None
    _conclusion: Belief | HypothesisSet | None = field(default=None, repr=False)
    _evidence_request: EvidenceRequest | None = field(default=None, repr=False)
    _recalled: tuple[RecalledMemory, ...] = field(default=(), repr=False)
    _inference: Inference | None = field(default=None, repr=False)
    _consulted: str | None = field(default=None, repr=False)
    _reflection_note: str | None = field(default=None, repr=False)
    _pending_events: list[CognitiveEvent] = field(
        default_factory=_empty_event_buffer, repr=False
    )

    def __post_init__(self) -> None:
        if not self.trigger or not self.trigger.strip():
            raise ValueError("A cognitive episode requires a non-empty trigger")
        # Record the fact that this episode came into existence.
        self._record(
            EpisodeStarted(episode_id=self.id, correlation_id=self.id, trigger=self.trigger)
        )

    # -- transitions ---------------------------------------------------------

    def begin_reasoning(self) -> None:
        self._transition_to(EpisodeState.REASONING)

    def begin_reflecting(self) -> None:
        self._transition_to(EpisodeState.REFLECTING)

    def begin_deciding(self) -> None:
        self._transition_to(EpisodeState.DECIDING)

    def complete(self, result: str) -> None:
        self._transition_to(EpisodeState.COMPLETED)
        self.result = result
        self._record(
            EpisodeCompleted(episode_id=self.id, correlation_id=self.id, result=result)
        )

    # -- conclusion model (the belief or hypotheses the episode is reasoning toward)

    def form_working_belief(
        self, statement: str, policy: EvidenceWeightingPolicy | None = None
    ) -> Belief:
        """Create the belief this episode is reasoning toward (Vision §12).

        ``policy`` sets how the belief weighs its evidence; when omitted the belief
        uses the default (no decay). A decaying policy makes stale evidence count for
        less over time (Vision §10, §22).
        """
        if self.state.is_terminal:
            raise InvalidStateTransition(
                f"Episode {self.id} is {self.state.value}; cannot form a belief"
            )
        belief = (
            Belief(statement=statement, weighting_policy=policy)
            if policy is not None
            else Belief(statement=statement)
        )
        self._conclusion = belief
        return belief

    def form_hypotheses(self, observation: str) -> HypothesisSet:
        """Attach the competing explanations this episode will weigh (Vision §17).

        Mirrors :meth:`form_working_belief` for the deliberation shape: the episode
        is one lifecycle shell and one event boundary whichever conclusion-model it
        holds (the hypothesis set's events flow through :meth:`pull_events` exactly
        like a belief's do).
        """
        if self.state.is_terminal:
            raise InvalidStateTransition(
                f"Episode {self.id} is {self.state.value}; cannot form hypotheses"
            )
        hypothesis_set = HypothesisSet(observation=observation)
        self._conclusion = hypothesis_set
        return hypothesis_set

    def adopt_working_belief(self, belief: Belief) -> None:
        """Attach an existing belief retrieved from memory (Vision §3 continuity)."""
        if self.state.is_terminal:
            raise InvalidStateTransition(
                f"Episode {self.id} is {self.state.value}; cannot adopt a belief"
            )
        self._conclusion = belief

    @property
    def conclusion(self) -> Belief | HypothesisSet | None:
        """The conclusion-model this episode reasoned toward, if any."""
        return self._conclusion

    @property
    def working_belief(self) -> Belief | None:
        """The working belief, or None when the episode weighs hypotheses instead."""
        conclusion = self._conclusion
        if isinstance(conclusion, Belief):
            return conclusion
        return None

    @property
    def hypothesis_set(self) -> HypothesisSet | None:
        """The competing explanations this episode weighs, or None for a belief."""
        conclusion = self._conclusion
        if isinstance(conclusion, HypothesisSet):
            return conclusion
        return None

    @property
    def kind(self) -> EpisodeKind:
        """Which shape of cognition this episode is -- derived, not caller-painted.

        An episode holding competing hypotheses is a DELIBERATION; anything else
        (a working belief, or none while still reasoning) is a CONCLUSION. The tag
        can never drift from the actual conclusion the episode carried (Vision §17).
        """
        if isinstance(self._conclusion, HypothesisSet):
            return EpisodeKind.DELIBERATION
        return EpisodeKind.CONCLUSION

    def explain(self) -> BeliefExplanation | None:
        """Explain the episode's conclusion, or None if it formed no belief."""
        belief = self.working_belief
        if belief is None:
            return None
        return belief.explain()

    def recall(self, memories: tuple[RecalledMemory, ...]) -> None:
        """Attach the memories retrieval surfaced as relevant to this trigger.

        This is *recalled context*, not truth: it drives how the episode is
        answered (Vision §3), and deliberately does NOT become evidence for the
        working belief -- remembering that a topic was discussed says nothing about
        whether a conclusion about it is true (memory is not truth, Vision §22).
        Confidence stays derived only from evidence that bears on the belief.
        """
        if self.state.is_terminal:
            raise InvalidStateTransition(
                f"Episode {self.id} is {self.state.value}; cannot recall into it"
            )
        self._recalled = memories

    @property
    def recalled_memories(self) -> tuple[RecalledMemory, ...]:
        """The memories judged relevant to this episode's trigger (Vision §3)."""
        return self._recalled

    def infer(self, inference: Inference) -> None:
        """Attach a provisional answer reasoned for this trigger (Vision §37).

        Like recalled memory, this is *response context*, not truth: it is offered
        when no grounded belief and no memory could answer, and it never becomes
        evidence or changes the working belief's derived confidence (Vision §38, D6).
        """
        if self.state.is_terminal:
            raise InvalidStateTransition(
                f"Episode {self.id} is {self.state.value}; cannot reason into it"
            )
        self._inference = inference

    @property
    def inference(self) -> Inference | None:
        """The provisional answer reasoned for this trigger, if any (Vision §37)."""
        return self._inference

    def record_consult(self, kind: str) -> None:
        """Record that this episode deliberately consulted the ``kind`` edge.

        Provenance only (Vision §26): the consult's findings arrive as ordinary
        candidate evidence via :meth:`observe`; this marker exists so the same
        episode never consults twice, and so a trace can later say *which* edge
        was asked and what it returned.
        """
        if self.state.is_terminal:
            raise InvalidStateTransition(
                f"Episode {self.id} is {self.state.value}; cannot record a consult"
            )
        self._consulted = kind

    @property
    def consulted(self) -> str | None:
        """The deliberate-consult edge this episode used, or None (Vision §26)."""
        return self._consulted

    def attach_evidence_request(self, request: EvidenceRequest) -> None:
        """Record what evidence this episode is missing (Vision §16, §37)."""
        self._evidence_request = request

    @property
    def evidence_request(self) -> EvidenceRequest | None:
        """The evidence this episode needs to conclude, or None if it was grounded."""
        return self._evidence_request

    def attend(self, attention: Attention) -> None:
        """Record how much reasoning this episode was given (Vision §14)."""
        self.attention = attention

    def observe(self, evidence: Evidence) -> None:
        """Route a piece of evidence to the episode's working belief.

        The belief's events are correlated to this episode, so the whole act of
        cognition forms one traceable process (Vision §26). A deliberation episode
        routes evidence to a specific hypothesis instead (through its
        :class:`HypothesisSet`), never to the episode itself.
        """
        conclusion = self._conclusion
        if conclusion is None:
            raise ValueError("Form a working belief before observing evidence")
        if not isinstance(conclusion, Belief):
            raise ValueError(
                "A deliberation episode routes evidence to a hypothesis, not to "
                "the episode; add it to the hypothesis set instead"
            )
        conclusion.add_evidence(evidence, correlation_id=self.id)

    def fail(self, reason: str) -> None:
        if self.state.is_terminal:
            raise InvalidStateTransition(
                f"Episode {self.id} is already {self.state.value}; cannot fail"
            )
        self.state = EpisodeState.FAILED
        self.result = None
        self._record(
            EpisodeFailed(episode_id=self.id, correlation_id=self.id, reason=reason)
        )

    def record_reflection(self, note: str, *, contested: bool) -> None:
        """Record the episode's review of its own reasoning (Vision §19).

        Reflection *notices*, it does not conclude: this appends an
        :class:`EpisodeReflected` event to the episode's trace and stores
        the note on the episode for later persistence.  ``note`` is what
        the review observed; ``contested`` marks that the conclusion rests
        on partly-contradicted evidence.
        """
        self._reflection_note = note
        self._record(
            EpisodeReflected(
                episode_id=self.id,
                correlation_id=self.id,
                note=note,
                contested=contested,
            )
        )

    # -- events --------------------------------------------------------------

    def pull_events(self) -> list[CognitiveEvent]:
        """Return and clear this episode's events, including its conclusion's."""
        events = self._pending_events[:]
        self._pending_events.clear()
        conclusion = self._conclusion
        if conclusion is not None:
            events.extend(conclusion.pull_events())
        return events

    # -- internals -----------------------------------------------------------

    def _transition_to(self, target: EpisodeState) -> None:
        if target not in _ALLOWED[self.state]:
            raise InvalidStateTransition(
                f"Cannot move episode {self.id} from {self.state.value} to {target.value}"
            )
        self.state = target

    def _record(self, event: CognitiveEvent) -> None:
        self._pending_events.append(event)
