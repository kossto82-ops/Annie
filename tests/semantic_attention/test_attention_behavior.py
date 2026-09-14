"""Part 3–4: Attention behavior and recall chain.

Tests:
- Part 3: Attention routing (FULL on novelty, BRIEF on repeat)
- Part 10: Attention development over episodes
- Part 15: Attention with semantic memory recall
"""
from jarvis.domain.entities.semantic_memory import SemanticMemory
from jarvis.domain.enums.attention import Attention
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.in_memory_semantic_memory_store import InMemorySemanticMemoryStore
from jarvis.jarvis import Jarvis

_TRIGGER = "supplier keeps promising delivery dates that fail"


def _evidence(text: str = "observed evidence") -> Evidence:
    return Evidence(
        content=text,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(1.0),
        supports=True,
    )


class TestAttentionRoutingNovelty:
    """Tests FULL vs BRIEF attention based on novelty."""

    def test_first_think_is_full(self):
        j = Jarvis(enable_recall=True)
        ep = j.think(_TRIGGER)
        assert ep.attention == Attention.FULL, "First think with no belief should be FULL"

    def test_same_trigger_second_time_brief(self):
        """Confirmed: 1 evidence of weight 1.0 -> belief confidence 0.5 (=grounded)."""
        j = Jarvis(enable_recall=True)
        j.think(_TRIGGER, evidence=[_evidence()])
        ep2 = j.think(_TRIGGER)
        assert ep2.attention == Attention.BRIEF, "Grounded trigger with no new evidence -> BRIEF"

    def test_same_trigger_second_new_evidence_is_full(self):
        """New evidence on a known trigger still warrants FULL (it integrates it)."""
        j = Jarvis(enable_recall=True)
        j.think(_TRIGGER, evidence=[_evidence()])
        ep2 = j.think(_TRIGGER, evidence=[_evidence("a second observation")])
        assert ep2.attention == Attention.FULL, "New evidence should keep an episode FULL"

    def test_ungrounded_repeat_stays_full(self):
        """A trigger with no confident belief never gets BRIEF (honest: not known)."""
        j = Jarvis(enable_recall=True)
        j.think(_TRIGGER)  # no evidence -> confidence 0.0
        ep2 = j.think(_TRIGGER)
        assert ep2.attention == Attention.FULL, "0.0-confidence repeat must stay FULL"

    def test_different_trigger_is_full(self):
        j = Jarvis(enable_recall=True)
        j.think(_TRIGGER, evidence=[_evidence()])
        ep2 = j.think("contractor repeatedly gives optimistic completion estimates")
        assert ep2.attention == Attention.FULL, "Different trigger should be FULL"

    def test_partial_lexical_overlap_is_full(self):
        """New trigger sharing some words but avoiding the exact statement -> FULL."""
        j = Jarvis(enable_recall=True)
        j.think(_TRIGGER, evidence=[_evidence()])
        ep2 = j.think("supplier promised delivery dates but failed them")
        assert ep2.attention == Attention.FULL

    def test_identical_lexical_overlap_is_brief(self):
        """Identical trigger text -> same working statement -> BRIEF."""
        j = Jarvis(enable_recall=True)
        j.think(_TRIGGER, evidence=[_evidence()])
        ep2 = j.think(_TRIGGER)
        assert ep2.attention == Attention.BRIEF


def _save_semantic(store: InMemorySemanticMemoryStore, pattern: str) -> None:
    """Persist a semantic memory with one supporting observation."""
    m = SemanticMemory(pattern=pattern)
    m.add_evidence(
        Evidence(
            content="supplier missed promise",
            source=EvidenceSource.SYSTEM_OBSERVATION,
            weight=Confidence(0.5),
            supports=True,
        )
    )
    m.pull_events()
    store.save(m)


