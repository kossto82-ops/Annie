"""CompanionModel: Jarvis's evolving model of its companion (Vision §5).

This is what makes Jarvis a companion rather than an assistant: a model of the
person that grows from evidence. Crucially it is *hypothesis-driven, never
absolute truth* (Vision §5). Each thing Jarvis believes about the companion is an
ordinary `Belief` -- confidence derived from evidence, revisable, contradictable.
The companion can contradict it and the belief weakens rather than being silently
overwritten (Vision §18): the distinction between an observation, a repeated
pattern, and a settled model is carried by how much evidence a belief has, not by
flattening everything into "facts".

Like other aggregates it collects the events its beliefs emit (D4/D15) and leaves
dispatch to the orchestrator.
"""

from __future__ import annotations

from jarvis.domain.entities.belief import Belief
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.value_objects.evidence import Evidence


class CompanionModel:
    """A set of beliefs about the companion, each grounded in evidence."""

    def __init__(self) -> None:
        self._beliefs: dict[str, Belief] = {}
        self._pending_events: list[CognitiveEvent] = []

    def observe(self, trait: str, evidence: Evidence) -> Belief:
        """Record an observation about the companion, evolving the matching belief."""
        belief = self._beliefs.get(trait)
        if belief is None:
            belief = Belief(statement=trait)
            self._beliefs[trait] = belief
        belief.add_evidence(evidence)
        self._pending_events.extend(belief.pull_events())
        return belief

    def belief_about(self, trait: str) -> Belief | None:
        """What Jarvis currently believes about ``trait``, or None if nothing yet."""
        return self._beliefs.get(trait)

    def beliefs(self) -> tuple[Belief, ...]:
        """Every belief Jarvis holds about the companion."""
        return tuple(self._beliefs.values())

    def summarise(self) -> list[str]:
        """A plain-language account of each belief about the companion (Vision §5, §40)."""
        return [belief.explain().narrate() for belief in self._beliefs.values()]

    def pull_events(self) -> list[CognitiveEvent]:
        """Return and clear the events recorded since the last pull."""
        events = self._pending_events[:]
        self._pending_events.clear()
        return events
