"""Round-trip persistence tests for the file-backed stores (Vision §3, §21)."""

from __future__ import annotations

from pathlib import Path

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.infrastructure.json_belief_store import JsonBeliefStore
from jarvis.infrastructure.json_episode_store import JsonEpisodeStore


def _ev(weight: float, *, supports: bool = True) -> Evidence:
    return Evidence(
        content="an observation",
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(weight),
        supports=supports,
    )


class TestBeliefStore:
    def test_unknown_statement_returns_none(self, tmp_path: Path) -> None:
        store = JsonBeliefStore(tmp_path / "beliefs.json")
        assert store.get_by_statement("nothing") is None

    def test_a_belief_survives_a_reload_with_its_evidence(self, tmp_path: Path) -> None:
        path = tmp_path / "beliefs.json"
        belief = Belief(statement="the user prefers simplicity")
        belief.add_evidence(_ev(0.9))
        belief.add_evidence(_ev(0.8, supports=False))
        JsonBeliefStore(path).save(belief)

        reloaded = JsonBeliefStore(path).get_by_statement("the user prefers simplicity")
        assert reloaded is not None
        assert reloaded.id == belief.id
        assert len(reloaded.evidence) == 2
        # Confidence and stability are re-derived, not stored (Vision §22).
        assert reloaded.confidence == belief.confidence
        assert reloaded.stability == belief.stability

    def test_contradiction_provenance_survives(self, tmp_path: Path) -> None:
        path = tmp_path / "beliefs.json"
        belief = Belief(statement="x")
        belief.add_evidence(_ev(0.9))
        belief.add_evidence(_ev(0.9, supports=False))
        JsonBeliefStore(path).save(belief)
        reloaded = JsonBeliefStore(path).get_by_statement("x")
        assert reloaded is not None
        assert len(reloaded.explain().contradicting) == 1


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
        )

    def test_history_survives_a_reload_in_order(self, tmp_path: Path) -> None:
        path = tmp_path / "episodes.json"
        store = JsonEpisodeStore(path)
        store.record(self._record("first"))
        store.record(self._record("second"))

        reloaded = JsonEpisodeStore(path)
        history = reloaded.history()
        assert [r.trigger for r in history] == ["first", "second"]
        assert history[0].conclusion_confidence == Confidence(0.42)
        assert history[0].origin is TriggerOrigin.COMPANION
