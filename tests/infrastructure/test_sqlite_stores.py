"""Round-trip persistence tests for the SQLite stores (Vision §3, §21, D10)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.value_objects.capability import Capability
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.infrastructure.sqlite_belief_store import SqliteBeliefStore
from jarvis.infrastructure.sqlite_capability_store import SqliteCapabilityStore
from jarvis.infrastructure.sqlite_database import build_sqlite_repositories
from jarvis.infrastructure.sqlite_episode_store import SqliteEpisodeStore
from jarvis.infrastructure.sqlite_refutation_store import SqliteRefutationStore


def _ev(weight: float, *, supports: bool = True) -> Evidence:
    return Evidence(
        content="an observation",
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(weight),
        supports=supports,
    )


class TestBeliefStore:
    def test_unknown_statement_returns_none(self) -> None:
        store = SqliteBeliefStore(sqlite3.connect(":memory:"))
        assert store.get_by_statement("nothing") is None

    def test_a_belief_survives_a_reload_with_its_evidence(self, tmp_path: Path) -> None:
        path = tmp_path / "jarvis.db"
        belief = Belief(statement="the user prefers simplicity")
        belief.add_evidence(_ev(0.9))
        belief.add_evidence(_ev(0.8, supports=False))

        connection = sqlite3.connect(path)
        SqliteBeliefStore(connection).save(belief)
        connection.close()

        reloaded = SqliteBeliefStore(sqlite3.connect(path)).get_by_statement(
            "the user prefers simplicity"
        )
        assert reloaded is not None
        assert reloaded.id == belief.id
        assert len(reloaded.evidence) == 2
        # Confidence and stability are re-derived, not stored (Vision §22).
        assert reloaded.confidence == belief.confidence
        assert reloaded.stability == belief.stability

    def test_contradiction_provenance_survives(self, tmp_path: Path) -> None:
        path = tmp_path / "jarvis.db"
        belief = Belief(statement="x")
        belief.add_evidence(_ev(0.9))
        belief.add_evidence(_ev(0.9, supports=False))

        connection = sqlite3.connect(path)
        SqliteBeliefStore(connection).save(belief)
        connection.close()

        reloaded = SqliteBeliefStore(sqlite3.connect(path)).get_by_statement("x")
        assert reloaded is not None
        assert len(reloaded.explain().contradicting) == 1

    def test_each_belief_table_is_isolated(self) -> None:
        connection = sqlite3.connect(":memory:")
        SqliteBeliefStore(connection, table="companion").save(
            Belief(statement="she likes jazz")
        )
        assert (
            SqliteBeliefStore(connection, table="beliefs").get_by_statement(
                "she likes jazz"
            )
            is None
        )

    def test_an_unknown_table_name_is_refused(self) -> None:
        try:
            SqliteBeliefStore(sqlite3.connect(":memory:"), table="DROP TABLE")
        except ValueError:
            return
        raise AssertionError("an unknown table name must be refused")


class TestCapabilityStore:
    def test_a_capability_survives_a_reload_with_its_status(self, tmp_path: Path) -> None:
        path = tmp_path / "jarvis.db"
        capability = Capability(
            name="search the web",
            description="search the Internet",
            requirement="an Internet source",
            provenance="met a need",
            status=CapabilityStatus.ACQUIRED,
        )

        connection = sqlite3.connect(path)
        SqliteCapabilityStore(connection).save(capability)
        connection.close()

        reloaded = SqliteCapabilityStore(sqlite3.connect(path)).get_by_name(
            "search the web"
        )
        assert reloaded is not None
        assert reloaded.id == capability.id
        assert reloaded.status is CapabilityStatus.ACQUIRED
        assert reloaded.requirement == "an Internet source"


class TestEpisodeStore:
    def _record(self, trigger: str) -> EpisodeRecord:
        return EpisodeRecord(
            episode_id="e-" + trigger,
            trigger=trigger,
            decision="decided",
            working_belief_id="b",
            outcome=EpisodeState.COMPLETED,
            conclusion_confidence=Confidence(0.42),
            conclusion_stability=TemporalStability(0.33),
            origin=TriggerOrigin.COMPANION,
            kind=EpisodeKind.CONCLUSION,
        )

    def test_history_survives_a_reload_in_order(self, tmp_path: Path) -> None:
        path = tmp_path / "jarvis.db"
        connection = sqlite3.connect(path)
        store = SqliteEpisodeStore(connection)
        store.record(self._record("first"))
        store.record(self._record("second"))
        connection.close()

        reloaded = SqliteEpisodeStore(sqlite3.connect(path))
        history = reloaded.history()
        assert [r.trigger for r in history] == ["first", "second"]
        assert history[0].conclusion_confidence == Confidence(0.42)
        assert history[0].origin is TriggerOrigin.COMPANION


class TestRefutationStore:
    def test_refuted_pairs_survive_a_reload(self, tmp_path: Path) -> None:
        path = tmp_path / "jarvis.db"
        connection = sqlite3.connect(path)
        store = SqliteRefutationStore(connection)
        store.add("the sky is green", "it must rain")
        store.add("the sky is green", "it must rain")  # idempotent
        connection.close()

        reloaded = SqliteRefutationStore(sqlite3.connect(path))
        assert reloaded.all() == frozenset({("the sky is green", "it must rain")})


class TestRepositoriesBuilder:
    def test_build_sqlite_repositories_lines_up_one_database(self, tmp_path: Path) -> None:
        repositories = build_sqlite_repositories(tmp_path / "jarvis.db")
        belief = Belief(statement="shared memory")
        belief.add_evidence(_ev(0.8))
        repositories.beliefs.save(belief)
        repositories.capabilities.save(
            Capability(
                name="search the web",
                description="search the Internet",
                requirement="an Internet source",
                provenance="met a need",
                status=CapabilityStatus.ACQUIRED,
            )
        )
        repositories.episodes.record(
            EpisodeRecord(
                episode_id="e-1",
                trigger="t",
                decision="d",
                working_belief_id="b",
                outcome=EpisodeState.COMPLETED,
                conclusion_confidence=Confidence(0.42),
                conclusion_stability=TemporalStability(0.33),
                origin=TriggerOrigin.COMPANION,
                kind=EpisodeKind.CONCLUSION,
            )
        )
        repositories.refutations.add("observation", "belief")
        repositories.close()

        restarted = build_sqlite_repositories(tmp_path / "jarvis.db")
        assert restarted.beliefs.get_by_statement("shared memory") is not None
        assert restarted.capabilities.get_by_name("search the web") is not None
        assert len(restarted.episodes.history()) == 1
        assert restarted.refutations.all() == frozenset({("observation", "belief")})
        restarted.close()