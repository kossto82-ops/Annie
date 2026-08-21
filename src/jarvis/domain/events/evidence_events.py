"""Events about evidence itself, shared across everything evidence can ground.

``EvidenceAdded`` is emitted whenever a piece of evidence is attached to a
subject that derives its confidence from evidence -- a belief or a hypothesis.
``subject_id`` identifies that subject, so the same event serves both without
either owning it.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.events.domain_event import CognitiveEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceAdded(CognitiveEvent):
    """A piece of evidence was attached to a belief or hypothesis."""

    subject_id: str
    evidence_id: str
    supports: bool
