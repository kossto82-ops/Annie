"""Concrete cognitive events emitted by a cognitive episode.

Each event is added when the cognitive operation that emits it is implemented:
an episode starts, reviews its own reasoning (reflects), and then ends either
successfully (completed) or without a conclusion (failed).
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.events.domain_event import CognitiveEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class EpisodeStarted(CognitiveEvent):
    """A cognitive episode has begun, driven by ``trigger``."""

    trigger: str


@dataclass(frozen=True, slots=True, kw_only=True)
class EpisodeReflected(CognitiveEvent):
    """The episode reviewed its own reasoning (Vision §19).

    ``note`` states what the review noticed about the working belief; ``contested``
    is true when the conclusion rests on evidence that is partly contradicted. The
    review notices, it does not conclude -- it changes no belief and no decision.
    """

    note: str
    contested: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class EpisodeCompleted(CognitiveEvent):
    """A cognitive episode finished successfully, producing ``result``."""

    result: str


@dataclass(frozen=True, slots=True, kw_only=True)
class EpisodeFailed(CognitiveEvent):
    """A cognitive episode ended without a conclusion, for ``reason``."""

    reason: str
