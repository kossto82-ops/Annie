"""Tests for reasoning with competing explanations (Vision §17)."""

from __future__ import annotations

from collections.abc import Sequence

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _ev(weight: float, *, supports: bool = True) -> Evidence:
    return Evidence(
        content="an observation",
        source=EvidenceSource.DIRECT_OBSERVATION,
        weight=Confidence(weight),
        supports=supports,
    )


_OBS = "my companion went quiet mid-project"


class TestConsider:
    def test_strong_evidence_picks_a_leading_explanation(self) -> None:
        result = Jarvis().consider(
            _OBS,
            {
                "they are busy": [_ev(0.9)],
                "they lost interest": [_ev(0.1)],
            },
        )
        assert result.leading == "they are busy"
        assert result.confidence.value > 0.0
        assert result.evidence_request is None

    def test_no_evidence_leaves_the_question_undecided(self) -> None:
        # Vision §17: do not collapse to one explanation without reason.
        result = Jarvis().consider(
            _OBS,
            {"they are busy": [], "they lost interest": []},
        )
        assert result.leading is None
        assert result.evidence_request is not None
        assert _OBS in result.evidence_request.needed

    def test_a_tie_yields_no_leader(self) -> None:
        result = Jarvis().consider(
            _OBS,
            {"they are busy": [_ev(0.5)], "they lost interest": [_ev(0.5)]},
        )
        assert result.leading is None

    def test_ranking_is_ordered_by_confidence(self) -> None:
        result = Jarvis().consider(
            _OBS,
            {
                "they are busy": [_ev(0.9)],
                "they are thinking it over": [_ev(0.4)],
                "they lost interest": [_ev(0.8, supports=False)],
            },
        )
        confidences = [c for _, c in result.ranking]
        assert confidences == sorted(confidences, reverse=True)
        assert result.ranking[0][0] == "they are busy"

    def test_contradicting_evidence_demotes_an_explanation(self) -> None:
        result = Jarvis().consider(
            _OBS,
            {
                "they are busy": [_ev(0.8)],
                "they lost interest": [_ev(0.8), _ev(0.9, supports=False)],
            },
        )
        assert result.leading == "they are busy"

    def test_deliberation_emits_events(self) -> None:
        from jarvis.domain.events.domain_event import CognitiveEvent
        from jarvis.domain.events.hypothesis_events import HypothesisCreated

        jarvis = Jarvis()
        seen: list[CognitiveEvent] = []
        jarvis.nervous_system.subscribe(CognitiveEvent, seen.append)  # type: ignore[arg-type]
        options: dict[str, Sequence[Evidence]] = {"a": [_ev(0.5)], "b": [_ev(0.5)]}
        jarvis.consider(_OBS, options)
        assert any(isinstance(e, HypothesisCreated) for e in seen)
