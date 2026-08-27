"""Inference: a provisional answer reasoned from knowledge, not remembered or grounded.

When Jarvis holds no grounded belief and recalls no relevant memory, it can still
*reason* about a question instead of refusing (Vision §37 is about not fabricating a
grounded conclusion -- it never said Jarvis may not think). An Inference is exactly
that: a candidate answer produced by a reasoner.

It is deliberately NOT a belief and NOT evidence. Its epistemic status is explicit in
its name and in how the surface frames it ("reasoning from what I understand…"): it is
provisional, carries no derived confidence, and a real observation always outweighs it.
The reasoner proposes; the domain decides to present it *as inference* (Vision §38, D6).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Inference:
    """A provisional, clearly-provisional answer a reasoner produced for a query."""

    answer: str
