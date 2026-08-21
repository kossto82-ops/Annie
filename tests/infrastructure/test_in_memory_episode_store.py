"""Behavioural tests for the in-memory episode store."""

from __future__ import annotations

from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.infrastructure.in_memory_episode_store import InMemoryEpisodeStore


def _record(trigger: str) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id="e-" + trigger,
        trigger=trigger,
        decision="decided",
        working_belief_id="b-" + trigger,
        outcome=EpisodeState.COMPLETED,
        conclusion_confidence=Confidence(0.5),
        conclusion_stability=TemporalStability(0.5),
        origin=TriggerOrigin.COMPANION,
    )


class TestStore:
    def test_history_is_empty_initially(self) -> None:
        assert InMemoryEpisodeStore().history() == ()

    def test_records_are_kept_in_order(self) -> None:
        store = InMemoryEpisodeStore()
        store.record(_record("first"))
        store.record(_record("second"))
        assert [r.trigger for r in store.history()] == ["first", "second"]
