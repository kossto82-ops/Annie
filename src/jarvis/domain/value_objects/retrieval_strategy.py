"""Retrieval-strategy experience (P2-C): which recall side was chosen and how it went.

The accumulated record is routing evidence only (D21): it decides which
retriever *surfaces candidates* for the executive, never what Jarvis
concludes. It is bounded (the most recent 100 outcomes), revisable (a
meaningful run of honest counter-evidence reverses a preference), and
strictly optional -- with no embedding retriever wired, nothing is ever
recorded and recall is byte-for-byte the old lexical behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RetrievalStrategy(Enum):
    """The recall sides the executive can route through."""

    LEXICAL = "lexical"
    EMBEDDING = "embedding"


@dataclass(frozen=True)
class StrategyOutcome:
    """One observed retrieval: what ran and whether it surfaced anything relevant.

    ``query`` is recorded for replay and forensic inspection (how Jarvis's
    preference formed), never consulted per query -- selection is
    evidence-driven, not query-driven.
    """

    strategy: RetrievalStrategy
    success: bool
    query: str = ""


@dataclass(frozen=True)
class RetrievalStrategyStats:
    """The bounded, most-recent-first record of retrieval outcomes."""

    outcomes: tuple[StrategyOutcome, ...] = ()

    def recorded(self, outcome: StrategyOutcome) -> RetrievalStrategyStats:
        """Return a new record with ``outcome`` appended, bounded to 100."""
        bounded = (*self.outcomes, outcome)[-100:]
        return RetrievalStrategyStats(outcomes=bounded)

    def count(self, strategy: RetrievalStrategy) -> int:
        """How many recorded outcomes used ``strategy``."""
        return sum(1 for seen in self.outcomes if seen.strategy is strategy)

    def success_rate(self, strategy: RetrievalStrategy) -> float:
        """The share of ``strategy``'s recorded runs that surfaced a hit; 0.0 when none."""
        runs = [seen for seen in self.outcomes if seen.strategy is strategy]
        if not runs:
            return 0.0
        return sum(1 for seen in runs if seen.success) / len(runs)