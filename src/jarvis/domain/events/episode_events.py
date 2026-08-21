"""Concrete cognitive events emitted by a cognitive episode.

Only the two events required by the current slice exist. Further events
(AttentionShifted, HypothesisCreated, BeliefStrengthened, ...) are added when
the cognitive operation that emits them is implemented.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.events.domain_event import CognitiveEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class EpisodeStarted(CognitiveEvent):
    """A cognitive episode has begun, driven by ``trigger``."""

    trigger: str


@dataclass(frozen=True, slots=True, kw_only=True)
class EpisodeCompleted(CognitiveEvent):
    """A cognitive episode finished successfully, producing ``result``."""

    result: str
