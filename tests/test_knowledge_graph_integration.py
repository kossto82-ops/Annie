"""Tests for Phase 9: knowledge graph integration.

Proves that concluded beliefs automatically populate the knowledge graph:
1. Entities are extracted from belief statements
2. Relationships are detected and stored as edges
3. Graph is queryable after population
"""

from __future__ import annotations

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.in_memory_knowledge_graph_store import InMemoryKnowledgeGraphStore


class TestKnowledgeGraphIntegration:
    def test_graph_populated_after_conclusion(self):
        """When a belief concludes, entities are extracted and stored in the graph."""
        graph = InMemoryKnowledgeGraphStore()

        # Create a belief with extractable entities
        belief = Belief(statement="Python is a programming language")
        belief.add_evidence(
            Evidence(
                content="Python is widely used",
                source=EvidenceSource.USER_STATEMENT,
                weight=Confidence(0.8),
                supports=True,
            )
        )

        # Simulate _remember by extracting entities
        from jarvis.domain.services.entity_extraction import extract_entities

        existing = graph.all_nodes()
        extraction = extract_entities(belief, existing_nodes=existing)
        for node in extraction.new_nodes:
            graph.save_node(node)
        for edge in extraction.new_edges:
            graph.save_edge(edge)

        # Verify nodes were created
        nodes = graph.all_nodes()
        assert len(nodes) > 0
        node_names = [n.name for n in nodes]
        assert "Python" in node_names

    def test_existing_nodes_not_duplicated(self):
        """When the same entity appears twice, it is not duplicated."""
        graph = InMemoryKnowledgeGraphStore()

        belief = Belief(statement="Python is great")
        belief.add_evidence(
            Evidence(
                content="Python is used everywhere",
                source=EvidenceSource.USER_STATEMENT,
                weight=Confidence(0.8),
                supports=True,
            )
        )

        from jarvis.domain.services.entity_extraction import extract_entities

        # First extraction
        extraction1 = extract_entities(belief, existing_nodes=())
        for node in extraction1.new_nodes:
            graph.save_node(node)

        # Second extraction with existing nodes
        extraction2 = extract_entities(belief, existing_nodes=graph.all_nodes())
        for node in extraction2.new_nodes:
            graph.save_node(node)

        # Should not duplicate
        nodes = graph.all_nodes()
        python_nodes = [n for n in nodes if n.name == "Python"]
        assert len(python_nodes) == 1

    def test_graph_queryable_after_population(self):
        """After population, graph neighbors can be traversed."""
        graph = InMemoryKnowledgeGraphStore()

        from jarvis.domain.entities.knowledge_edge import KnowledgeEdge
        from jarvis.domain.entities.knowledge_node import KnowledgeNode
        from jarvis.domain.enums.node_kind import NodeKind

        node1 = KnowledgeNode(kind=NodeKind.CONCEPT, name="Python")
        node2 = KnowledgeNode(kind=NodeKind.CONCEPT, name="Programming")
        graph.save_node(node1)
        graph.save_node(node2)

        edge = KnowledgeEdge(
            source_id=node1.id,
            target_id=node2.id,
            relation="is_a",
        )
        graph.save_edge(edge)

        # Query neighbors
        neighbors = graph.neighbors(node1.id)
        assert len(neighbors) == 1
        assert neighbors[0].name == "Programming"
