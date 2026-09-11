"""Entity extraction: extracting knowledge graph entities from beliefs.

Analyses belief statements and evidence content to detect entities (people,
projects, concepts) and relationships between them. Returns new nodes and
edges to be added to the knowledge graph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from jarvis.domain.entities.belief import Belief
from jarvis.domain.entities.knowledge_edge import KnowledgeEdge
from jarvis.domain.entities.knowledge_node import KnowledgeNode
from jarvis.domain.enums.node_kind import NodeKind
from jarvis.domain.value_objects.evidence import Evidence

# Simple heuristics for entity detection
_UPPERCASED = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")
_RELATION_PATTERNS = [
    (re.compile(r"trabaja\s+(?:en|para)\s+", re.IGNORECASE), "works_on"),
    (re.compile(r"conoce\s+a\s+", re.IGNORECASE), "knows"),
    (re.compile(r"decidi[oó]\s+", re.IGNORECASE), "decided"),
    (re.compile(r"caus[oó]\s+", re.IGNORECASE), "caused"),
    (re.compile(r"prefiere\s+", re.IGNORECASE), "prefers"),
    (re.compile(r"usa\s+", re.IGNORECASE), "uses"),
    (re.compile(r"cre[oó]\s+", re.IGNORECASE), "created"),
    (re.compile(r"es\s+parte\s+de\s+", re.IGNORECASE), "part_of"),
    (re.compile(r"depende\s+de\s+", re.IGNORECASE), "depends_on"),
]


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """The result of entity extraction from a belief."""

    new_nodes: tuple[KnowledgeNode, ...]
    new_edges: tuple[KnowledgeEdge, ...]


def _extract_proper_names(text: str) -> list[str]:
    """Extract potential proper names (capitalized words) from text."""
    return _UPPERCASED.findall(text)


def _detect_relation(text: str) -> str | None:
    """Detect a relationship type from text."""
    for pattern, relation in _RELATION_PATTERNS:
        if pattern.search(text):
            return relation
    return None


def extract_entities(
    belief: Belief,
    existing_nodes: tuple[KnowledgeNode, ...] = (),
) -> ExtractionResult:
    """Extract entities and relationships from a belief.

    Analyses the belief statement and evidence to detect:
    1. Proper names → CONCEPT nodes (or PERSON if context suggests)
    2. Relationship patterns → edges between detected entities

    Returns new nodes and edges to be added to the graph.
    """
    text = f"{belief.statement} {' '.join(e.content for e in belief.evidence)}"
    names = _extract_proper_names(text)

    # Build lookup of existing nodes by name
    existing_by_name = {n.name: n for n in existing_nodes}

    new_nodes: list[KnowledgeNode] = []
    node_map: dict[str, KnowledgeNode] = {}

    for name in names:
        if name in existing_by_name:
            node_map[name] = existing_by_name[name]
        elif name not in node_map:
            # Default to CONCEPT; could be enhanced with context analysis
            node = KnowledgeNode(kind=NodeKind.CONCEPT, name=name)
            new_nodes.append(node)
            node_map[name] = node

    # Detect relationships
    new_edges: list[KnowledgeEdge] = []
    relation = _detect_relation(text)

    if relation and len(node_map) >= 2:
        # Create edges between all pairs of detected entities
        names_list = list(node_map.keys())
        for i in range(len(names_list)):
            for j in range(i + 1, len(names_list)):
                source = node_map[names_list[i]]
                target = node_map[names_list[j]]
                edge = KnowledgeEdge(
                    source_id=source.id,
                    target_id=target.id,
                    relation=relation,
                )
                new_edges.append(edge)

    return ExtractionResult(
        new_nodes=tuple(new_nodes),
        new_edges=tuple(new_edges),
    )
