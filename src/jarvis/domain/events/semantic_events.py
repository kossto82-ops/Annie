"""Domain events for semantic memory."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.events.domain_event import CognitiveEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class SemanticMemoryReinforced(CognitiveEvent):
    """Emitted when evidence strengthens a semantic memory pattern."""

    memory_id: str
    pattern: str
    evidence_content: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SemanticMemoryContested(CognitiveEvent):
    """Emitted when evidence contradicts a semantic memory pattern."""

    memory_id: str
    pattern: str
    evidence_content: str
