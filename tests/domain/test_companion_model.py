"""Behavioural tests for the model of the companion (Vision §5)."""

from __future__ import annotations

from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.events.belief_events import ContradictionDetected
from jarvis.domain.events.evidence_events import EvidenceAdded
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore

_TRAIT = "prefers simplicity over feature quantity"


def _ev(weight: float, *, supports: bool = True, content: str = "observation") -> Evidence:
    return Evidence(
        content=content,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(weight),
        supports=supports,
    )


class TestObserving:
    def test_nothing_believed_before_any_observation(self) -> None:
        assert CompanionModel(InMemoryBeliefStore()).belief_about(_TRAIT) is None

    def test_an_observation_forms_a_belief_about_the_companion(self) -> None:
        model = CompanionModel(InMemoryBeliefStore())
        belief = model.observe(_TRAIT, _ev(0.8))
        assert model.belief_about(_TRAIT) is belief
        assert belief.confidence.value > 0.0

    def test_repeated_observations_strengthen_the_belief(self) -> None:
        model = CompanionModel(InMemoryBeliefStore())
        model.observe(_TRAIT, _ev(0.5))
        first = model.belief_about(_TRAIT)
        assert first is not None
        after_one = first.confidence
        model.observe(_TRAIT, _ev(0.5))
        assert first.confidence.is_stronger_than(after_one)


class TestNeverAbsolute:
    def test_the_companion_can_contradict_a_belief(self) -> None:
        # Vision §5/§18: a belief about the companion is never absolute truth and
        # is weakened, not overwritten, by a contradicting statement.
        model = CompanionModel(InMemoryBeliefStore())
        model.observe(_TRAIT, _ev(0.8, content="chose the simpler design"))
        belief = model.belief_about(_TRAIT)
        assert belief is not None
        before = belief.confidence
        model.observe(_TRAIT, _ev(0.8, supports=False, content="asked for advanced mode"))
        assert before.is_stronger_than(belief.confidence)
        # The original evidence is preserved, not erased.
        assert len(belief.evidence) == 2


class TestEvents:
    def test_observations_emit_events(self) -> None:
        model = CompanionModel(InMemoryBeliefStore())
        model.observe(_TRAIT, _ev(0.8))
        model.observe(_TRAIT, _ev(0.8, supports=False))
        kinds = [type(e) for e in model.pull_events()]
        assert EvidenceAdded in kinds
        assert ContradictionDetected in kinds


class TestRelevance:
    def test_a_confident_belief_is_relevant_when_its_trait_is_in_the_trigger(self) -> None:
        model = CompanionModel(InMemoryBeliefStore())
        model.observe(_TRAIT, _ev(0.9))
        model.observe(_TRAIT, _ev(0.9))
        assert model.relevant_to(f"will they act because they {_TRAIT}?") is not None

    def test_an_unrelated_trigger_matches_nothing(self) -> None:
        model = CompanionModel(InMemoryBeliefStore())
        model.observe(_TRAIT, _ev(0.9))
        model.observe(_TRAIT, _ev(0.9))
        assert model.relevant_to("what time is it?") is None

    def test_a_weakly_held_belief_is_not_relevant(self) -> None:
        model = CompanionModel(InMemoryBeliefStore())
        model.observe(_TRAIT, _ev(0.1))  # confidence stays below the threshold
        assert model.relevant_to(f"do they {_TRAIT}?") is None


class TestSummary:
    def test_summarise_narrates_each_belief(self) -> None:
        model = CompanionModel(InMemoryBeliefStore())
        model.observe(_TRAIT, _ev(0.9, content="picked the minimal option"))
        summary = model.summarise()
        assert len(summary) == 1
        assert _TRAIT in summary[0]
        assert "picked the minimal option" in summary[0]
