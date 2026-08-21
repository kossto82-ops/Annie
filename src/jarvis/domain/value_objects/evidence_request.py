"""EvidenceRequest: naming the gap instead of guessing (Vision §16, §37).

When an episode cannot conclude confidently, uncertainty should be explicit and
*actionable* -- not just "insufficient evidence", but a structured statement of
what is being asked, how confident Jarvis currently is, and what kind of
observation would raise that confidence. Curiosity names a valuable unknown
(Vision §16); this is that unknown made concrete on the episode.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.value_objects.confidence import Confidence


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceRequest:
    """A structured request for the evidence a conclusion is missing."""

    question: str  # the trigger that prompted the episode
    statement: str  # the working conclusion Jarvis is trying to reach
    confidence: Confidence  # how confident it currently is (low, by definition)
    needed: str  # what kind of observation would help
