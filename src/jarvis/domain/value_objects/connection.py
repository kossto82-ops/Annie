"""Connection: a derived association between two beliefs (Vision §4, §31).

Beliefs are otherwise islands -- each grounded in its own evidence, keyed by its
own trigger. A Connection records that two of them *rest on the same observation*:
they share one or more pieces of evidence (by content). This is the raw material
of insight -- once beliefs are connected, later stages can reflect over the
clusters and form hypotheses that span them.

Like everything else it is derived, never asserted: a Connection exists only
because shared evidence exists, and its ``strength`` is just how much they share.
Semantic association (beliefs that are *about* the same thing without sharing
literal evidence) is a later, richer step; this is the honest first one.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Connection:
    """Two beliefs linked by the evidence they share."""

    first: str  # statement of one belief
    second: str  # statement of the other
    shared_evidence: tuple[str, ...]  # evidence contents present in both

    @property
    def strength(self) -> int:
        """How strongly the two are connected: the count of shared observations."""
        return len(self.shared_evidence)

    def involves(self, statement: str) -> bool:
        return statement in (self.first, self.second)
