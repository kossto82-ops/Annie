"""Reasoner: the seam for thinking about a question memory and belief can't answer.

Recall answers "what do I remember about this?"; a belief answers "what have I
concluded, and how strongly?". Neither can help with a novel, answerable question --
and refusing every such question is what made Jarvis feel useless (Vision §37 forbids
fabricating a *grounded* conclusion, not thinking at all).

This is a domain-level Protocol, mirroring :class:`PerceptionSource` and
:class:`MemoryRetriever` (Vision §32, §38): a reasoner is a capability provider that
*proposes a candidate answer*. It is NOT the epistemic judge -- the domain decides to
present the result as an :class:`Inference` (provisional, clearly labelled, carrying no
derived confidence and always beaten by real evidence, D6). An offline default that
reasons about nothing is the honest baseline; an LLM-backed reasoner drops in behind
this Protocol without the cognitive core changing (Vision §38, D7).

Producing nothing is a valid answer (Vision §37): a reasoner that cannot help returns
None rather than a fabricated one.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jarvis.domain.conversation.conversation_context import Turn
from jarvis.domain.value_objects.inference import Inference
from jarvis.domain.value_objects.recalled_memory import RecalledMemory


@runtime_checkable
class Reasoner(Protocol):
    """Proposes a provisional answer to a query, optionally using recalled context."""

    def infer(
        self,
        query: str,
        memory: tuple[RecalledMemory, ...] = (),
        conversation: tuple[Turn, ...] = (),
    ) -> Inference | None:
        """Answer ``query`` from optional memory and recent dialogue, or return None."""
        ...
