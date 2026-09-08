"""SqliteEpisodeTrace records events, replays them across a restart, and tolerates junk."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from jarvis.domain.events.episode_events import EpisodeReflected, EpisodeStarted
from jarvis.infrastructure.sqlite_episode_trace import SqliteEpisodeTrace
from jarvis.jarvis import Jarvis


def _started(correlation: str) -> EpisodeStarted:
    return EpisodeStarted(
        episode_id=correlation, correlation_id=correlation, trigger="why?"
    )


class TestInMemoryBehaviour:
    def test_groups_events_by_correlation(self) -> None:
        trace = SqliteEpisodeTrace(sqlite3.connect(":memory:"))
        trace.handle(_started("one"))
        trace.handle(_started("two"))
        assert len(trace.for_correlation("one")) == 1
        assert len(trace.all_events()) == 2

    def test_ignores_non_cognitive_events(self) -> None:
        trace = SqliteEpisodeTrace(sqlite3.connect(":memory:"))
        trace.handle(object())  # type: ignore[arg-type]
        assert trace.all_events() == ()


class TestPersistence:
    def test_events_survive_a_new_instance_on_the_same_database(self) -> None:
        connection = sqlite3.connect(":memory:")
        first = SqliteEpisodeTrace(connection)
        first.handle(_started("one"))
        first.handle(
            EpisodeReflected(
                episode_id="one", correlation_id="one", note="grounded", contested=False
            )
        )

        reloaded = SqliteEpisodeTrace(connection)
        kinds = [type(e) for e in reloaded.for_correlation("one")]
        assert kinds == [EpisodeStarted, EpisodeReflected]

    def test_events_survive_across_a_connection_reopen(self, tmp_path: Path) -> None:
        path = tmp_path / "jarvis.db"
        first = SqliteEpisodeTrace(sqlite3.connect(path))
        first.handle(_started("one"))

        reopened = SqliteEpisodeTrace(sqlite3.connect(path))
        assert len(reopened.for_correlation("one")) == 1

    def test_a_corrupt_row_is_skipped_on_load(self) -> None:
        connection = sqlite3.connect(":memory:")
        trace = SqliteEpisodeTrace(connection)
        trace.handle(_started("one"))
        connection.execute(
            "INSERT INTO trace_events (correlation_id, payload) VALUES (?, ?)",
            ("one", "{not json"),  # a torn row, like the JSONL twin's interrupted write
        )
        connection.commit()

        reloaded = SqliteEpisodeTrace(connection)
        assert len(reloaded.all_events()) == 1  # only the intact row survives


class TestDurableTraceThroughJarvis:
    def test_a_database_jarvis_keeps_its_trace_across_a_restart(
        self, tmp_path: Path
    ) -> None:
        jarvis = Jarvis.database(tmp_path)
        episode = jarvis.think("is the plan solid?")
        original = [type(e) for e in jarvis.trace_of(episode)]
        assert EpisodeStarted in original

        revived = Jarvis.database(tmp_path)
        restored = [type(e) for e in revived.trace(episode.id)]
        assert restored == original