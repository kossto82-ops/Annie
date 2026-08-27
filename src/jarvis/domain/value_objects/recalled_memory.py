"""RecalledMemory: one remembered item surfaced as relevant to a query (Vision §3).

A retriever does not decide anything (mirrors the PerceptionSource boundary,
Vision §32, §38): it *surfaces candidates* from what Jarvis already holds and
reports how relevant each is and where it came from. Turning a recalled item into
standing evidence -- and deriving any confidence from it -- is the cognitive
core's job in a later step, not the retriever's.

So this value object carries only what a retriever can honestly report:

* ``content``          -- the remembered text, ready to show or reason over.
* ``kind``             -- which store it came from (:class:`MemoryKind`).
* ``provenance``       -- a short, human-readable source note (auditable, Vision §8).
* ``relevance``        -- the ranking score for this query, in ``[0, 1]``. It is a
                          match strength, NOT a truth or confidence claim.
* ``source_confidence``-- the derived confidence of the underlying belief when the
                          item is belief-backed (a world belief, companion trait,
                          goal, or an episode's conclusion), else ``None``. Reported,
                          never re-derived here.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.enums.memory_kind import MemoryKind


@dataclass(frozen=True, slots=True, kw_only=True)
class RecalledMemory:
    """A remembered item a retriever judged relevant to a query."""

    content: str
    kind: MemoryKind
    provenance: str
    relevance: float
    source_confidence: float | None = None
