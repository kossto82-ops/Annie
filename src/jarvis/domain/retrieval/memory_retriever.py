"""MemoryRetriever: the seam between a query and what Jarvis already remembers.

Persistence gives Jarvis continuity, but a store keyed by exact statement can only
answer "have I concluded about this exact string before?". Conversation needs the
other direction: given what the companion just said, *which of my memories bear on
it?* That is retrieval, and it is a distinct capability from storage.

This is a domain-level Protocol, mirroring :class:`PerceptionSource` (Vision §32,
§38): a retriever is a capability provider that *surfaces relevant candidates* from
memory -- it does not judge them, weigh beliefs, or decide anything. The cognitive
core still derives confidence and reasons. A deterministic, offline implementation
is the honest first step; a semantic (embedding) one can drop in behind the same
Protocol later without touching cognition (Vision §38, D11).

Recalling nothing is a valid, honest answer (Vision §37): a query no memory bears
on returns an empty result rather than a forced match.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jarvis.domain.value_objects.recalled_memory import RecalledMemory


@runtime_checkable
class MemoryRetriever(Protocol):
    """Surfaces the memories most relevant to a query, most relevant first."""

    def recall(self, query: str, *, limit: int = 5) -> tuple[RecalledMemory, ...]:
        """Return up to ``limit`` remembered items bearing on ``query``.

        Ordered most-relevant first; empty when nothing bears on the query.
        """
        ...
