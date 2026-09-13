"""Learning continuity: adaptation must survive restarts (P0).

End-to-end proof of the full loop:

    failure -> self-observation -> learned state -> adaptation
      -> persist -> restart -> state restored -> same problem class
      -> behaviour remains adapted

Only justified adaptations persist (the adaptation gates already require a
confident habit, bounded steps and reversibility); the store is the durable
record, and ``reset_learned_state`` always recovers defaults.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.cognitive_knobs import CognitiveKnobs
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.json_learned_state_store import JsonLearnedStateStore
from jarvis.jarvis import Jarvis


def _borderline_evidence() -> list[Evidence]:
    # One full-strength companion statement: confidence exactly 0.5 --
    # grounded at the default threshold, ungrounded once learning raises it.
    return [
        Evidence(
            content="the sky looks blue today",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(1.0),
        )
    ]


def _drive_failures(jarvis: Jarvis, count: int = 4) -> None:
    """Repeated ungrounded conclusions: the systematic failure to learn from."""
    for index in range(count):
        jarvis.think(f"an unfounded question about {index}")


class TestLearningSurvivesRestart:
    def test_adaptation_persists_and_changes_post_restart_behaviour(
        self, tmp_path: Path
    ) -> None:
        first_run = Jarvis.persistent(tmp_path)
        assert first_run.knobs().grounded_confidence == 0.5

        # Baseline: borderline evidence grounds at the default threshold.
        baseline = first_run.think(
            "is the sky blue today?", evidence=_borderline_evidence()
        )
        assert baseline.working_belief is not None
        assert baseline.evidence_request is None

        # Learning: systematic failure adapts the threshold, in memory...
        _drive_failures(first_run)
        adapted = first_run.knobs().grounded_confidence
        assert adapted > 0.5
        learned = first_run.learned_state()
        assert learned is not None
        assert learned.knobs.grounded_confidence == adapted
        assert learned.reason.strip()

        # ...and the adaptation is durable on disk.
        assert (tmp_path / "learned.json").exists()

        # Restart: a brand-new runtime from the same directory.
        second_run = Jarvis.persistent(tmp_path)
        assert second_run.knobs().grounded_confidence == adapted
        assert second_run.learned_state() is not None

        # Repeat: the same problem class now behaves differently -- the
        # borderline case no longer grounds, so Jarvis asks for evidence.
        repeated = second_run.think(
            "is the sky blue today?", evidence=_borderline_evidence()
        )
        assert repeated.working_belief is not None
        assert repeated.evidence_request is not None

    def test_database_backend_persists_learning(
        self, tmp_path: Path
    ) -> None:
        first_run = Jarvis.database(tmp_path)
        _drive_failures(first_run)
        adapted = first_run.knobs().grounded_confidence
        assert adapted > 0.5

        second_run = Jarvis.database(tmp_path)
        assert second_run.knobs().grounded_confidence == adapted

    def test_reset_forgets_and_restores_defaults(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        _drive_failures(jarvis)
        assert jarvis.knobs().grounded_confidence > 0.5

        jarvis.reset_learned_state()
        assert jarvis.knobs() == CognitiveKnobs()
        assert jarvis.learned_state() is None
        assert not (tmp_path / "learned.json").exists()

        # A restart after reset stays at defaults.
        assert Jarvis.persistent(tmp_path).knobs() == CognitiveKnobs()

    def test_operator_tuning_is_not_recorded_as_learning(
        self, tmp_path: Path
    ) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        jarvis.set_knobs(CognitiveKnobs(grounded_confidence=0.8))
        assert jarvis.knobs().grounded_confidence == 0.8
        # Deliberate tuning is session config, not learned state.
        assert jarvis.learned_state() is None

    def test_explicit_knobs_win_over_stored_learning(
        self, tmp_path: Path
    ) -> None:
        first_run = Jarvis.persistent(tmp_path)
        _drive_failures(first_run)
        assert first_run.knobs().grounded_confidence > 0.5

        explicit = CognitiveKnobs(grounded_confidence=0.9)
        override = Jarvis(
            learned_state_store=JsonLearnedStateStore(tmp_path / "learned.json"),
            cognitive_knobs=explicit,
        )
        assert override.knobs() == explicit

    def test_corrupt_learned_state_recovers_to_defaults(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "learned.json").write_text(
            '{"grounded_confidence": 99.0}', encoding="utf-8"
        )
        jarvis = Jarvis.persistent(tmp_path)
        assert jarvis.knobs() == CognitiveKnobs()
        assert jarvis.learned_state() is None
