"""PerceptionSource: the seam between the world and Jarvis's epistemology.

Jarvis reasons only over `Evidence` (Vision §8) -- structured, weighted, sourced
facts. But the world does not arrive as evidence; it arrives as raw observations
(a companion's utterance, a document, a signal). A `PerceptionSource` translates
one raw observation into zero or more `Evidence` objects.

This is the boundary named in Vision §32: a capability provider (today a dumb
rule, tomorrow perhaps an LLM) may *produce evidence* from the world, but it
never decides anything. Confidence is still derived from the evidence, and the
executive still reasons. Swapping a smarter implementation in behind this
Protocol must not touch the cognitive core (Vision §38).

Producing no evidence is a valid, honest answer (Vision §37): a source that
cannot make anything of an observation stays silent rather than inventing.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jarvis.domain.value_objects.evidence import Evidence


@runtime_checkable
class PerceptionSource(Protocol):
    """Translates a raw observation into evidence Jarvis can reason over."""

    def perceive(self, observation: str) -> tuple[Evidence, ...]:
        """Return evidence drawn from ``observation`` -- empty when it makes none."""
        ...
