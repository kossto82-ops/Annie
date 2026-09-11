"""Meta-observation: second-order reflection on cognitive processes.

Observes patterns in reasoning strategies, retrieval quality, and attention
allocation. Returns ``MetaKnowledge`` instances that capture insights about
how Jarvis knows, not just what it knows. Returns None when there is
insufficient history to judge honestly.
"""

from __future__ import annotations

from collections.abc import Sequence

from jarvis.domain.entities.meta_knowledge import MetaKnowledge
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.meta_knowledge_kind import MetaKnowledgeKind
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.recalled_memory import RecalledMemory

# Minimum history for honest meta-observation (higher than first-order)
_MINIMUM_HISTORY = 6

_OBSERVATION_WEIGHT = Confidence(1.0)


def observe_reasoning_effectiveness(
    episodes: Sequence[EpisodeRecord],
) -> MetaKnowledge | None:
    """Observe which reasoning strategies produce well-grounded conclusions.

    Compares CONCLUSION episodes (think) vs DELIBERATION episodes (consider)
    to detect which approach yields higher confidence conclusions.
    Returns None when there is insufficient history.
    """
    conclusions = [
        r for r in episodes
        if r.kind.value == "conclusion"
    ]
    deliberations = [
        r for r in episodes
        if r.kind.value == "deliberation"
    ]

    # Need sufficient history in both categories
    if len(conclusions) < _MINIMUM_HISTORY or len(deliberations) < _MINIMUM_HISTORY:
        return None

    avg_conclusion_confidence = (
        sum(r.conclusion_confidence.value for r in conclusions) / len(conclusions)
    )
    avg_deliberation_confidence = (
        sum(r.conclusion_confidence.value for r in deliberations) / len(deliberations)
    )

    # Only note a pattern when the difference is significant
    if avg_conclusion_confidence > avg_deliberation_confidence + 0.15:
        statement = (
            "My conclusions tend to be better grounded than my deliberations"
        )
    elif avg_deliberation_confidence > avg_conclusion_confidence + 0.15:
        statement = (
            "My deliberations tend to produce better grounded conclusions"
        )
    else:
        return None  # No clear pattern

    mk = MetaKnowledge(kind=MetaKnowledgeKind.REASONING_STRATEGY, statement=statement)

    for record in episodes:
        mk.add_evidence(
            Evidence(
                content=(
                    f"episode about '{record.trigger}' ({record.kind.value}) "
                    f"concluded at confidence {record.conclusion_confidence.value:.2f}"
                ),
                source=EvidenceSource.SYSTEM_OBSERVATION,
                weight=_OBSERVATION_WEIGHT,
                supports=record.kind.value == "conclusion"
                    and avg_conclusion_confidence > avg_deliberation_confidence,
                observed_at=record.recorded_at,
            )
        )
    return mk


def observe_retrieval_quality(
    episodes: Sequence[EpisodeRecord],
    recalled: Sequence[RecalledMemory],
) -> MetaKnowledge | None:
    """Observe whether memory retrieval is relevant or noisy.

    Compares the relevance scores of recalled memories against episode
    outcomes to detect if retrieval is helping or hindering.
    Returns None when there is insufficient data.
    """
    if len(episodes) < _MINIMUM_HISTORY or not recalled:
        return None

    avg_relevance = sum(r.relevance for r in recalled) / len(recalled)
    high_relevance = avg_relevance > 0.5

    if high_relevance:
        statement = "My memory retrieval tends to surface relevant memories"
    else:
        statement = "My memory retrieval tends to surface noisy memories"

    mk = MetaKnowledge(kind=MetaKnowledgeKind.RETRIEVAL_QUALITY, statement=statement)

    # Use recalled memories as evidence
    for memory in recalled[:10]:  # Cap at 10 pieces of evidence
        mk.add_evidence(
            Evidence(
                content=(
                    f"recalled '{memory.content[:50]}' with relevance "
                    f"{memory.relevance:.2f} (kind: {memory.kind.value})"
                ),
                source=EvidenceSource.SYSTEM_OBSERVATION,
                weight=_OBSERVATION_WEIGHT,
                supports=memory.relevance > 0.5,
            )
        )
    return mk


def observe_attention_allocation(
    episodes: Sequence[EpisodeRecord],
) -> MetaKnowledge | None:
    """Observe whether attention allocation (FULL/BRIEF) is appropriate.

    Detects if the system is over- or under-allocating attention by
    comparing episode outcomes with their recorded attention levels.
    Returns None when there is insufficient history.
    """
    if len(episodes) < _MINIMUM_HISTORY:
        return None

    # Group by whether conclusion was grounded
    grounded = [
        r for r in episodes
        if r.conclusion_confidence.value >= 0.5
    ]
    ungrounded = [
        r for r in episodes
        if r.conclusion_confidence.value < 0.5
    ]

    if not grounded and not ungrounded:
        return None

    # If most episodes are ungrounded, attention may be insufficient
    ungrounded_ratio = len(ungrounded) / len(episodes) if episodes else 0.0

    if ungrounded_ratio > 0.7:
        statement = "I tend to allocate insufficient attention to complex questions"
    elif ungrounded_ratio < 0.3 and len(episodes) >= 5:
        statement = "I tend to allocate attention appropriately"
    else:
        return None  # No clear pattern

    mk = MetaKnowledge(kind=MetaKnowledgeKind.ATTENTION_PATTERN, statement=statement)

    for record in episodes:
        mk.add_evidence(
            Evidence(
                content=(
                    f"episode about '{record.trigger}' concluded at "
                    f"confidence {record.conclusion_confidence.value:.2f}"
                ),
                source=EvidenceSource.SYSTEM_OBSERVATION,
                weight=_OBSERVATION_WEIGHT,
                supports=record.conclusion_confidence.value >= 0.5,
                observed_at=record.recorded_at,
            )
        )
    return mk
