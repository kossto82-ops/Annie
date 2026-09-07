"""The per-belief default weighting policy is injectable at the Jarvis root.

Every belief Jarvis creates on its own -- goals, actions, needs, companion traits,
self-observed habits -- used to be born with `DEFAULT_WEIGHTING`, with no way to
override the *source* policy at the root (the decay composition was injectable,
Increment 113, but only for episode working beliefs). This closes that gap
(Increment 144): `Jarvis(default_belief_policy=...)` and `set_belief_policy(...)`
make the per-belief default root-injectable and live, exactly like `CognitiveKnobs`.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.evidence_weighting import (
    DEFAULT_WEIGHTING,
    SourceWeightingPolicy,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.goal import Goal
from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore
from jarvis.jarvis import Jarvis


def _blind_policy() -> SourceWeightingPolicy:
    """An extreme sceptical policy: no source counts for anything."""
    return SourceWeightingPolicy(
        factors={source: 0.0 for source in EvidenceSource}
    )


def _evidence(source: EvidenceSource = EvidenceSource.USER_STATEMENT) -> Evidence:
    return Evidence(
        content="a piece of evidence",
        source=source,
        weight=Confidence(1.0),
        supports=True,
    )


class TestRootDefaultPolicy:
    def test_the_historical_default_is_unchanged(self) -> None:
        jarvis = Jarvis()
        assert jarvis.default_belief_policy() == DEFAULT_WEIGHTING
        intent = jarvis.act("tidy the room", "room is tidy")
        belief = jarvis.record_outcome(intent, "tidy", True)
        assert belief.weighting_policy == DEFAULT_WEIGHTING
        assert belief.confidence.value > 0.4  # 0.7 effective / 1.7 ~ 0.41

    def test_an_injected_policy_governs_every_fresh_belief(self) -> None:
        policy = _blind_policy()
        jarvis = Jarvis(default_belief_policy=policy)
        assert jarvis.default_belief_policy() == policy

        # Action learning.
        intent = jarvis.act("tidy the room", "room is tidy")
        belief = jarvis.record_outcome(intent, "tidy", True)
        assert belief.weighting_policy == policy
        assert belief.confidence.value < 0.01  # the policy zeroed the evidence

        # Goal reachability.
        goal = jarvis.mark_goal_reached(Goal(statement="fetch water"))
        assert goal.weighting_policy == policy
        assert goal.confidence.value < 0.01

        # Companion traits through Jarvis.
        trait = jarvis.companion.observe("rises at dawn", _evidence())
        assert trait.weighting_policy == policy

    def test_the_swap_applies_to_subsequent_creations_only(self) -> None:
        jarvis = Jarvis()
        first = jarvis.companion.observe("rises at dawn", _evidence())
        assert first.weighting_policy == DEFAULT_WEIGHTING

        policy = _blind_policy()
        jarvis.set_belief_policy(policy)
        assert jarvis.default_belief_policy() == policy
        second = jarvis.companion.observe("reads at night", _evidence())
        assert second.weighting_policy == policy
        # An existing belief is not silently re-weighted.
        earlier = jarvis.companion.belief_about("rises at dawn")
        assert earlier is not None
        assert earlier.weighting_policy == DEFAULT_WEIGHTING

    def test_the_swap_reaches_goal_creation(self) -> None:
        jarvis = Jarvis()
        jarvis.set_belief_policy(_blind_policy())
        goal = jarvis.mark_goal_reached(Goal(statement="fetch water"))
        assert goal.weighting_policy == _blind_policy()

    def test_persistent_boot_forwards_the_root_policy(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path, default_belief_policy=_blind_policy())
        assert jarvis.default_belief_policy() == _blind_policy()
        intent = jarvis.act("tidy the room", "room is tidy")
        belief = jarvis.record_outcome(intent, "tidy", True)
        assert belief.weighting_policy == _blind_policy()


class TestCompanionModelDefaultPolicy:
    def test_the_companion_aggregate_honours_an_injected_policy(self) -> None:
        model = CompanionModel(InMemoryBeliefStore(), default_policy=_blind_policy())
        trait = model.observe("rises at dawn", _evidence())
        assert trait.weighting_policy == _blind_policy()
        assert trait.confidence.value < 0.01
