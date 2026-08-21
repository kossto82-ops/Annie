"""Jarvis continuity across a simulated restart (Vision §3, §21)."""

from __future__ import annotations

from pathlib import Path

from jarvis import Jarvis
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
