"""Round-trip persistence tests for the file-backed stores (Vision §3, §21)."""

from __future__ import annotations

from pathlib import Path

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.evidence_weighting import DEFAULT_WEIGHTING
from jarvis.domain.value_objects.capability import Capability
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.infrastructure.json_belief_store import JsonBeliefStore, deserialise_belief
from jarvis.infrastructure.json_capability_store import JsonCapabilityStore
from jarvis.infrastructure.json_episode_store import JsonEpisodeStore


def _ev(weight: float, *, supports: bool = True) -> Evidence:
    return Evidence(
        content="an observation",
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(weight),
        supports=supports,
    )


def _ev_neutral(weight: float) -> Evidence:
    return Evidence(
        content="a neutral observation",
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(weight),
        is_neutral=True,
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

    def test_neutral_evidence_round_trip_and_ordinary_stays_ordinary(
        self, tmp_path: Path
    ) -> None:
        # Neutral evidence must survive persistence as neutral, and ordinary
        # evidence must never become neutral (inversion of the default).
        path = tmp_path / "beliefs.json"
        neutral = _ev_neutral(0.8)
        ordinary = _ev(0.9)
        belief = Belief(statement="y")
        belief.add_evidence(neutral)
        belief.add_evidence(ordinary)
        JsonBeliefStore(path).save(belief)

        reloaded = JsonBeliefStore(path).get_by_statement("y")
        assert reloaded is not None
        persisted = sorted(reloaded.evidence, key=lambda e: e.content)
        reloaded_neutral = persisted[0]
        reloaded_ordinary = persisted[1]
        assert reloaded_neutral.is_neutral is True
        assert reloaded_ordinary.is_neutral is False
        # Every other reportable evidence field survives unchanged.
        assert reloaded_neutral.content == neutral.content
        assert reloaded_neutral.source is neutral.source
        assert reloaded_neutral.weight == neutral.weight
        assert reloaded_neutral.supports == neutral.supports
        assert reloaded_neutral.context == neutral.context
        assert reloaded_neutral.observed_at == neutral.observed_at
        assert reloaded_neutral.id == neutral.id

    def test_legacy_payload_without_is_neutral_loads_as_ordinary(self) -> None:
        # A serialized belief predating the is_neutral field must load with
        # is_neutral=False (missing key never fabricates neutrality).
        legacy = {
            "statement": "x",
            "id": "bid",
            "formed_at": "2024-01-01T00:00:00+00:00",
            "evidence": [
                {
                    "content": "old observation",
                    "source": EvidenceSource.USER_STATEMENT.value,
                    "weight": 0.7,
                    "supports": True,
                    "context": None,
                    "provenance": None,
                    "observed_at": "2024-01-01T00:00:00+00:00",
                    "id": "eid",
                }
            ],
        }
        reloaded = deserialise_belief(legacy, DEFAULT_WEIGHTING)
        assert reloaded.evidence[0].is_neutral is False

    def test_neutral_evidence_does_not_change_confidence(self, tmp_path: Path) -> None:
        # The forensic failure: a neutral piece reloading as supporting moved
        # confidence from 0.0 to a positive value. Here it must stay 0.0.
        path = tmp_path / "beliefs.json"
        belief = Belief(statement="zc")
        belief.add_evidence(_ev_neutral(0.8))
        assert belief.confidence == Confidence(0.0)

        before = belief.confidence
        JsonBeliefStore(path).save(belief)
        reloaded = JsonBeliefStore(path).get_by_statement("zc")
        assert reloaded is not None
        assert reloaded.confidence == before
        assert reloaded.evidence[0].is_neutral is True

    def test_mixed_evidence_contradiction_survives_persistence(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "beliefs.json"
        belief = Belief(statement="zc")
        belief.add_evidence(_ev(0.9))
        belief.add_evidence(_ev(0.7, supports=False))
        belief.add_evidence(_ev_neutral(0.8))
        before = belief.confidence

        JsonBeliefStore(path).save(belief)
        reloaded = JsonBeliefStore(path).get_by_statement("zc")
        assert reloaded is not None
        assert reloaded.confidence == before
        neutral = [e for e in reloaded.evidence if e.is_neutral]
        assert len(neutral) == 1
        assert neutral[0].is_neutral is True
        # Exactly one supporting and one contradicting piece survive as such.
        assert sum(1 for e in reloaded.evidence if not e.is_neutral and e.supports) == 1
        assert (
            sum(1 for e in reloaded.evidence if not e.is_neutral and not e.supports) == 1
        )


class TestCapabilityStore:
    def test_a_capability_survives_a_reload_with_its_status(self, tmp_path: Path) -> None:
        path = tmp_path / "capabilities.json"
        capability = Capability(
            name="search the web",
            description="search the Internet",
            requirement="an Internet source",
            provenance="met a need",
            status=CapabilityStatus.ACQUIRED,
        )
        JsonCapabilityStore(path).save(capability)

        reloaded = JsonCapabilityStore(path).get_by_name("search the web")
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
        path = tmp_path / "episodes.json"
        store = JsonEpisodeStore(path)
        store.record(self._record("first"))
        store.record(self._record("second"))

        reloaded = JsonEpisodeStore(path)
        history = reloaded.history()
        assert [r.trigger for r in history] == ["first", "second"]
        assert history[0].conclusion_confidence == Confidence(0.42)
        assert history[0].origin is TriggerOrigin.COMPANION
