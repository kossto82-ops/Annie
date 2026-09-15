"""Relation-aware graph recall (P2-B).

A stored relation (``works_on``, ``knows``, ...) is a *retrieval cue*, never
authority (Vision §22): when the trigger names one, only that relation
traverses; with no cue the traversal stays unfiltered. The recalled node is
context, never evidence -- a poisoned edge cannot move the derived confidence.
"""

from __future__ import annotations

from jarvis.domain.entities.knowledge_edge import KnowledgeEdge
from jarvis.domain.entities.knowledge_node import KnowledgeNode
from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.enums.node_kind import NodeKind
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.executive.executive_controller import relation_cues_for, working_statement
from jarvis.infrastructure.in_memory_knowledge_graph_store import InMemoryKnowledgeGraphStore
from jarvis.jarvis import Jarvis


def _graph_with_alice() -> InMemoryKnowledgeGraphStore:
    graph = InMemoryKnowledgeGraphStore()
    alice = KnowledgeNode(kind=NodeKind.PERSON, name="Alice")
    project = KnowledgeNode(kind=NodeKind.PROJECT, name="Project X")
    bob = KnowledgeNode(kind=NodeKind.PERSON, name="Bob")
    for node in (alice, project, bob):
        graph.save_node(node)
    graph.save_edge(KnowledgeEdge(alice.id, project.id, "works_on"))
    graph.save_edge(KnowledgeEdge(alice.id, bob.id, "knows"))
    return graph


class TestRelationCuesFor:
    def test_a_named_relation_is_a_cue(self) -> None:
        relations = relation_cues_for("what does Alice work on?", ("works_on", "knows"))
        assert relations == ("works_on",)

    def test_stem_bridges_trailing_s_plurals(self) -> None:
        assert relation_cues_for("does Bob know Alice?", ("knows",)) == ("knows",)

    def test_multiword_relations_match_any_part(self) -> None:
        assert relation_cues_for("project status", ("project_owner", "needs")) == (
            "project_owner",
        )

    def test_no_cue_returns_empty_and_stays_unfiltered(self) -> None:
        assert relation_cues_for("anything connected to Alice?", ("works_on", "knows")) == ()


class TestRelationAwareGraphRecall:
    def _jarvis(self) -> Jarvis:
        return Jarvis(knowledge_graph_store=_graph_with_alice())

    def _graph_memories(self, jarvis: Jarvis, trigger: str) -> list[RecalledMemory]:
        episode = jarvis.perceive(trigger, trigger=trigger)
        return [
            m
            for m in episode.recalled_memories
            if m.kind is MemoryKind.GRAPH_NODE
        ]

    def test_a_named_relation_filters_the_traversal(self) -> None:
        jarvis = self._jarvis()
        memories = self._graph_memories(jarvis, "what does Alice work on?")
        contents = [m.content for m in memories]
        assert any("Project X" in text for text in contents)
        assert not any("Bob" in text for text in contents)
        provenance = {m.provenance for m in memories}
        assert any("via works_on" in source for source in provenance)

    def test_no_cue_keeps_the_unfiltered_traversal(self) -> None:
        jarvis = self._jarvis()
        memories = self._graph_memories(jarvis, "anything connected to Alice?")
        contents = [m.content for m in memories]
        assert any("Project X" in text for text in contents)
        assert any("Bob" in text for text in contents)

    def test_poisoned_relation_is_context_never_confidence(self) -> None:
        jarvis = self._jarvis()
        trigger = "what does Alice work on?"
        memories = self._graph_memories(jarvis, trigger)
        assert memories
        belief = jarvis.beliefs.get_by_statement(working_statement(trigger))
        assert belief is not None
        # Recall rode the episode as context: the graph node is remembered
        # memory, never belief evidence, so it cannot move the derived
        # confidence -- a hostile edge surfaces as context at most.
        graph_contents = {m.content for m in memories}
        assert not graph_contents & {piece.content for piece in belief.evidence}