class TestAttentionWithSemanticMemory:
    """Part 15: Attention behavior when semantic memory exists."""

    def test_recall_returns_semantic_memory(self):
        """Semantic memory surfaces when query shares >=20% of tokens with pattern."""
        store = InMemorySemanticMemoryStore()
        _save_semantic(store, "unsupported optimistic claims about deadlines fail")
        j = Jarvis(enable_recall=True, semantic_memory_store=store)
        recalled = j.recall("contractor hypothesized optimistic schedules")
        assert len(recalled) > 0, "Semantic memory should surface on partial token overlap"
        assert recalled[0].kind.value == "semantic"
        assert recalled[0].relevance >= 0.2

    def test_recall_empty_when_too_few_tokens_overlap(self):
        """Semantic memory filtered below the 0.2 recall relevance floor."""
        store = InMemorySemanticMemoryStore()
        _save_semantic(store, "delivery promises fail without verification")
        j = Jarvis(enable_recall=True, semantic_memory_store=store)
        recalled = j.recall("the weather in the mountains")
        assert len(recalled) == 0, "Disjoint query returns nothing"

    def test_default_jarvis_has_no_semantic_store(self):
        """Default Jarvo has no semantic memory store wired."""
        j = Jarvis()
        assert j._semantic_memory_store is None

    def test_semantic_store_not_updated_by_think(self):
        """CRITICAL: think() NEVER writes semantic memories — the store is read-only in
        the runtime path. abstract_patterns() is dead code; nothing calls it."""
        store = InMemorySemanticMemoryStore()
        j = Jarvis(enable_recall=True, semantic_memory_store=store)
        j.think(_TRIGGER, evidence=[_evidence()])
        assert len(store.all_memories()) == 0, (
            "Semantic memory store is never written by the cognition lifecycle"
        )


class TestRecallChainToDecision:
    """Tests the recall → reasoner → belief chain (critical path)."""

    def test_strong_semantic_recall_bypasses_reasoner(self):
        """A strong concept-level recall (relevance >= 0.6) already answers the
        trigger, so the live reasoner is NOT re-asked — semantic recall now
        genuinely bridges meaning (the point of the rework)."""
        from jarvis.domain.value_objects.inference import Inference

        class ProbeReasoner:
            def __init__(self):
                self.calls = 0
            def infer(self, query, memory=(), conversation=(), span=()):
                self.calls += 1
                if memory:
                    return Inference(answer="reasoned from recall")
                return None
            def infer_stream(self, query, memory=(), conversation=(), span=()):
                yield ""

        store = InMemorySemanticMemoryStore()
        _save_semantic(store, "promises without verification tend to fail")

        reasoner = ProbeReasoner()
        j = Jarvis(enable_recall=True, semantic_memory_store=store, reasoner=reasoner)
        ep = j.think("promises are unreliable")  # concepts {PROMISE, FAIL} fully match

        recalled_semantic = [m for m in ep.recalled_memories if m.kind.value == "semantic"]
        assert recalled_semantic, "Semantic memory should be recalled"
        assert recalled_semantic[0].relevance >= 0.6, "Concept match should be strong"
        assert reasoner.calls == 0, "Strong recall must not re-ask the model"

    def test_weak_semantic_recall_reaches_live_reasoner(self):
        """A present-but-weak semantic memory (relevance < 0.6) is passed to a live
        reasoner, which can ground the belief from it."""
        from jarvis.domain.value_objects.inference import Inference

        class ProbeReasoner:
            def __init__(self):
                self.last_memory = []
            def infer(self, query, memory=(), conversation=(), span=()):
                self.last_memory = list(memory)
                if memory:
                    return Inference(answer="reasoned from recall")
                return None
            def infer_stream(self, query, memory=(), conversation=(), span=()):
                yield ""

        store = InMemorySemanticMemoryStore()
        _save_semantic(store, "promises without verification tend to fail")

        reasoner = ProbeReasoner()
        j = Jarvis(enable_recall=True, semantic_memory_store=store, reasoner=reasoner)
        ep = j.think("delivery promises were reconsidered under new management")
        # concepts {DELIVER, PROMISE} share only PROMISE with pattern {PROMISE, FAIL}
        # -> relevance 0.5: surfaced but not strong enough to bypass the reasoner.

        assert len(reasoner.last_memory) > 0, "Reasoner should receive recalled memories"
        assert ep.working_belief is not None
        assert ep.working_belief.confidence.value > 0, "Belief grounded by inference evidence"

    def test_recall_without_reasoner_leaves_no_answer(self):
        """Without a live reasoner, recall memories don't generate an inference."""
        store = InMemorySemanticMemoryStore()
        _save_semantic(store, "delivery promises tend to fail")
        j = Jarvis(enable_recall=True, semantic_memory_store=store)
        ep = j.think("promises are unreliable")
        assert ep.inference is None, "SilentReasoner never infers"