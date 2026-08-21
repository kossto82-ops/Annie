"""Jarvis continuity across a simulated restart (Vision §3, §21)."""

from __future__ import annotations

from pathlib import Path

from jarvis import Jarvis
from jarvis.domain.enums.action_stance import ActionStance
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.json_belief_store import JsonBeliefStore
from jarvis.infrastructure.json_episode_store import JsonEpisodeStore


def _ev(weight: float) -> Evidence:
    return Evidence(
        content="an observation",
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(weight),
    )


def _boot(tmp_path: Path) -> Jarvis:
    return Jarvis(
        beliefs=JsonBeliefStore(tmp_path / "beliefs.json"),
        episodes=JsonEpisodeStore(tmp_path / "episodes.json"),
        companion_store=JsonBeliefStore(tmp_path / "companion.json"),
        actions_store=JsonBeliefStore(tmp_path / "actions.json"),
    )


class TestContinuityAcrossRestart:
    def test_a_belief_survives_a_restart_and_keeps_evolving(self, tmp_path: Path) -> None:
        question = "does my companion prefer simplicity?"

        first_run = _boot(tmp_path)
        first_run.think(question, evidence=[_ev(0.9)])

        # "Restart": a brand-new Jarvis reading the same files.
        second_run = _boot(tmp_path)
        episode = second_run.think(question, evidence=[_ev(0.9)])
        assert episode.working_belief is not None
        # Two pieces of evidence total -> the belief carried over and grew.
        assert len(episode.working_belief.evidence) == 2

    def test_episode_history_survives_a_restart(self, tmp_path: Path) -> None:
        first_run = _boot(tmp_path)
        first_run.think("question one")
        first_run.think("question two")

        second_run = _boot(tmp_path)
        assert [r.trigger for r in second_run.episodes.history()] == [
            "question one",
            "question two",
        ]

    def test_self_model_survives_a_restart(self, tmp_path: Path) -> None:
        # A tendency learned before the restart is still known after it.
        first_run = _boot(tmp_path)
        for topic in ("a", "b", "c"):
            first_run.think(f"an unfounded question about {topic}")

        second_run = _boot(tmp_path)
        self_belief = second_run.observe_self()
        assert self_belief is not None
        assert self_belief.confidence.value > 0.0

    def test_action_learning_survives_a_restart(self, tmp_path: Path) -> None:
        # What Jarvis learned about acting must outlive the process (Vision §21, §27).
        first_run = _boot(tmp_path)
        for _ in range(3):
            action = first_run.act("tidy the notes", expected="tidy", reversible=True)
            first_run.record_outcome(action, actual="tidy", met_expectation=True)
        belief = first_run.belief_about_action("tidy the notes")
        assert belief is not None
        confidence_before = belief.confidence

        second_run = _boot(tmp_path)
        reloaded = second_run.belief_about_action("tidy the notes")
        assert reloaded is not None
        assert reloaded.confidence == confidence_before
        # And the recommendation it drives is unchanged after the restart.
        pending = second_run.act("tidy the notes", expected="tidy", reversible=True)
        assert second_run.recommend_action(pending).stance is ActionStance.SUGGEST

    def test_companion_model_survives_a_restart_and_still_informs(self, tmp_path: Path) -> None:
        # Jarvis must not forget the person it is meant to know (Vision §5).
        trait = "prefers simplicity"
        first_run = _boot(tmp_path)
        first_run.observe_companion(trait, _ev(0.9))
        first_run.observe_companion(trait, _ev(0.9))

        second_run = _boot(tmp_path)
        belief = second_run.companion.belief_about(trait)
        assert belief is not None
        assert len(belief.evidence) == 2
        # And it still shapes cognition after the restart (Increment 14).
        episode = second_run.think(f"will they be happy if they {trait}?")
        assert episode.working_belief is not None
        assert episode.working_belief.confidence.value > 0.0


class TestPersistentFactory:
    def test_persistent_wires_every_store_under_one_directory(self, tmp_path: Path) -> None:
        # One call gives full cross-restart continuity (Vision §3, §21).
        first = Jarvis.persistent(tmp_path)
        first.think("does my companion prefer simplicity?", evidence=[_ev(0.9)])
        first.observe_companion("prefers simplicity", _ev(0.9))
        action = first.act("tidy the notes", expected="tidy", reversible=True)
        first.record_outcome(action, actual="tidy", met_expectation=True)

        second = Jarvis.persistent(tmp_path)
        assert second.episodes.history()  # episodes survived
        assert second.companion.belief_about("prefers simplicity") is not None
        assert second.belief_about_action("tidy the notes") is not None

    def test_a_fresh_directory_starts_empty(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path / "fresh")
        assert jarvis.episodes.history() == ()
        assert jarvis.companion.beliefs() == ()
