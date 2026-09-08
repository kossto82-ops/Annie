"""Jarvis continuity on a real database across a simulated restart (Vision §3, §21, D10)."""

from __future__ import annotations

from pathlib import Path

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.interface.command_center import handle


def _ev(weight: float) -> Evidence:
    return Evidence(
        content="an observation",
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(weight),
    )


class TestDatabaseFactory:
    def test_database_lines_up_one_sqlite_file_under_the_directory(
        self, tmp_path: Path
    ) -> None:
        Jarvis.database(tmp_path)
        assert (tmp_path / "jarvis.db").exists()

    def test_a_belief_survives_a_restart_and_keeps_evolving(
        self, tmp_path: Path
    ) -> None:
        question = "does my companion prefer simplicity?"

        first_run = Jarvis.database(tmp_path)
        first_run.think(question, evidence=[_ev(0.9)])

        second_run = Jarvis.database(tmp_path)
        episode = second_run.think(question, evidence=[_ev(0.9)])
        assert episode.working_belief is not None
        assert len(episode.working_belief.evidence) == 2

    def test_episode_history_survives_a_restart(self, tmp_path: Path) -> None:
        first_run = Jarvis.database(tmp_path)
        first_run.think("question one")
        first_run.think("question two")

        second_run = Jarvis.database(tmp_path)
        assert [r.trigger for r in second_run.episodes.history()] == [
            "question one",
            "question two",
        ]

    def test_the_trace_survives_a_restart(self, tmp_path: Path) -> None:
        first_run = Jarvis.database(tmp_path)
        episode = first_run.think("question one")
        original = [type(e) for e in first_run.trace_of(episode)]

        second_run = Jarvis.database(tmp_path)
        assert [type(e) for e in second_run.trace(episode.id)] == original

    def test_self_model_survives_a_restart(self, tmp_path: Path) -> None:
        first_run = Jarvis.database(tmp_path)
        for topic in ("a", "b", "c"):
            first_run.think(f"an unfounded question about {topic}")

        second_run = Jarvis.database(tmp_path)
        self_belief = second_run.observe_self()
        assert self_belief is not None
        assert self_belief.confidence.value > 0.0

    def test_companion_model_survives_a_restart_and_still_informs(
        self, tmp_path: Path
    ) -> None:
        trait = "prefers simplicity"
        first_run = Jarvis.database(tmp_path)
        first_run.observe_companion(trait, _ev(0.9))
        first_run.observe_companion(trait, _ev(0.9))

        second_run = Jarvis.database(tmp_path)
        belief = second_run.companion.belief_about(trait)
        assert belief is not None
        assert len(belief.evidence) == 2
        assert belief.confidence.value > 0.0

    def test_action_learning_survives_a_restart(self, tmp_path: Path) -> None:
        from jarvis.domain.enums.action_stance import ActionStance

        first_run = Jarvis.database(tmp_path)
        for _ in range(3):
            action = first_run.act("tidy the notes", expected="tidy", reversible=True)
            first_run.record_outcome(action, actual="tidy", met_expectation=True)
        belief = first_run.belief_about_action("tidy the notes")
        assert belief is not None
        confidence_before = belief.confidence

        second_run = Jarvis.database(tmp_path)
        pending = second_run.act("tidy the notes", expected="tidy", reversible=True)
        assert second_run.recommend_action(pending).stance is ActionStance.SUGGEST
        reloaded = second_run.belief_about_action("tidy the notes")
        assert reloaded is not None
        assert reloaded.confidence == confidence_before

    def test_acquired_capabilities_survive_restart(self, tmp_path: Path) -> None:
        first_run = Jarvis.database(tmp_path)
        candidate = first_run.need_capability("perceive speech", "to hear me")[0]
        first_run.remember_capability(candidate)
        first_run.acquire_capability("perceive speech")

        second_run = Jarvis.database(tmp_path)
        assert second_run.can_do("perceive speech")
        assert "perceive speech" in second_run.usable_capabilities()

    def test_a_remember_turn_persists_and_documents_stay_under_home(
        self, tmp_path: Path
    ) -> None:
        first = Jarvis.database(tmp_path)
        handle(first, "say", {"text": "Recuerda que prefiero la noche."})
        first.write_document("plan.md", "# follow the plan")
        assert first.episodes.history()

        second = Jarvis.database(tmp_path)
        assert len(second.episodes.history()) == 1
        assert second.beliefs.all_beliefs()
        assert second.list_documents() == ("plan.md",)
        assert second.read_document("plan.md") == b"# follow the plan"

    def test_an_unknown_table_belief_name_is_still_refused(self, tmp_path: Path) -> None:
        import sqlite3

        from jarvis.infrastructure.sqlite_belief_store import SqliteBeliefStore

        try:
            SqliteBeliefStore(sqlite3.connect(tmp_path / "j.db"), table="users")
        except ValueError:
            return
        raise AssertionError("an unknown belief table must be refused")