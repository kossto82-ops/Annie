"""TEMPORAL VALIDITY v1 facade: Jarvis.temporal_applicability seam.

The public seam delegates to the pure domain function; reference time stays
injectable so tests remain deterministic (D8). These prove the seam exists and
matches the domain verdicts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.temporal_applicability import (
    QueryTemporalContext,
    TemporalApplicability,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence

REFERENCE = datetime(2026, 9, 16, tzinfo=UTC)


def _evidence(content: str) -> Evidence:
    return Evidence(
        content=content,
        source=EvidenceSource.EXTERNAL_SOURCE,
        weight=Confidence(0.5),
    )


class TestTemporalApplicabilityFacade:
    def test_injected_reference_time_keeps_verdicts_deterministic(
        self, tmp_path: Path
    ) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        evidence = _evidence("In 2024, Company X had 500 employees")
        verdict = jarvis.temporal_applicability(
            evidence,
            QueryTemporalContext.CURRENT,
            reference_time=REFERENCE,
            recency_window=timedelta(days=30),
        )
        assert verdict is TemporalApplicability.STALE_FOR_QUERY

    def test_historical_question_still_applies(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        evidence = _evidence("In 2024, Company X had 500 employees")
        verdict = jarvis.temporal_applicability(
            evidence,
            QueryTemporalContext.HISTORICAL,
            reference_time=REFERENCE,
        )
        assert verdict is TemporalApplicability.HISTORICAL

    def test_default_reference_time_is_now(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        evidence = _evidence("The Earth has one natural satellite")
        verdict = jarvis.temporal_applicability(
            evidence, QueryTemporalContext.UNKNOWN
        )
        assert verdict is TemporalApplicability.POSSIBLY_APPLICABLE