"""End-to-end tests for the cognitive vertical slice, now grounded in evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis import Jarvis
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.events.episode_events import EpisodeCompleted, EpisodeStarted
from jarvis.domain.events.evidence_events import EvidenceAdded
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


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
            jarvis.think(f"question about {topic}", evidence=[_ev(0.9), _ev(0.9)])
        self_belief = jarvis.observe_self()
        assert self_belief is not None
        assert self_belief.confidence == Confidence.none()
