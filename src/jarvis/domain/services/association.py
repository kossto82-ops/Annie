"""Connecting beliefs that rest on shared evidence (Vision §4, §31).

The first stage of the reflective cycle beyond mere remembering: notice that two
beliefs are grounded in the same observation. This is a pure read over the
beliefs -- it derives connections, it stores nothing and asserts nothing. What it
finds becomes the material the later stages (reflect, hypothesise) work on.
"""

from __future__ import annotations

from collections.abc import Sequence

from jarvis.domain.entities.belief import Belief
from jarvis.domain.value_objects.connection import Connection


def _evidence_contents(belief: Belief) -> set[str]:
    explanation = belief.explain()
    return {piece.content for piece in (*explanation.supporting, *explanation.contradicting)}


def find_connections(beliefs: Sequence[Belief]) -> tuple[Connection, ...]:
    """Every pair of beliefs that share at least one piece of evidence, strongest
    (most shared) first. Beliefs grounded in no evidence connect to nothing.
    """
    contents = [(belief, _evidence_contents(belief)) for belief in beliefs]
    connections: list[Connection] = []
    for index, (belief, belief_contents) in enumerate(contents):
        if not belief_contents:
            continue
        for other, other_contents in contents[index + 1 :]:
            shared = belief_contents & other_contents
            if shared:
                connections.append(
                    Connection(
                        first=belief.statement,
                        second=other.statement,
                        shared_evidence=tuple(sorted(shared)),
                    )
                )
    connections.sort(key=lambda connection: connection.strength, reverse=True)
    return tuple(connections)
