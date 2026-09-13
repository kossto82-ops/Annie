"""File-backed implementation of :class:`KnowledgeGraphRepository` (Vision §3).

Persists nodes and edges to one JSON file with crash-safe atomic writes,
reusing the canonical serialisers shared with the SQLite twin. Traversal is
the same BFS as the in-memory twin. A missing file reads as empty;
malformed entries are skipped (recovery, not a crash).
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any, cast

from jarvis.domain.entities.knowledge_edge import KnowledgeEdge
from jarvis.domain.entities.knowledge_node import KnowledgeNode
from jarvis.domain.enums.node_kind import NodeKind
from jarvis.infrastructure.atomic_write import atomic_write_text
from jarvis.infrastructure.sqlite_knowledge_graph_store import (
    deserialise_edge,
    deserialise_node,
    serialise_edge,
    serialise_node,
)


class JsonKnowledgeGraphStore:
    """An entity/relationship graph persisted to a JSON file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._nodes: dict[str, KnowledgeNode] = {}
        self._nodes_by_name: dict[str, KnowledgeNode] = {}
        self._edges: dict[str, KnowledgeEdge] = {}
        self._edges_from: dict[str, list[KnowledgeEdge]] = {}
        self._edges_to: dict[str, list[KnowledgeEdge]] = {}
        self._load()

    def get_node(self, node_id: str) -> KnowledgeNode | None:
        return self._nodes.get(node_id)

    def get_node_by_name(
        self, name: str, kind: NodeKind | None = None
    ) -> KnowledgeNode | None:
        for node in self._nodes.values():
            if node.name == name and (kind is None or node.kind == kind):
                return node
        return None

    def save_node(self, node: KnowledgeNode) -> None:
        self._nodes[node.id] = node
        self._nodes_by_name[node.name] = node
        self._flush()

    def all_nodes(self) -> tuple[KnowledgeNode, ...]:
        return tuple(self._nodes.values())

    def get_edge(self, edge_id: str) -> KnowledgeEdge | None:
        return self._edges.get(edge_id)

    def save_edge(self, edge: KnowledgeEdge) -> None:
        self._edges[edge.id] = edge
        self._edges_from.setdefault(edge.source_id, []).append(edge)
        self._edges_to.setdefault(edge.target_id, []).append(edge)
        self._flush()

    def edges_from(self, node_id: str) -> tuple[KnowledgeEdge, ...]:
        return tuple(self._edges_from.get(node_id, []))

    def edges_to(self, node_id: str) -> tuple[KnowledgeEdge, ...]:
        return tuple(self._edges_to.get(node_id, []))

    def edges_between(
        self, source_id: str, target_id: str
    ) -> tuple[KnowledgeEdge, ...]:
        return tuple(
            e for e in self._edges_from.get(source_id, [])
            if e.target_id == target_id
        )

    def neighbors(
        self, node_id: str, relation: str | None = None, depth: int = 1
    ) -> tuple[KnowledgeNode, ...]:
        """BFS traversal up to ``depth`` hops, optionally filtering by relation."""
        visited: set[str] = {node_id}
        current_level = [node_id]
        result: list[KnowledgeNode] = []

        for _ in range(depth):
            next_level: list[str] = []
            for nid in current_level:
                for edge in self._edges_from.get(nid, []):
                    if relation is not None and edge.relation != relation:
                        continue
                    if edge.target_id not in visited:
                        visited.add(edge.target_id)
                        if edge.target_id in self._nodes:
                            result.append(self._nodes[edge.target_id])
                        next_level.append(edge.target_id)
            current_level = next_level

        return tuple(result)

    def path_between(
        self, source_id: str, target_id: str, max_depth: int = 4
    ) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]] | None:
        """BFS to find shortest path from source to target."""
        if source_id == target_id:
            node = self._nodes.get(source_id)
            return ([node], []) if node is not None else None

        visited: set[str] = {source_id}
        queue: deque[tuple[str, list[str], list[str]]] = deque()
        queue.append((source_id, [source_id], []))

        while queue:
            current, path_nodes, path_edges = queue.popleft()
            if len(path_nodes) > max_depth + 1:
                continue

            for edge in self._edges_from.get(current, []):
                if edge.target_id in visited:
                    continue
                new_path_nodes = path_nodes + [edge.target_id]
                new_path_edges = path_edges + [edge.id]

                if edge.target_id == target_id:
                    nodes = [self._nodes[nid] for nid in new_path_nodes if nid in self._nodes]
                    edges = [self._edges[eid] for eid in new_path_edges if eid in self._edges]
                    return (nodes, edges)

                visited.add(edge.target_id)
                queue.append((edge.target_id, new_path_nodes, new_path_edges))

        return None

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw: Any = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        data = cast(dict[str, Any], raw)
        for entry in cast(list[Any], data.get("nodes", [])):
            if not isinstance(entry, dict):
                continue
            try:
                node = deserialise_node(cast(dict[str, Any], entry))
            except (KeyError, TypeError, ValueError):
                continue
            self._nodes[node.id] = node
            self._nodes_by_name[node.name] = node
        for entry in cast(list[Any], data.get("edges", [])):
            if not isinstance(entry, dict):
                continue
            try:
                edge = deserialise_edge(cast(dict[str, Any], entry))
            except (KeyError, TypeError, ValueError):
                continue
            self._edges[edge.id] = edge
            self._edges_from.setdefault(edge.source_id, []).append(edge)
            self._edges_to.setdefault(edge.target_id, []).append(edge)

    def _flush(self) -> None:
        atomic_write_text(
            self._path,
            json.dumps(
                {
                    "nodes": [serialise_node(n) for n in self._nodes.values()],
                    "edges": [serialise_edge(e) for e in self._edges.values()],
                }
            ),
        )
