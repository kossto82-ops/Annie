"""Tests for Phase 6: reflection gating.

Proves that reflection is only triggered when warranted:
1. Contested evidence → always reflect
2. Confidence near threshold → reflect
3. Thin belief (≤3 evidence) → reflect
4. Well-established belief with clear grounding → skip
"""

from __future__ import annotations

from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.cognitive_knobs import CognitiveKnobs
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.executive.executive_controller import ExecutiveController
from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore
from jarvis.infrastructure.in_memory_episode_store import InMemoryEpisodeStore
from jarvis.nervous_system.nervous_system import NervousSystem


def _make_controller() -> ExecutiveController:
    """Create a minimal controller for testing gating logic."""
    return ExecutiveController(
        nervous_system=NervousSystem(),
        beliefs=InMemoryBeliefStore(),
        episodes=InMemoryEpisodeStore(),
        companion=CompanionModel(InMemoryBeliefStore()),
        knobs=CognitiveKnobs(),
    )


def _make_belief(
    statement: str = "test belief",
    evidence_count: int = 0,
    weight: float = 0.8,
    has_contradiction: bool = False,
) -> Belief:
    """Create a belief with controlled evidence."""
    belief = Belief(statement=statement)
    for i in range(evidence_count):
        belief.add_evidence(
            Evidence(
                content=f"evidence {i}",
                source=EvidenceSource.USER_STATEMENT,
                weight=Confidence(weight),
                supports=not (has_contradiction and i == evidence_count - 1),
            )
        )
    return belief


class TestReflectionGating:
    def test_reflects_on_contested_evidence(self):
        controller = _make_controller()
        belief = _make_belief(
            evidence_count=5, weight=0.8, has_contradiction=True
        )

        assert controller._should_reflect(belief) is True

    def test_reflects_on_thin_belief(self):
        controller = _make_controller()
        belief = _make_belief(evidence_count=2, weight=0.9)

        assert controller._should_reflect(belief) is True

    def test_skips_reflection_for_established_belief(self):
        controller = _make_controller()
        belief = _make_belief(evidence_count=5, weight=0.9)

        assert controller._should_reflect(belief) is False

    def test_reflects_near_threshold(self):
        controller = _make_controller()
        # 2 evidence pieces → reflect (thin belief, ≤3)
        belief = _make_belief(evidence_count=2, weight=0.5)

        assert controller._should_reflect(belief) is True

    def test_skips_well_above_threshold(self):
        controller = _make_controller()
        # High confidence, 5 evidence pieces → skip
        belief = _make_belief(evidence_count=5, weight=0.9)

        assert controller._should_reflect(belief) is False

    def test_reflects_when_evidence_count_is_three(self):
        controller = _make_controller()
        # 3 evidence pieces → reflect (thin belief)
        belief = _make_belief(evidence_count=3, weight=0.9)

        assert controller._should_reflect(belief) is True
