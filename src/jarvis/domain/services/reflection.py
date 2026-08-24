"""Reflecting over the belief web to notice load-bearing observations (Vision §19).

Cycle stage two, after Connect: group beliefs by the evidence they share and
surface each observation that grounds two or more of them. This replaces the
executive's placeholder "reflection" with something that genuinely reviews what
Jarvis has concluded -- as a pure read-model, deriving findings, storing and
asserting nothing. What it finds feeds the next stage (autonomous hypotheses).
"""

from __future__ import annotations

from collections.abc import Sequence

from jarvis.domain.entities.belief import Belief
from jarvis.domain.value_objects.reflection import Reflection


def _evidence_contents(belief: Belief) -> set[str]:
    explanation = belief.explain()
    return {piece.content for piece in (*explanation.supporting, *explanation.contradicting)}


def find_reflections(
    beliefs: Sequence[Belief],
    refuted: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[Reflection, ...]:
    """Every observation that grounds two or more beliefs, most load-bearing first.

    A ``(observation, belief statement)`` pair in ``refuted`` no longer counts:
    Challenge (Increment 77) has established that belief would hold without that
    observation, so it does not rest on it.
    """
    by_observation: dict[str, set[str]] = {}
    for belief in beliefs:
        for content in _evidence_contents(belief):
            if (content, belief.statement) in refuted:
                continue
            by_observation.setdefault(content, set()).add(belief.statement)
    findings = [
        Reflection(observation=observation, beliefs=tuple(sorted(statements)))
        for observation, statements in by_observation.items()
        if len(statements) >= 2
    ]
    findings.sort(key=lambda finding: finding.load, reverse=True)
    return tuple(findings)
