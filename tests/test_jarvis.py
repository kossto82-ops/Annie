"""End-to-end tests for the cognitive vertical slice, now grounded in evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis import Jarvis
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.events.episode_events import EpisodeCompleted, EpisodeStarted
from jarvis.domain.events.evidence_events import EvidenceAdded
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
_TRAIT_PHRASE = "prefers simplicity"  # must appear verbatim in a relevant trigger


def _ev(
    weight: float,
    *,
    supports: bool = True,
    content: str = "observation",
    at: datetime | None = None,
) -> Evidence:
    kwargs: dict[str, object] = {
        "content": content,
        "source": EvidenceSource.USER_STATEMENT,
        "weight": Confidence(weight),
        "supports": supports,
    }
    if at is not None:
        kwargs["observed_at"] = at
    return Evidence(**kwargs)  # type: ignore[arg-type]


class TestThink:
    def test_returns_a_completed_episode(self) -> None:
        episode = Jarvis().think("I need to understand a problem.")
        assert episode.state == EpisodeState.COMPLETED
        assert episode.result is not None
        assert "I need to understand a problem." in episode.result

    def test_each_think_is_an_independent_episode(self) -> None:
        jarvis = Jarvis()
        assert jarvis.think("a").id != jarvis.think("b").id


class TestEpistemologyDrivesTheDecision:
    def test_no_evidence_yields_an_honest_non_conclusion(self) -> None:
        # Vision §37: with no evidence, Jarvis says so rather than fabricating.
        episode = Jarvis().think("does my companion prefer simplicity?")
        assert episode.result is not None
        assert "Insufficient evidence" in episode.result
        assert episode.working_belief is not None
        assert episode.working_belief.confidence == Confidence.none()

    def test_strong_evidence_yields_a_grounded_conclusion(self) -> None:
        episode = Jarvis().think(
            "does my companion prefer simplicity?",
            evidence=[_ev(0.9), _ev(0.8), _ev(0.9)],
        )
        assert episode.result is not None
        assert "Concluded" in episode.result
        assert episode.working_belief is not None
        assert episode.working_belief.confidence.value >= 0.5

    def test_weak_evidence_yields_a_tentative_conclusion(self) -> None:
        episode = Jarvis().think("is my companion in a hurry?", evidence=[_ev(0.1)])
        assert episode.result is not None
        assert "Tentative" in episode.result


class TestEvidenceRequest:
    def test_an_ungrounded_episode_asks_for_the_evidence_it_needs(self) -> None:
        # Vision §16/§37: name the gap, do not guess.
        question = "does my companion prefer simplicity?"
        episode = Jarvis().think(question)
        request = episode.evidence_request
        assert request is not None
        assert request.question == question
        assert request.statement == episode.working_belief.statement  # type: ignore[union-attr]
        assert request.confidence == Confidence.none()
        assert question in request.needed

    def test_a_tentative_episode_also_asks_for_more(self) -> None:
        episode = Jarvis().think("is my companion busy?", evidence=[_ev(0.1)])
        assert episode.evidence_request is not None

    def test_a_grounded_episode_asks_for_nothing(self) -> None:
        episode = Jarvis().think(
            "does my companion prefer simplicity?", evidence=[_ev(0.9), _ev(0.9)]
        )
        assert episode.evidence_request is None

    def test_grounded_but_narrow_evidence_warns_of_overfitting(self) -> None:
        # High confidence from a single burst is flagged as possible overfitting.
        episode = Jarvis().think(
            "does my companion prefer simplicity?",
            evidence=[_ev(0.9, at=_EPOCH), _ev(0.9, at=_EPOCH)],
        )
        assert episode.result is not None
        assert "Concluded" in episode.result
        assert "overfitting" in episode.result

    def test_grounded_and_time_spread_evidence_does_not_warn(self) -> None:
        episode = Jarvis().think(
            "does my companion prefer simplicity?",
            evidence=[_ev(0.9, at=_EPOCH), _ev(0.9, at=_EPOCH + timedelta(days=90))],
        )
        assert episode.result is not None
        assert "Concluded" in episode.result
        assert "overfitting" not in episode.result


class TestEventFlow:
    def test_emits_started_then_completed_when_ungrounded(self) -> None:
        jarvis = Jarvis()
        events: list[CognitiveEvent] = []
        jarvis.nervous_system.subscribe(CognitiveEvent, events.append)  # type: ignore[arg-type]
        episode = jarvis.think("hello")
        assert [type(e) for e in events] == [EpisodeStarted, EpisodeCompleted]
        assert all(e.episode_id == episode.id for e in events)

    def test_belief_events_flow_when_evidence_is_provided(self) -> None:
        jarvis = Jarvis()
        events: list[CognitiveEvent] = []
        jarvis.nervous_system.subscribe(CognitiveEvent, events.append)  # type: ignore[arg-type]
        jarvis.think("does my companion prefer simplicity?", evidence=[_ev(0.9)])
        kinds = [type(e) for e in events]
        assert kinds[0] is EpisodeStarted
        assert EvidenceAdded in kinds
        assert kinds[-1] is EpisodeCompleted

    def test_grounded_episode_can_explain_its_conclusion(self) -> None:
        episode = Jarvis().think(
            "does my companion prefer simplicity?",
            evidence=[_ev(0.9, content="chose the simpler design")],
        )
        assert episode.working_belief is not None
        explanation = episode.working_belief.explain()
        assert explanation.supporting  # provenance is reconstructable (Vision §8)


class TestContinuityAcrossEpisodes:
    def test_a_belief_persists_and_evolves_across_episodes(self) -> None:
        # The essence of Jarvis: it does not start from zero each time (Vision §3).
        jarvis = Jarvis()
        question = "does my companion prefer simplicity?"

        first = jarvis.think(question, evidence=[_ev(0.5)])
        assert first.working_belief is not None
        confidence_after_first = first.working_belief.confidence  # immutable snapshot

        second = jarvis.think(question, evidence=[_ev(0.5)])

        assert second.working_belief is first.working_belief  # same belief retrieved
        assert second.working_belief is not None
        assert second.working_belief.confidence.is_stronger_than(
            confidence_after_first
        )  # accumulated evidence across episodes raised confidence

    def test_evidence_accumulates_in_the_remembered_belief(self) -> None:
        jarvis = Jarvis()
        question = "is my companion busy this week?"
        jarvis.think(question, evidence=[_ev(0.4)])
        second = jarvis.think(question, evidence=[_ev(0.4)])
        assert second.working_belief is not None
        assert len(second.working_belief.evidence) == 2

    def test_different_triggers_form_independent_beliefs(self) -> None:
        jarvis = Jarvis()
        one = jarvis.think("question A", evidence=[_ev(0.5)])
        two = jarvis.think("question B", evidence=[_ev(0.5)])
        assert one.working_belief is not two.working_belief

    def test_each_think_is_remembered_as_an_episode(self) -> None:
        jarvis = Jarvis()
        jarvis.think("question A")
        jarvis.think("question B")
        history = jarvis.episodes.history()
        assert [r.trigger for r in history] == ["question A", "question B"]
        assert all(isinstance(r, EpisodeRecord) for r in history)

    def test_the_record_links_to_the_episode_and_its_belief(self) -> None:
        jarvis = Jarvis()
        episode = jarvis.think("question A", evidence=[_ev(0.9)])
        record = jarvis.episodes.history()[-1]
        assert record.episode_id == episode.id
        assert episode.working_belief is not None
        assert record.working_belief_id == episode.working_belief.id
        assert record.decision == episode.result
        assert record.outcome == EpisodeState.COMPLETED

    def test_confidence_is_still_derived_not_asserted(self) -> None:
        # Memory is not truth (Vision §22): a remembered belief with only weak
        # evidence stays weak; storage never inflates confidence.
        jarvis = Jarvis()
        question = "does my companion dislike meetings?"
        jarvis.think(question, evidence=[_ev(0.1)])
        second = jarvis.think(question)  # revisited with no new evidence
        assert second.result is not None
        assert "Tentative" in second.result


class TestSelfObservation:
    def test_no_self_belief_without_enough_history(self) -> None:
        jarvis = Jarvis()
        jarvis.think("only one question")
        assert jarvis.observe_self() is None

    def test_habitually_ungrounded_thinking_becomes_a_self_belief(self) -> None:
        # Vision §6, §31: Jarvis notices its own tendency from measurable history.
        jarvis = Jarvis()
        for topic in ("a", "b", "c"):
            jarvis.think(f"an unfounded question about {topic}")  # no evidence
        self_belief = jarvis.observe_self()
        assert self_belief is not None
        assert self_belief.confidence.value > 0.0
        assert "sufficient evidence" in self_belief.statement

    def test_well_grounded_thinking_does_not_incriminate_jarvis(self) -> None:
        jarvis = Jarvis()
        for topic in ("a", "b", "c"):
            jarvis.think(
                f"question about {topic}",
                evidence=[
                    _ev(0.9, at=_EPOCH),
                    _ev(0.9, at=_EPOCH + timedelta(days=60)),
                ],
            )
        self_belief = jarvis.observe_self()
        assert self_belief is not None
        assert self_belief.confidence == Confidence.none()


class TestOverconfidenceSelfObservation:
    def test_grounded_but_narrow_conclusions_form_an_overconfidence_belief(self) -> None:
        # Vision §6/§11: notice concluding confidently on temporally thin evidence.
        jarvis = Jarvis()
        for topic in ("a", "b", "c"):
            # Both pieces at the same instant -> grounded but zero stability.
            jarvis.think(
                f"question about {topic}",
                evidence=[_ev(0.9, at=_EPOCH), _ev(0.9, at=_EPOCH)],
            )
        belief = jarvis.observe_overconfidence()
        assert belief is not None
        assert belief.confidence.value > 0.0

    def test_stable_grounded_conclusions_do_not(self) -> None:
        jarvis = Jarvis()
        for topic in ("a", "b", "c"):
            jarvis.think(
                f"question about {topic}",
                evidence=[
                    _ev(0.9, at=_EPOCH),
                    _ev(0.9, at=_EPOCH + timedelta(days=60)),
                ],
            )
        belief = jarvis.observe_overconfidence()
        assert belief is not None
        assert belief.confidence == Confidence.none()

    def test_self_beliefs_aggregates_the_tendencies_it_can_judge(self) -> None:
        jarvis = Jarvis()
        for topic in ("a", "b", "c"):
            jarvis.think(f"an unfounded question about {topic}")  # evidence habit only
        statements = [b.statement for b in jarvis.self_beliefs()]
        assert any("sufficient evidence" in s for s in statements)


class TestCuriosity:
    def _make_habitually_ungrounded(self) -> Jarvis:
        jarvis = Jarvis()
        for topic in ("a", "b", "c", "d"):
            jarvis.think(f"an unfounded question about {topic}")
        return jarvis

    def test_a_healthy_jarvis_feels_no_curiosity(self) -> None:
        jarvis = Jarvis()
        for topic in ("a", "b", "c"):
            jarvis.think(f"question about {topic}", evidence=[_ev(0.9), _ev(0.9)])
        assert jarvis.feel_curious() is None

    def test_a_recognised_weakness_raises_curiosity(self) -> None:
        assert self._make_habitually_ungrounded().feel_curious() is not None

    def test_pursuing_curiosity_runs_a_self_triggered_episode(self) -> None:
        # The first episode Jarvis initiates on its own (Vision §16, §31).
        jarvis = self._make_habitually_ungrounded()
        impulse = jarvis.feel_curious()
        assert impulse is not None
        episode = jarvis.pursue(impulse)
        assert episode.origin is TriggerOrigin.CURIOSITY
        assert episode.state == EpisodeState.COMPLETED

    def test_self_triggered_episodes_do_not_inflate_the_habit(self) -> None:
        # Pursuing curiosity must not feed the very tendency it responds to.
        jarvis = self._make_habitually_ungrounded()
        before = jarvis.observe_self()
        assert before is not None
        jarvis.pursue(jarvis.feel_curious())  # type: ignore[arg-type]
        after = jarvis.observe_self()
        assert after is not None
        assert len(after.evidence) == len(before.evidence)  # curiosity episode excluded


class TestCompanionModel:
    _TRAIT = "prefers simplicity"

    def test_jarvis_builds_a_model_of_its_companion(self) -> None:
        jarvis = Jarvis()
        jarvis.observe_companion(self._TRAIT, _ev(0.9, content="chose the simpler design"))
        belief = jarvis.companion.belief_about(self._TRAIT)
        assert belief is not None
        assert belief.confidence.value > 0.0
        assert self._TRAIT in belief.explain().narrate()

    def test_companion_observations_flow_through_the_nervous_system(self) -> None:
        jarvis = Jarvis()
        events: list[CognitiveEvent] = []
        jarvis.nervous_system.subscribe(CognitiveEvent, events.append)  # type: ignore[arg-type]
        jarvis.observe_companion(self._TRAIT, _ev(0.9))
        assert any(isinstance(e, EvidenceAdded) for e in events)

    def test_the_model_is_separate_from_working_conclusions(self) -> None:
        # A belief about the companion is not the same as a think() conclusion.
        jarvis = Jarvis()
        jarvis.observe_companion(self._TRAIT, _ev(0.9))
        jarvis.think("some unrelated question")
        assert [b.statement for b in jarvis.companion.beliefs()] == [self._TRAIT]


class TestCompanionModelInformsCognition:
    _TRAIT = "prefers simplicity"

    def _make_confident(self, jarvis: Jarvis) -> None:
        jarvis.observe_companion(self._TRAIT, _ev(0.9))
        jarvis.observe_companion(self._TRAIT, _ev(0.9))

    def test_prior_knowledge_raises_confidence_over_a_blank_slate(self) -> None:
        # Vision §3: past understanding shapes new interpretation.
        question = f"will my companion be happy given they {_TRAIT_PHRASE}?"

        blank = Jarvis().think(question)
        assert blank.working_belief is not None

        informed = Jarvis()
        self._make_confident(informed)
        episode = informed.think(question)
        assert episode.working_belief is not None
        assert episode.working_belief.confidence.is_stronger_than(
            blank.working_belief.confidence
        )

    def test_no_relevant_belief_leaves_cognition_unchanged(self) -> None:
        jarvis = Jarvis()
        jarvis.observe_companion("likes strong coffee", _ev(0.9))
        jarvis.observe_companion("likes strong coffee", _ev(0.9))
        episode = jarvis.think(f"will they be happy if they {_TRAIT_PHRASE}?")
        assert episode.working_belief is not None
        assert episode.working_belief.confidence == Confidence.none()

    def test_a_weakly_held_belief_does_not_inform_cognition(self) -> None:
        jarvis = Jarvis()
        jarvis.observe_companion(self._TRAIT, _ev(0.1))  # stays below threshold
        episode = jarvis.think(f"do they {_TRAIT_PHRASE}?")
        assert episode.working_belief is not None
        assert episode.working_belief.confidence == Confidence.none()


class TestLearning:
    def test_a_fresh_jarvis_gives_a_plain_non_conclusion(self) -> None:
        episode = Jarvis().think("some ungrounded question")
        assert episode.result is not None
        assert "Insufficient evidence" in episode.result
        assert "asking for evidence" not in episode.result

    def test_jarvis_changes_behaviour_once_it_recognises_the_habit(self) -> None:
        # Vision §20: a recognised tendency must change future behaviour.
        jarvis = Jarvis()
        for topic in ("a", "b", "c"):
            jarvis.think(f"unfounded question about {topic}")  # establishes the habit
        learned = jarvis.think("yet another unfounded question")
        assert learned.result is not None
        assert "I have learned" in learned.result
        assert "asking for evidence" in learned.result

    def test_the_learned_behaviour_reverts_when_the_habit_stops(self) -> None:
        # Evidence-driven, not a permanent mode: it fades as Jarvis does better.
        jarvis = Jarvis()
        for topic in ("a", "b", "c"):
            jarvis.think(f"unfounded question about {topic}")  # habit forms
        for topic in ("d", "e", "f"):
            jarvis.think(f"grounded question about {topic}", evidence=[_ev(0.9), _ev(0.9)])
        reverted = jarvis.think("a final unfounded question")
        assert reverted.result is not None
        assert "Insufficient evidence" in reverted.result
        assert "asking for evidence" not in reverted.result
