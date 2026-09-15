"""Evidence-driven selection of which recall retriever answers (P2-C).

Pure string logic, no model involved. The default is lexical recall; a
preference for embedding recall forms only on well-sampled, meaningful
evidence and always stays reversible (D20).
"""

from __future__ import annotations

from jarvis.domain.value_objects.retrieval_strategy import (
    RetrievalStrategy,
    RetrievalStrategyStats,
)

# How many recorded runs each side must have before its success rate is
# meaningful enough to prefer it over the safe default.
MIN_STRATEGY_SAMPLES = 5

# The success-rate gap that turns a sampled tendency into a preference.
STRATEGY_PREFERENCE_GAP = 0.15


def select_retrieval_strategy(
    stats: RetrievalStrategyStats, *, embedding_available: bool
) -> RetrievalStrategy:
    """Which retriever the current evidence selects.

    With no embedding retriever available the answer is always lexical (and
    nothing is ever recorded). With one available, embedding wins only when
    both sides are well sampled and its success rate clears lexical by a
    meaningful gap; anything else -- ties, thin evidence, an inconclusive
    gap -- keeps the safe default.
    """
    if not embedding_available:
        return RetrievalStrategy.LEXICAL
    if (
        stats.count(RetrievalStrategy.LEXICAL) < MIN_STRATEGY_SAMPLES
        or stats.count(RetrievalStrategy.EMBEDDING) < MIN_STRATEGY_SAMPLES
    ):
        return RetrievalStrategy.LEXICAL
    gap = stats.success_rate(RetrievalStrategy.EMBEDDING) - stats.success_rate(
        RetrievalStrategy.LEXICAL
    )
    if gap >= STRATEGY_PREFERENCE_GAP:
        return RetrievalStrategy.EMBEDDING
    return RetrievalStrategy.LEXICAL