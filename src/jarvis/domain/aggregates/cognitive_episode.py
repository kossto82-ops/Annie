"""CognitiveEpisode -- the fundamental unit of cognition and an aggregate root.

An episode is *not* a prompt/response pair. It is a bounded cognitive process
with a trigger, an explicit lifecycle, and a stream of events describing what
happened inside it. The episode owns its own state-machine invariants: only
legal transitions are permitted, and it records a domain event for the facts
that matter (started, completed).

The aggregate does not publish its own events -- it collects them, and an
orchestrator (the executive controller) pulls and dispatches them. This keeps
the domain free of infrastructure coupling.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from jarvis.domain.entities.belief import Belief, BeliefExplanation
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.events.episode_events import EpisodeCompleted, EpisodeStarted
from jarvis.domain.value_objects.evidence import Evidence


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
    _working_belief: Belief | None = field(default=None, repr=False)
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

    # -- working belief (the conclusion the episode is reasoning toward) ------

    def form_working_belief(self, statement: str) -> Belief:
        """Create the belief this episode is reasoning toward (Vision §12)."""
        if self.state.is_terminal:
            raise InvalidStateTransition(
                f"Episode {self.id} is {self.state.value}; cannot form a belief"
            )
        belief = Belief(statement=statement)
        self._working_belief = belief
        return belief

    def adopt_working_belief(self, belief: Belief) -> None:
        """Attach an existing belief retrieved from memory (Vision §3 continuity)."""
        if self.state.is_terminal:
            raise InvalidStateTransition(
                f"Episode {self.id} is {self.state.value}; cannot adopt a belief"
            )
        self._working_belief = belief

    @property
    def working_belief(self) -> Belief | None:
        return self._working_belief

    def explain(self) -> BeliefExplanation | None:
        """Explain the episode's conclusion, or None if it formed no belief."""
        if self._working_belief is None:
            return None
        return self._working_belief.explain()

    def observe(self, evidence: Evidence) -> None:
        """Route a piece of evidence to the episode's working belief.

        The belief's events are correlated to this episode, so the whole act of
        cognition forms one traceable process (Vision §26).
        """
        if self._working_belief is None:
            raise ValueError("Form a working belief before observing evidence")
        self._working_belief.add_evidence(evidence, correlation_id=self.id)

    def fail(self, reason: str) -> None:
        if self.state.is_terminal:
            raise InvalidStateTransition(
                f"Episode {self.id} is already {self.state.value}; cannot fail"
            )
        self.state = EpisodeState.FAILED
        self.result = None
        _ = reason  # reason is retained by the caller/log; no failure event yet

    # -- events --------------------------------------------------------------

    def pull_events(self) -> list[CognitiveEvent]:
        """Return and clear this episode's events, including its belief's."""
        events = self._pending_events[:]
        self._pending_events.clear()
        if self._working_belief is not None:
            events.extend(self._working_belief.pull_events())
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
