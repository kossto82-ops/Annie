"""The contract for persisting and querying the knowledge graph.

The knowledge graph stores entities (nodes) and their relationships (edges),
supporting traversal and path-finding queries. Concrete storage lives in
``jarvis.infrastructure``.
"""

from __future__ import annotations

from typing import Protocol

from jarvis.domain.entities.knowledge_edge import KnowledgeEdge
from jarvis.domain.entities.knowledge_node import KnowledgeNode
from jarvis.domain.enums.node_kind import NodeKind


class KnowledgeGraphRepository(Protocol):
    """Persists knowledge nodes and edges, supporting traversal queries."""

    # --- Node operations ---

    def get_node(self, node_id: str) -> KnowledgeNode | None:
        """Return the node with the given id, or None if unknown."""
        ...

    def get_node_by_name(
        self, name: str, kind: NodeKind | None = None
    ) -> KnowledgeNode | None:
        """Return the first node matching name (and optionally kind)."""
        ...

    def save_node(self, node: KnowledgeNode) -> None:
        """Persist (insert or update) a node."""
        ...

    def all_nodes(self) -> tuple[KnowledgeNode, ...]:
        """Every node in the graph."""
        ...

    # --- Edge operations ---

    def get_edge(self, edge_id: str) -> KnowledgeEdge | None:
        """Return the edge with the given id, or None if unknown."""
        ...

    def save_edge(self, edge: KnowledgeEdge) -> None:
        """Persist (insert or update) an edge."""
        ...

    def edges_from(self, node_id: str) -> tuple[KnowledgeEdge, ...]:
        """All edges originating from the given node."""
        ...

    def edges_to(self, node_id: str) -> tuple[KnowledgeEdge, ...]:
        """All edges pointing to the given node."""
        ...

    def edges_between(
        self, source_id: str, target_id: str
    ) -> tuple[KnowledgeEdge, ...]:
        """All edges from source to target."""
        ...

    # --- Traversal ---

    def neighbors(
        self, node_id: str, relation: str | None = None, depth: int = 1
    ) -> tuple[KnowledgeNode, ...]:
        """Nodes reachable from ``node_id`` up to ``depth`` hops.

        Optionally filtered by relation type.
        """
        ...

    def path_between(
        self, source_id: str, target_id: str, max_depth: int = 4
    ) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]] | None:
        """Find a path from source to target, or None if unreachable within max_depth."""
        ...
