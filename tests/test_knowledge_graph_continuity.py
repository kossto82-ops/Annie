"""Knowledge graph: KEEP AND WIRE (decision gate, P1).

The concrete problem: multi-hop entity recall that isolated retrieval cannot
see. Charlie is related to Alice only through Bob and shares no surface
tokens with a question about Alice, so lexical recall (beliefs, episodes,
semantic, conversation) can never surface him -- only relationship traversal
can. This file proves the wired path:

    seeded entity -> bounded traversal -> recalled context
      -> reasoning -> observable benefit (+ persistence across restart)

A control without the graph proves the benefit comes from traversal.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.domain.aggregates.cognitive_episode import CognitiveEpisode
from jarvis.domain.conversation.conversation_context import Turn
from jarvis.domain.entities.knowledge_edge import KnowledgeEdge
from jarvis.domain.entities.knowledge_node import KnowledgeNode
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.enums.node_kind import NodeKind
from jarvis.domain.reasoning.reasoning_span import SpanThread
from jarvis.domain.value_objects.inference import Inference
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.jarvis import Jarvis


def _seed_graph(jarvis: Jarvis) -> None:
    graph = jarvis.knowledge_graph
    assert graph is not None
    alice = KnowledgeNode(kind=NodeKind.PERSON, name="Alice", id="n-alice")
    bob = KnowledgeNode(kind=NodeKind.PERSON, name="Bob", id="n-bob")
    charlie = KnowledgeNode(kind=NodeKind.PERSON, name="Charlie", id="n-charlie")
    graph.save_node(alice)
    graph.save_node(bob)
    graph.save_node(charlie)
    graph.save_edge(
        KnowledgeEdge(source_id=alice.id, target_id=bob.id, relation="knows", id="e-ab")
    )
    graph.save_edge(
        KnowledgeEdge(source_id=bob.id, target_id=charlie.id, relation="knows", id="e-bc")
    )


def _graph_contents(episode: CognitiveEpisode) -> list[str]:
    return [
        memory.content
        for memory in episode.recalled_memories
        if memory.kind is MemoryKind.GRAPH_NODE
    ]


class _GraphEchoReasoner:
    """Answers from graph-traversed memories (test seam)."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, tuple[RecalledMemory, ...]]] = []

    def infer(
        self,
        query: str,
        memory: tuple[RecalledMemory, ...] = (),
        conversation: tuple[Turn, ...] = (),
        span: tuple[SpanThread, ...] = (),
    ) -> Inference | None:
        self.seen.append((query, memory))
        graph_bits = [m.content for m in memory if m.kind is MemoryKind.GRAPH_NODE]
        if not graph_bits:
            return None
        return Inference(answer=f"through relationships: {' | '.join(graph_bits)}.")


class TestGraphTraversalMatters:
    def test_two_hop_entity_surfaces_through_traversal(self, tmp_path: Path) -> None:
        jarvis = Jarvis.database(tmp_path)
        _seed_graph(jarvis)

        episode = jarvis.think("who is connected to Alice?")
        contents = _graph_contents(episode)
        # Bob (one hop) and Charlie (two hops) both arrive; Charlie shares no
        # tokens with the question, so only traversal could have found him.
        assert any("Bob" in text for text in contents)
        assert any("Charlie" in text for text in contents)

    def test_control_without_graph_finds_nothing(self) -> None:
        jarvis = Jarvis()
        assert jarvis.knowledge_graph is None
        episode = jarvis.think("who is connected to Alice?")
        assert _graph_contents(episode) == []

    def test_traversal_reaches_reasoning(self, tmp_path: Path) -> None:
        jarvis = Jarvis.database(tmp_path)
        _seed_graph(jarvis)
        probe = _GraphEchoReasoner()
        jarvis.set_reasoner(probe)

        episode = jarvis.think("who is connected to Alice?")
        assert probe.seen, "the reasoner was never consulted"
        heard = [m.content for _, memories in probe.seen for m in memories]
        assert any("Charlie" in text for text in heard)
        # The reasoned answer is remembered as clearly-sourced INFERENCE
        # evidence: traversal shaped the working belief without deciding it.
        assert episode.working_belief is not None
        inferred = [
            piece.content
            for piece in episode.working_belief.evidence
            if piece.source is EvidenceSource.INFERENCE
        ]
        assert any("Charlie" in text for text in inferred)

    def test_graph_survives_restart(self, tmp_path: Path) -> None:
        first_run = Jarvis.database(tmp_path)
        _seed_graph(first_run)
        assert any(
            "Charlie" in text
            for text in _graph_contents(first_run.think("who is connected to Alice?"))
        )

        second_run = Jarvis.database(tmp_path)
        contents = _graph_contents(second_run.think("who is connected to Alice?"))
        assert any("Charlie" in text for text in contents)

    def test_json_backend_persists_traversal(self, tmp_path: Path) -> None:
        first_run = Jarvis.persistent(tmp_path)
        assert first_run.knowledge_graph is not None
        _seed_graph(first_run)
        assert (tmp_path / "graph.json").exists()

        second_run = Jarvis.persistent(tmp_path)
        contents = _graph_contents(second_run.think("who is connected to Alice?"))
        assert any("Charlie" in text for text in contents)
