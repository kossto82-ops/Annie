"""NodeKind: the type of entity in the knowledge graph."""

from __future__ import annotations

from enum import Enum


class NodeKind(Enum):
    """The type of entity a knowledge node represents."""

    PERSON = "person"
    PROJECT = "project"
    CONCEPT = "concept"
    DECISION = "decision"
    EVENT = "event"
