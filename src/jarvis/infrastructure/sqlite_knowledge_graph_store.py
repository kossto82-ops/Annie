"""SQLite-backed KnowledgeGraphRepository.

Stores nodes and edges as JSON payloads in SQLite tables, with in-memory
caching for session semantics. Traversal operations (neighbors, path_between)
use BFS on the in-memory cache.
"""

from __future__ import annotations

import json
import sqlite3
from collections import deque
from datetime import datetime
from typing import Any

from jarvis.domain.entities.knowledge_edge import KnowledgeEdge
from jarvis.domain.entities.knowledge_node import KnowledgeNode
from jarvis.domain.enums.node_kind import NodeKind


def _serialise_node(node: KnowledgeNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "kind": node.kind.value,
        "name": node.name,
        "description": node.description,
        "properties": node.properties,
        "created_at": node.created_at.isoformat(),
    }


def _deserialise_node(data: dict[str, Any]) -> KnowledgeNode:
    return KnowledgeNode(
        kind=NodeKind(data["kind"]),
        name=data["name"],
        id=data["id"],
        description=data.get("description"),
        properties=data.get("properties", {}),
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def _serialise_edge(edge: KnowledgeEdge) -> dict[str, Any]:
    return {
        "id": edge.id,
        "source_id": edge.source_id,
        "target_id": edge.target_id,
        "relation": edge.relation,
        "created_at": edge.created_at.isoformat(),
    }


def _deserialise_edge(data: dict[str, Any]) -> KnowledgeEdge:
    return KnowledgeEdge(
        source_id=data["source_id"],
        target_id=data["target_id"],
        relation=data["relation"],
        id=data["id"],
        created_at=datetime.fromisoformat(data["created_at"]),
    )


class SqliteKnowledgeGraphStore:
    """A knowledge graph store backed by SQLite."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._nodes: dict[str, KnowledgeNode] = {}
        self._edges: dict[str, KnowledgeEdge] = {}
        self._edges_from: dict[str, list[KnowledgeEdge]] = {}
        self._edges_to: dict[str, list[KnowledgeEdge]] = {}
        self._ensure_schema()
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
        payload = json.dumps(_serialise_node(node), separators=(",", ":"))
        self._conn.execute(
            "INSERT INTO knowledge_nodes (id, name, payload) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
            (node.id, node.name, payload),
        )
        self._conn.commit()

    def all_nodes(self) -> tuple[KnowledgeNode, ...]:
        return tuple(self._nodes.values())

    def get_edge(self, edge_id: str) -> KnowledgeEdge | None:
        return self._edges.get(edge_id)

    def save_edge(self, edge: KnowledgeEdge) -> None:
        self._edges[edge.id] = edge
        self._edges_from.setdefault(edge.source_id, []).append(edge)
        self._edges_to.setdefault(edge.target_id, []).append(edge)
        payload = json.dumps(_serialise_edge(edge), separators=(",", ":"))
        self._conn.execute(
            "INSERT INTO knowledge_edges (id, source_id, target_id, payload) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
            (edge.id, edge.source_id, edge.target_id, payload),
        )
        self._conn.commit()

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

    def _ensure_schema(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS knowledge_nodes "
            "(id TEXT PRIMARY KEY, name TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS knowledge_edges "
            "(id TEXT PRIMARY KEY, source_id TEXT NOT NULL, "
            "target_id TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_edges_source ON knowledge_edges(source_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_edges_target ON knowledge_edges(target_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nodes_name ON knowledge_nodes(name)"
        )
        self._conn.commit()

    def _load(self) -> None:
        for row in self._conn.execute("SELECT payload FROM knowledge_nodes"):
            node = _deserialise_node(json.loads(row[0]))
            self._nodes[node.id] = node
        for row in self._conn.execute("SELECT payload FROM knowledge_edges"):
            edge = _deserialise_edge(json.loads(row[0]))
            self._edges[edge.id] = edge
            self._edges_from.setdefault(edge.source_id, []).append(edge)
            self._edges_to.setdefault(edge.target_id, []).append(edge)
