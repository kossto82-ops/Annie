"""EnergyCosts: what a cognitive episode costs, by attention (Vision §15, §14).

Thinking is not free. A FULL episode -- the whole lifecycle, seeding the companion
model, seeking evidence, reflecting -- costs more than a BRIEF one that answers
from an already-confident belief (Increment 33). This value object holds those
costs so they are configurable (injectable at construction), not a buried
constant -- so a later command center can tune them at runtime.

This increment only makes cost *visible* (accumulated and reported); a budget that
makes attention *choose* BRIEF under load is a later step.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.enums.attention import Attention


@dataclass(frozen=True, slots=True, kw_only=True)
class EnergyCosts:
    """The cognitive cost of an episode, per attention level."""

    full: int = 3
    brief: int = 1

    def for_attention(self, attention: Attention) -> int:
        return self.full if attention is Attention.FULL else self.brief
