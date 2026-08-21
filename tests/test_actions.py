"""Tests for acting and learning from outcomes (Vision §27, §20)."""

from __future__ import annotations

import pytest

from jarvis import Jarvis
from jarvis.domain.enums.action_stance import ActionStance
from jarvis.domain.events.action_events import ActionOutcomeRecorded
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.value_objects.confidence import Confidence


class TestAct:
    def test_act_declares_an_intention_without_side_effects(self) -> None:
        action = Jarvis().act(
            "send the weekly summary",
            expected="the companion reads it",
            confidence=Confidence(0.7),
            reversible=False,
        )
        assert action.description == "send the weekly summary"
        assert action.expected == "the companion reads it"
        assert action.confidence == Confidence(0.7)
        assert action.reversible is False

    def test_act_requires_a_description_and_expectation(self) -> None:
        with pytest.raises(ValueError):
            Jarvis().act("   ", expected="x")
        with pytest.raises(ValueError):
            Jarvis().act("x", expected="  ")


class TestLearningFromOutcomes:
    def test_nothing_is_believed_before_any_outcome(self) -> None:
        assert Jarvis().belief_about_action("deploy the change") is None

    def test_a_met_expectation_builds_confidence(self) -> None:
        jarvis = Jarvis()
        action = jarvis.act("deploy the change", expected="tests stay green")
        jarvis.record_outcome(action, actual="tests stayed green", met_expectation=True)
        belief = jarvis.belief_about_action("deploy the change")
        assert belief is not None
        assert belief.confidence.value > 0.0

    def test_repeated_mismatches_erode_confidence(self) -> None:
        jarvis = Jarvis()
        action = jarvis.act("deploy on friday", expected="a quiet weekend")
        jarvis.record_outcome(action, actual="a quiet weekend", met_expectation=True)
        before = jarvis.belief_about_action("deploy on friday").confidence  # type: ignore[union-attr]
        again = jarvis.act("deploy on friday", expected="a quiet weekend")
        jarvis.record_outcome(again, actual="an incident", met_expectation=False)
        after = jarvis.belief_about_action("deploy on friday").confidence  # type: ignore[union-attr]
        assert before.is_stronger_than(after)

    def test_the_outcome_is_retrievable_as_provenance(self) -> None:
        jarvis = Jarvis()
        action = jarvis.act("call the client", expected="they pick up")
        jarvis.record_outcome(action, actual="voicemail", met_expectation=False)
        belief = jarvis.belief_about_action("call the client")
        assert belief is not None
        narration = belief.explain().narrate()
        assert "voicemail" in narration

    def test_recording_an_outcome_emits_an_event(self) -> None:
        jarvis = Jarvis()
        seen: list[CognitiveEvent] = []
        jarvis.nervous_system.subscribe(CognitiveEvent, seen.append)  # type: ignore[arg-type]
        action = jarvis.act("water the plants", expected="they perk up")
        jarvis.record_outcome(action, actual="they perked up", met_expectation=True)
        assert any(isinstance(e, ActionOutcomeRecorded) for e in seen)


class TestGradedAutonomy:
    def test_an_unproven_action_is_asked_first(self) -> None:
        jarvis = Jarvis()
        action = jarvis.act("restart the server", expected="it comes back up")
        assert jarvis.recommend_action(action).stance is ActionStance.ASK_FIRST

    def test_a_well_learned_reversible_action_is_suggested(self) -> None:
        jarvis = Jarvis()
        for _ in range(3):
            a = jarvis.act("tidy the notes", expected="notes are tidy", reversible=True)
            jarvis.record_outcome(a, actual="notes are tidy", met_expectation=True)
        pending = jarvis.act("tidy the notes", expected="notes are tidy", reversible=True)
        assert jarvis.recommend_action(pending).stance is ActionStance.SUGGEST

    def test_the_same_learning_but_irreversible_is_asked_first(self) -> None:
        jarvis = Jarvis()
        for _ in range(3):
            a = jarvis.act("delete the file", expected="space is freed", reversible=True)
            jarvis.record_outcome(a, actual="space is freed", met_expectation=True)
        pending = jarvis.act("delete the file", expected="space is freed", reversible=False)
        assert jarvis.recommend_action(pending).stance is ActionStance.ASK_FIRST

    def test_a_contradicted_action_is_withheld(self) -> None:
        jarvis = Jarvis()
        outcomes = [True, False, False]
        for met in outcomes:
            a = jarvis.act("deploy on friday", expected="quiet weekend")
            jarvis.record_outcome(
                a, actual="quiet" if met else "an incident", met_expectation=met
            )
        pending = jarvis.act("deploy on friday", expected="quiet weekend")
        assert jarvis.recommend_action(pending).stance is ActionStance.WITHHOLD
