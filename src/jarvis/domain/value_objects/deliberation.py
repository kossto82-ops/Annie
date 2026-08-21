"""Deliberation: the outcome of weighing competing explanations (Vision §17).

Jarvis should hold several explanations for an observation at once and let
evidence shift their relative standing, rather than collapsing to one. A
Deliberation reports where that stands: the current ranking, the leading
explanation *if one is clearly ahead*, and -- when the top two are tied, i.e. the
evidence does not yet decide -- no leader plus a request for what would (Vision
§17, §37). It never forces a winner.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence_request import EvidenceRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class Deliberation:
    """The current standing of competing explanations for an observation."""

    observation: str
    leading: str | None  # the strongest explanation, or None if undecided (a tie)
    confidence: Confidence  # confidence in the leader (none if undecided)
    ranking: tuple[tuple[str, float], ...]  # (statement, confidence) descending
    evidence_request: EvidenceRequest | None  # what would decide it, when undecided
