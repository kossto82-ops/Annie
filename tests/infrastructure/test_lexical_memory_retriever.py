"""Tests for the lexical memory retriever: query -> ranked recall (Vision §3, §37).

Inc B: retrieval only. The retriever surfaces relevant memories; it is not yet
wired into the conversation path. These tests build the stores directly so the
ranking is fully controlled and deterministic.
"""

from __future__ import annotations

from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.retrieval.memory_retriever import MemoryRetriever
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.executive.executive_controller import working_statement
from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore
from jarvis.infrastructure.in_memory_episode_store import InMemoryEpisodeStore
from jarvis.infrastructure.lexical_memory_retriever import LexicalMemoryRetriever


def _belief(statement: str, *, supports: bool = True) -> Belief:
    belief = Belief(statement=statement)
    belief.add_evidence(
        Evidence(
            content=statement,
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(1.0),
            supports=supports,
        )
    )
    return belief


def _episode(trigger: str, decision: str, goal: str | None = None) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id="e",
        trigger=trigger,
        decision=decision,
        working_belief_id="b",
        outcome=EpisodeState.COMPLETED,
        conclusion_confidence=Confidence.none(),
        conclusion_stability=TemporalStability.none(),
        origin=TriggerOrigin.COMPANION,
        kind=EpisodeKind.CONCLUSION,
        goal=goal,
    )


def _retriever(
    *,
    beliefs: InMemoryBeliefStore | None = None,
    episodes: InMemoryEpisodeStore | None = None,
    companion: CompanionModel | None = None,
    goals: InMemoryBeliefStore | None = None,
) -> LexicalMemoryRetriever:
    return LexicalMemoryRetriever(
        beliefs=beliefs or InMemoryBeliefStore(),
        episodes=episodes or InMemoryEpisodeStore(),
        companion=companion or CompanionModel(InMemoryBeliefStore()),
        goals=goals or InMemoryBeliefStore(),
    )


class TestProtocol:
    def test_it_satisfies_the_memory_retriever_protocol(self) -> None:
        assert isinstance(_retriever(), MemoryRetriever)


class TestEmptyAndNoMatch:
    def test_an_empty_query_recalls_nothing(self) -> None:
        assert _retriever().recall("   ") == ()

    def test_a_query_that_shares_no_tokens_recalls_nothing(self) -> None:
        beliefs = InMemoryBeliefStore()
        beliefs.save(_belief(working_statement("the deployment plan")))
        assert _retriever(beliefs=beliefs).recall("gardening in winter") == ()

    def test_a_fresh_memory_recalls_nothing(self) -> None:
        assert _retriever().recall("anything at all") == ()


class TestRecall:
    def test_it_surfaces_a_relevant_world_belief(self) -> None:
        beliefs = InMemoryBeliefStore()
        beliefs.save(_belief(working_statement("the deployment plan")))
        hits = _retriever(beliefs=beliefs).recall("what about the deployment plan")
        assert len(hits) == 1
        assert hits[0].kind is MemoryKind.WORLD_BELIEF
        assert hits[0].content == "the deployment plan"
        assert hits[0].provenance == "world belief"
        assert hits[0].relevance > 0.0

    def test_it_surfaces_a_companion_trait(self) -> None:
        companion = CompanionModel(InMemoryBeliefStore())
        companion.observe(
            "the companion is named Raúl",
            Evidence(
                content="said so",
                source=EvidenceSource.USER_STATEMENT,
                weight=Confidence(1.0),
            ),
        )
        hits = _retriever(companion=companion).recall("who is Raúl")
        assert [h.kind for h in hits] == [MemoryKind.COMPANION_TRAIT]
        assert "Raúl" in hits[0].content

    def test_a_rephrased_question_still_finds_the_episode_by_surface_words(self) -> None:
        # "me llamo Ricardo" was said earlier; a later "sabes como me llamo?"
        # shares surface tokens (me, llamo) and so recalls that episode -- the win
        # lexical retrieval gives even before semantic matching (D11).
        episodes = InMemoryEpisodeStore()
        episodes.record(_episode("me llamo Raúl", "Noted about the companion."))
        hits = _retriever(episodes=episodes).recall("sabes como me llamo")
        assert len(hits) == 1
        assert hits[0].kind is MemoryKind.EPISODE
        # The remembered *utterance* (trigger) is surfaced, not the internal decision.
        assert hits[0].content == "me llamo Raúl"

    def test_it_surfaces_a_goal_by_its_own_words(self) -> None:
        goals = InMemoryBeliefStore()
        goals.save(_belief("The goal 'ship Jarvis' is reachable"))
        hits = _retriever(goals=goals).recall("how do we ship Jarvis")
        assert [h.kind for h in hits] == [MemoryKind.GOAL]
        assert hits[0].content == "ship Jarvis"


class TestRanking:
    def test_a_more_overlapping_memory_outranks_a_less_overlapping_one(self) -> None:
        beliefs = InMemoryBeliefStore()
        beliefs.save(_belief(working_statement("the deployment plan for Jarvis")))
        beliefs.save(_belief(working_statement("the deployment weather")))
        hits = _retriever(beliefs=beliefs).recall("the deployment plan for Jarvis")
        assert hits[0].content == "the deployment plan for Jarvis"
        assert hits[0].relevance > hits[1].relevance

    def test_limit_caps_the_number_of_results(self) -> None:
        beliefs = InMemoryBeliefStore()
        for n in range(5):
            beliefs.save(_belief(working_statement(f"the deployment plan number {n}")))
        hits = _retriever(beliefs=beliefs).recall("the deployment plan", limit=2)
        assert len(hits) == 2

    def test_recall_is_deterministic(self) -> None:
        beliefs = InMemoryBeliefStore()
        beliefs.save(_belief(working_statement("the deployment plan")))
        beliefs.save(_belief(working_statement("the deployment schedule")))
        retriever = _retriever(beliefs=beliefs)
        first = retriever.recall("the deployment plan and schedule")
        second = retriever.recall("the deployment plan and schedule")
        assert first == second
