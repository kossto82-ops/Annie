"""Events about competing hypotheses (Vision §17)."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.events.domain_event import CognitiveEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class HypothesisCreated(CognitiveEvent):
    """A candidate explanation was proposed within a set of competing hypotheses."""

    hypothesis_id: str
    statement: str
