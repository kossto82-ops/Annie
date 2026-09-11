"""Tests for the knowledge graph: nodes, edges, stores, and entity extraction."""

from __future__ import annotations

import sqlite3

import pytest

from jarvis.domain.entities.knowledge_edge import KnowledgeEdge
from jarvis.domain.entities.knowledge_node import KnowledgeNode
from jarvis.domain.enums.node_kind import NodeKind
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.entity_extraction import extract_entities
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.in_memory_knowledge_graph_store import InMemoryKnowledgeGraphStore
from jarvis.infrastructure.sqlite_knowledge_graph_store import SqliteKnowledgeGraphStore
from jarvis.domain.entities.belief import Belief


def _node(kind: NodeKind = NodeKind.CONCEPT, name: str = "test") -> KnowledgeNode:
    return KnowledgeNode(kind=kind, name=name)


def _edge(source: str, target: str, relation: str = "knows") -> KnowledgeEdge:
    return KnowledgeEdge(source_id=source, target_id=target, relation=relation)


def _ev(content: str = "observation") -> Evidence:
    return Evidence(
        content=content,
        source=EvidenceSource.DIRECT_OBSERVATION,
        weight=Confidence(0.6),
        supports=True,
    )


# --- KnowledgeNode tests ---

class TestKnowledgeNode:
    def test_requires_kind_and_name(self) -> None:
        node = _node(NodeKind.PERSON, "Alice")
        assert node.kind == NodeKind.PERSON
        assert node.name == "Alice"

    def test_assigned_id_when_none(self) -> None:
        node = _node()
        assert node.id

    def test_uses_provided_id(self) -> None:
        node = KnowledgeNode(kind=NodeKind.CONCEPT, name="test", id="n1")
        assert node.id == "n1"

    def test_confidence_none_without_evidence(self) -> None:
        node = _node()
        assert node.confidence == Confidence.none()

    def test_confidence_increases_with_evidence(self) -> None:
        node = _node()
        node.add_evidence(_ev())
        assert node.confidence.value > 0.0

    def test_properties_dict(self) -> None:
        node = KnowledgeNode(
            kind=NodeKind.PROJECT,
            name="Annie",
            properties={"language": "python"},
        )
        assert node.properties["language"] == "python"

    def test_repr(self) -> None:
        node = _node(NodeKind.PERSON, "Alice")
        r = repr(node)
        assert "Alice" in r
        assert "person" in r


# --- KnowledgeEdge tests ---

class TestKnowledgeEdge:
    def test_requires_source_target_relation(self) -> None:
        edge = _edge("s1", "t1", "works_on")
        assert edge.source_id == "s1"
        assert edge.target_id == "t1"
        assert edge.relation == "works_on"

    def test_weight_none_without_evidence(self) -> None:
        edge = _edge("s1", "t1")
        assert edge.weight == Confidence.none()

    def test_weight_increases_with_evidence(self) -> None:
        edge = _edge("s1", "t1")
        edge.add_evidence(_ev())
        assert edge.weight.value > 0.0

    def test_repr(self) -> None:
        edge = _edge("s1", "t1", "knows")
        r = repr(edge)
        assert "knows" in r


# --- InMemoryKnowledgeGraphStore tests ---

class TestInMemoryKnowledgeGraphStore:
    def test_save_and_get_node(self) -> None:
        store = InMemoryKnowledgeGraphStore()
        node = _node(NodeKind.PERSON, "Alice")
        store.save_node(node)
        assert store.get_node(node.id) is node

    def test_get_node_by_name(self) -> None:
        store = InMemoryKnowledgeGraphStore()
        node = _node(NodeKind.PERSON, "Alice")
        store.save_node(node)
        assert store.get_node_by_name("Alice") is node

    def test_get_node_by_name_with_kind(self) -> None:
        store = InMemoryKnowledgeGraphStore()
        store.save_node(_node(NodeKind.PERSON, "Alice"))
        store.save_node(_node(NodeKind.CONCEPT, "Alice"))
        results = [store.get_node_by_name("Alice", NodeKind.PERSON)]
        assert len(results) == 1

    def test_all_nodes(self) -> None:
        store = InMemoryKnowledgeGraphStore()
        store.save_node(_node(name="a"))
        store.save_node(_node(name="b"))
        assert len(store.all_nodes()) == 2

    def test_save_and_get_edge(self) -> None:
        store = InMemoryKnowledgeGraphStore()
        n1 = _node(name="Alice")
        n2 = _node(name="Bob")
        store.save_node(n1)
        store.save_node(n2)
        edge = _edge(n1.id, n2.id, "knows")
        store.save_edge(edge)
        assert store.get_edge(edge.id) is edge

    def test_edges_from_and_to(self) -> None:
        store = InMemoryKnowledgeGraphStore()
        n1 = _node(name="Alice")
        n2 = _node(name="Bob")
        store.save_node(n1)
        store.save_node(n2)
        edge = _edge(n1.id, n2.id, "knows")
        store.save_edge(edge)
        assert len(store.edges_from(n1.id)) == 1
        assert len(store.edges_to(n2.id)) == 1
        assert len(store.edges_from(n2.id)) == 0

    def test_edges_between(self) -> None:
        store = InMemoryKnowledgeGraphStore()
        n1 = _node(name="Alice")
        n2 = _node(name="Bob")
        store.save_node(n1)
        store.save_node(n2)
        e1 = _edge(n1.id, n2.id, "knows")
        e2 = _edge(n2.id, n1.id, "knows")
        store.save_edge(e1)
        store.save_edge(e2)
        assert len(store.edges_between(n1.id, n2.id)) == 1

    def test_neighbors(self) -> None:
        store = InMemoryKnowledgeGraphStore()
        n1 = _node(name="Alice")
        n2 = _node(name="Bob")
        n3 = _node(name="Charlie")
        store.save_node(n1)
        store.save_node(n2)
        store.save_node(n3)
        store.save_edge(_edge(n1.id, n2.id, "knows"))
        store.save_edge(_edge(n2.id, n3.id, "knows"))
        neighbors = store.neighbors(n1.id, depth=2)
        assert len(neighbors) == 2
        names = {n.name for n in neighbors}
        assert "Bob" in names
        assert "Charlie" in names

    def test_neighbors_with_relation_filter(self) -> None:
        store = InMemoryKnowledgeGraphStore()
        n1 = _node(name="Alice")
        n2 = _node(name="Bob")
        n3 = _node(name="Project")
        store.save_node(n1)
        store.save_node(n2)
        store.save_node(n3)
        store.save_edge(_edge(n1.id, n2.id, "knows"))
        store.save_edge(_edge(n1.id, n3.id, "works_on"))
        neighbors = store.neighbors(n1.id, relation="knows")
        assert len(neighbors) == 1
        assert neighbors[0].name == "Bob"

    def test_path_between(self) -> None:
        store = InMemoryKnowledgeGraphStore()
        n1 = _node(name="Alice")
        n2 = _node(name="Bob")
        n3 = _node(name="Charlie")
        store.save_node(n1)
        store.save_node(n2)
        store.save_node(n3)
        store.save_edge(_edge(n1.id, n2.id, "knows"))
        store.save_edge(_edge(n2.id, n3.id, "knows"))
        result = store.path_between(n1.id, n3.id)
        assert result is not None
        nodes, edges = result
        assert len(nodes) == 3
        assert len(edges) == 2

    def test_path_between_no_path(self) -> None:
        store = InMemoryKnowledgeGraphStore()
        n1 = _node(name="Alice")
        n2 = _node(name="Bob")
        store.save_node(n1)
        store.save_node(n2)
        result = store.path_between(n1.id, n2.id)
        assert result is None

    def test_path_between_same_node(self) -> None:
        store = InMemoryKnowledgeGraphStore()
        n1 = _node(name="Alice")
        store.save_node(n1)
        result = store.path_between(n1.id, n1.id)
        assert result is not None
        nodes, edges = result
        assert len(nodes) == 1
        assert len(edges) == 0


