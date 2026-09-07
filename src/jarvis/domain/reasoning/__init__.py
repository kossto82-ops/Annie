"""Reasoning: producing a provisional answer when memory and belief have none.

The domain owns the *contract* for reasoning (:class:`Reasoner`) and the short-term
:class:`ReasoningSpan` that carries a session's reasoning across turns; concrete
reasoners live in :mod:`jarvis.infrastructure`, like perception and retrieval. A
reasoner proposes a candidate answer; it never decides truth (Vision §38, D6).
"""

from __future__ import annotations

from jarvis.domain.reasoning.reasoner import Reasoner
from jarvis.domain.reasoning.reasoning_span import (
    ReasoningSpan,
    SpanThread,
    ThreadPosture,
)

__all__ = [
    "Reasoner",
    "ReasoningSpan",
    "SpanThread",
    "ThreadPosture",
]