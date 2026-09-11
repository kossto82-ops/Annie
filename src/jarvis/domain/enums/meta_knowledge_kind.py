"""MetaKnowledgeKind: the type of meta-cognitive knowledge."""

from __future__ import annotations

from enum import Enum


class MetaKnowledgeKind(Enum):
    """The kind of knowledge about one's own cognitive process."""

    REASONING_STRATEGY = "reasoning_strategy"  # what works for reasoning
    RETRIEVAL_QUALITY = "retrieval_quality"  # how well memory retrieval works
    ATTENTION_PATTERN = "attention_pattern"  # how attention is allocated