# --- SqliteKnowledgeGraphStore tests ---

class TestSqliteKnowledgeGraphStore:
    def _make_store(self) -> SqliteKnowledgeGraphStore:
        conn = sqlite3.connect(":memory:")
        return SqliteKnowledgeGraphStore(conn)

    def test_save_and_get_node(self) -> None:
        store = self._make_store()
        node = _node(NodeKind.PERSON, "Alice")
        store.save_node(node)
        assert store.get_node(node.id) is node

    def test_save_and_get_edge(self) -> None:
        store = self._make_store()
        n1 = _node(name="Alice")
        n2 = _node(name="Bob")
        store.save_node(n1)
        store.save_node(n2)
        edge = _edge(n1.id, n2.id, "knows")
        store.save_edge(edge)
        assert store.get_edge(edge.id) is edge

    def test_persistence(self) -> None:
        conn = sqlite3.connect(":memory:")
        store1 = SqliteKnowledgeGraphStore(conn)
        n1 = _node(name="Alice")
        store1.save_node(n1)
        store2 = SqliteKnowledgeGraphStore(conn)
        assert store2.get_node(n1.id) is not None

    def test_neighbors(self) -> None:
        store = self._make_store()
        n1 = _node(name="Alice")
        n2 = _node(name="Bob")
        store.save_node(n1)
        store.save_node(n2)
        store.save_edge(_edge(n1.id, n2.id, "knows"))
        neighbors = store.neighbors(n1.id)
        assert len(neighbors) == 1
        assert neighbors[0].name == "Bob"

    def test_path_between(self) -> None:
        store = self._make_store()
        n1 = _node(name="Alice")
        n2 = _node(name="Bob")
        n3 = _node(name="Charlie")
        store.save_node(n1)
        store.save_node(n2)
        store.save_node(n3)
        store.save_edge(_edge(n1.id, n2.id, "knows"))
        store.save_edge(_edge(n2.id, n3.id, "knows"))
        result = store.path_between(n1.id, n3.id)
        assert result is not None
        nodes, edges = result
        assert len(nodes) == 3


# --- Entity extraction tests ---

class TestEntityExtraction:
    def test_extracts_proper_names(self) -> None:
        belief = Belief(statement="Alice trabaja en el proyecto Annie")
        belief.add_evidence(_ev("observación de Alice"))
        result = extract_entities(belief)
        names = {n.name for n in result.new_nodes}
        assert "Alice" in names
        assert "Annie" in names

    def test_detects_relation(self) -> None:
        belief = Belief(statement="Alice trabaja en el proyecto Annie")
        belief.add_evidence(_ev())
        result = extract_entities(belief)
        assert len(result.new_edges) >= 1
        assert result.new_edges[0].relation == "works_on"

    def test_uses_existing_nodes(self) -> None:
        existing = KnowledgeNode(kind=NodeKind.CONCEPT, name="Alice", id="existing")
        belief = Belief(statement="Alice trabaja en el proyecto Annie")
        belief.add_evidence(_ev())
        result = extract_entities(belief, existing_nodes=(existing,))
        # Alice should use existing node, Annie should be new
        assert len(result.new_nodes) == 1
        assert result.new_nodes[0].name == "Annie"

    def test_no_entities(self) -> None:
        belief = Belief(statement="the weather is nice today")
        belief.add_evidence(_ev())
        result = extract_entities(belief)
        assert len(result.new_nodes) == 0
        assert len(result.new_edges) == 0
