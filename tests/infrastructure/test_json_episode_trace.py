"""JsonEpisodeTrace records events, replays them across a restart, and tolerates junk."""

from __future__ import annotations

from pathlib import Path

from jarvis.domain.events.episode_events import EpisodeReflected, EpisodeStarted
from jarvis.infrastructure.json_episode_trace import JsonEpisodeTrace
from jarvis.jarvis import Jarvis


def _started(correlation: str) -> EpisodeStarted:
    return EpisodeStarted(
        episode_id=correlation, correlation_id=correlation, trigger="why?"
    )


class TestInMemoryBehaviour:
    def test_groups_events_by_correlation(self, tmp_path: Path) -> None:
        trace = JsonEpisodeTrace(tmp_path / "trace.jsonl")
        trace.handle(_started("one"))
        trace.handle(_started("two"))
        assert len(trace.for_correlation("one")) == 1
        assert len(trace.all_events()) == 2

    def test_ignores_non_cognitive_events(self, tmp_path: Path) -> None:
        trace = JsonEpisodeTrace(tmp_path / "trace.jsonl")
        trace.handle(object())  # type: ignore[arg-type]
        assert trace.all_events() == ()


class TestPersistence:
    def test_events_survive_a_new_instance_on_the_same_file(self, tmp_path: Path) -> None:
        path = tmp_path / "trace.jsonl"
        first = JsonEpisodeTrace(path)
        first.handle(_started("one"))
        first.handle(
            EpisodeReflected(
                episode_id="one", correlation_id="one", note="grounded", contested=False
            )
        )

        reloaded = JsonEpisodeTrace(path)
        kinds = [type(e) for e in reloaded.for_correlation("one")]
        assert kinds == [EpisodeStarted, EpisodeReflected]

    def test_a_torn_final_line_is_skipped_on_load(self, tmp_path: Path) -> None:
        path = tmp_path / "trace.jsonl"
        trace = JsonEpisodeTrace(path)
        trace.handle(_started("one"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"type": "EpisodeStarted", "event_id": ')  # truncated write

        reloaded = JsonEpisodeTrace(path)
        assert len(reloaded.all_events()) == 1  # only the intact line survives


class TestDurableTraceThroughJarvis:
    def test_a_persistent_jarvis_keeps_its_trace_across_a_restart(
        self, tmp_path: Path
    ) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        episode = jarvis.think("is the plan solid?")
        original = [type(e) for e in jarvis.trace_of(episode)]
        assert EpisodeStarted in original

        revived = Jarvis.persistent(tmp_path)
        restored = [type(e) for e in revived.trace(episode.id)]
        assert restored == original
