"""TEMPORAL VALIDITY v1: query-relative applicability of evidence (Phase 30).

Everything is evaluated at a fixed ``REFERENCE`` time (2026-09-16T00:00:00Z)
so the suite is fully deterministic (D8): no clocks. The verdicts are
question-relative labels -- never truth, falsity, contradiction, or confidence
(Vision §10) -- and evidence is never mutated, deleted, or re-weighted.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.temporal_applicability import (
    ClaimTemporalAnchor,
    QueryTemporalContext,
    TemporalAnchor,
    TemporalApplicability,
    claim_temporal_anchor,
    temporal_applicability,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.evidence_provenance import EvidenceProvenance

REFERENCE = datetime(2026, 9, 16, tzinfo=UTC)
_DAY = timedelta(days=1)
_WINDOW = timedelta(days=30)


def _provenance(
    *,
    retrieved_at: datetime | None = None,
    published_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> EvidenceProvenance:
    return EvidenceProvenance(
        provider="test",
        backend="test",
        channel="web",
        url="https://example.test/a",
        retrieved_at=retrieved_at,
        published_at=published_at,
        updated_at=updated_at,
    )


def _evidence(
    content: str,
    *,
    observed_at: datetime = REFERENCE,
    supports: bool = True,
    provenance: EvidenceProvenance | None = None,
) -> Evidence:
    return Evidence(
        content=content,
        source=EvidenceSource.EXTERNAL_SOURCE,
        weight=Confidence(0.5),
        supports=supports,
        provenance=provenance,
        observed_at=observed_at,
    )


class TestClaimTemporalAnchor:
    @pytest.mark.parametrize(
        ("content", "expected_date"),
        [
            ("In 2024, Company X had 500 employees", datetime(2024, 1, 1, tzinfo=UTC)),
            ("As of January 2024 the price was $145", datetime(2024, 1, 1, tzinfo=UTC)),
            ("during 2023 revenue fell", datetime(2023, 1, 1, tzinfo=UTC)),
            ("last year we expanded", datetime(2025, 1, 1, tzinfo=UTC)),
            ("by Dec 2024 the office opened", datetime(2024, 12, 1, tzinfo=UTC)),
        ],
    )
    def test_explicit_past_markers(
        self, content: str, expected_date: datetime
    ) -> None:
        assert claim_temporal_anchor(content, REFERENCE) == TemporalAnchor(
            anchor=ClaimTemporalAnchor.HISTORICAL, anchor_date=expected_date
        )

    @pytest.mark.parametrize(
        ("content", "expected_date"),
        [
            ("the price will reach $210 by 2027", datetime(2027, 1, 1, tzinfo=UTC)),
            ("we plan to open next year", datetime(2027, 1, 1, tzinfo=UTC)),
            ("in October 2027 the factory opens", datetime(2027, 10, 1, tzinfo=UTC)),
            ("expenses grow by 2029", datetime(2029, 1, 1, tzinfo=UTC)),
        ],
    )
    def test_explicit_future_markers(
        self, content: str, expected_date: datetime
    ) -> None:
        assert claim_temporal_anchor(content, REFERENCE) == TemporalAnchor(
            anchor=ClaimTemporalAnchor.FUTURE, anchor_date=expected_date
        )

    @pytest.mark.parametrize(
        "content",
        [
            "The Earth has one natural satellite",
            "The price is EUR 499",
            "in 2026 expenses grew",
            "in September 2026 the price rose",
            "2024",
            "the 2024 report is complete",
            "Company X operates 11 sites",
        ],
    )
    def test_no_explicit_anchor(self, content: str) -> None:
        assert claim_temporal_anchor(content, REFERENCE) == TemporalAnchor(
            anchor=ClaimTemporalAnchor.UNANCHORED, anchor_date=None
        )


class TestHistoricalAnchorApplicability:
    def test_past_anchored_claim_is_stale_for_a_current_question(self) -> None:
        evidence = _evidence("In 2024, Company X had 500 employees")
        assert (
            temporal_applicability(
                evidence,
                reference_time=REFERENCE,
                query_context=QueryTemporalContext.CURRENT,
                recency_window=_WINDOW,
            )
            is TemporalApplicability.STALE_FOR_QUERY
        )

    def test_past_anchored_claim_applies_to_a_historical_question(self) -> None:
        evidence = _evidence("In 2024, Company X had 500 employees")
        assert (
            temporal_applicability(
                evidence,
                reference_time=REFERENCE,
                query_context=QueryTemporalContext.HISTORICAL,
            )
            is TemporalApplicability.HISTORICAL
        )

    def test_past_anchored_claim_is_possible_under_unknown_intent(self) -> None:
        evidence = _evidence("In 2024, Company X had 500 employees")
        assert (
            temporal_applicability(
                evidence,
                reference_time=REFERENCE,
                query_context=QueryTemporalContext.UNKNOWN,
            )
            is TemporalApplicability.POSSIBLY_APPLICABLE
        )

    def test_claim_meaning_outranks_fresh_fetch(self) -> None:
        # A freshly fetched page that says something historical is still
        # historical; the fetch time does not make it "current" (freshness !=
        # applicability, and neither is truth).
        evidence = _evidence(
            "In 2024, Company X had 500 employees",
            provenance=_provenance(retrieved_at=REFERENCE - _DAY),
        )
        assert (
            temporal_applicability(
                evidence,
                reference_time=REFERENCE,
                query_context=QueryTemporalContext.CURRENT,
                recency_window=_WINDOW,
            )
            is TemporalApplicability.STALE_FOR_QUERY
        )

    def test_verdict_never_marks_evidence_false_or_unsupported(self) -> None:
        evidence = _evidence("In 2024, Company X had 500 employees", supports=True)
        verdict = temporal_applicability(
            evidence,
            reference_time=REFERENCE,
            query_context=QueryTemporalContext.CURRENT,
        )
        assert verdict is TemporalApplicability.STALE_FOR_QUERY
        # The evidence itself is untouched and still supports the belief.
        assert evidence.content == "In 2024, Company X had 500 employees"
        assert evidence.supports is True
        assert evidence.contradicts is False


class TestFutureAnchorApplicability:
    def test_future_claim_is_future_before_its_moment(self) -> None:
        evidence = _evidence("the price will reach $210 by 2027")
        for context in QueryTemporalContext:
            assert (
                temporal_applicability(
                    evidence,
                    reference_time=REFERENCE,
                    query_context=context,
                )
                is TemporalApplicability.FUTURE
            )

    def test_future_claim_moment_passes_without_mutation(self) -> None:
        content = "the price will reach $210 by 2027"
        evidence = _evidence(content)
        after = datetime(2027, 3, 1, tzinfo=UTC)
        assert (
            temporal_applicability(
                evidence,
                reference_time=after,
                query_context=QueryTemporalContext.CURRENT,
            )
            is TemporalApplicability.POSSIBLY_APPLICABLE
        )
        assert evidence.content == content
        assert evidence.supports is True


class TestRecencyWindow:
    def test_age_alone_never_degrades_without_a_window(self) -> None:
        old = _evidence(
            "the price is EUR 499", observed_at=datetime(2019, 1, 1, tzinfo=UTC)
        )
        assert (
            temporal_applicability(
                old,
                reference_time=REFERENCE,
                query_context=QueryTemporalContext.CURRENT,
            )
            is TemporalApplicability.POSSIBLY_APPLICABLE
        )

    def test_fresh_claim_is_applicable_with_a_window(self) -> None:
        evidence = _evidence(
            "the current price is EUR 510",
            provenance=_provenance(updated_at=REFERENCE - _DAY),
        )
        assert (
            temporal_applicability(
                evidence,
                reference_time=REFERENCE,
                query_context=QueryTemporalContext.CURRENT,
                recency_window=_WINDOW,
            )
            is TemporalApplicability.APPLICABLE
        )

    def test_old_claim_is_stale_for_current_question_with_a_window(self) -> None:
        evidence = _evidence(
            "the price is EUR 499",
            provenance=_provenance(published_at=datetime(2019, 3, 1, tzinfo=UTC)),
        )
        assert (
            temporal_applicability(
                evidence,
                reference_time=REFERENCE,
                query_context=QueryTemporalContext.CURRENT,
                recency_window=_WINDOW,
            )
            is TemporalApplicability.STALE_FOR_QUERY
        )

    def test_boundary_inside_window_is_applicable(self) -> None:
        evidence = _evidence(
            "the price is EUR 510",
            provenance=_provenance(published_at=REFERENCE - _WINDOW),
        )
        assert (
            temporal_applicability(
                evidence,
                reference_time=REFERENCE,
                query_context=QueryTemporalContext.CURRENT,
                recency_window=_WINDOW,
            )
            is TemporalApplicability.APPLICABLE
        )


class TestSourceTimeSelection:
    def test_updated_at_is_chosen_over_older_publication(self) -> None:
        evidence = _evidence(
            "the price is EUR 510",
            provenance=_provenance(
                updated_at=REFERENCE - _DAY,
                published_at=datetime(2024, 1, 1, tzinfo=UTC),
                retrieved_at=REFERENCE - _DAY * 10,
            ),
        )
        assert (
            temporal_applicability(
                evidence,
                reference_time=REFERENCE,
                query_context=QueryTemporalContext.CURRENT,
                recency_window=_WINDOW,
            )
            is TemporalApplicability.APPLICABLE
        )

    def test_published_at_is_used_when_updated_is_absent(self) -> None:
        evidence = _evidence(
            "the price is EUR 510",
            provenance=_provenance(
                published_at=REFERENCE - _DAY,
                retrieved_at=datetime(2019, 1, 1, tzinfo=UTC),
            ),
        )
        assert (
            temporal_applicability(
                evidence,
                reference_time=REFERENCE,
                query_context=QueryTemporalContext.CURRENT,
                recency_window=_WINDOW,
            )
            is TemporalApplicability.APPLICABLE
        )

    def test_retrieved_at_when_no_content_time_is_known(self) -> None:
        evidence = _evidence(
            "the price is EUR 499",
            provenance=_provenance(retrieved_at=datetime(2019, 1, 2, tzinfo=UTC)),
        )
        assert (
            temporal_applicability(
                evidence,
                reference_time=REFERENCE,
                query_context=QueryTemporalContext.CURRENT,
                recency_window=_WINDOW,
            )
            is TemporalApplicability.STALE_FOR_QUERY
        )

    def test_observed_at_fallback_for_untraced_evidence(self) -> None:
        old = _evidence(
            "the price is EUR 499", observed_at=datetime(2019, 1, 1, tzinfo=UTC)
        )
        assert (
            temporal_applicability(
                old,
                reference_time=REFERENCE,
                query_context=QueryTemporalContext.CURRENT,
                recency_window=_WINDOW,
            )
            is TemporalApplicability.STALE_FOR_QUERY
        )


class TestUnanchoredQueryIntents:
    @pytest.mark.parametrize(
        "context",
        [QueryTemporalContext.HISTORICAL, QueryTemporalContext.UNKNOWN],
    )
    def test_unanchored_claim_under_non_current_intent(
        self, context: QueryTemporalContext
    ) -> None:
        evidence = _evidence("The Earth has one natural satellite")
        assert (
            temporal_applicability(
                evidence,
                reference_time=REFERENCE,
                query_context=context,
            )
            is TemporalApplicability.POSSIBLY_APPLICABLE
        )


class TestContradictionCoexistence:
    def test_old_and_new_contradictory_claims_coexist_with_distinct_labels(self) -> None:
        old = _evidence(
            "In 2023 the price was $145",
            provenance=_provenance(published_at=datetime(2023, 5, 1, tzinfo=UTC)),
        )
        new = _evidence(
            "the current price is EUR 510",
            provenance=_provenance(updated_at=REFERENCE - _DAY),
        )
        old_label = temporal_applicability(
            old,
            reference_time=REFERENCE,
            query_context=QueryTemporalContext.CURRENT,
            recency_window=_WINDOW,
        )
        new_label = temporal_applicability(
            new,
            reference_time=REFERENCE,
            query_context=QueryTemporalContext.CURRENT,
            recency_window=_WINDOW,
        )
        assert old_label is TemporalApplicability.STALE_FOR_QUERY
        assert new_label is TemporalApplicability.APPLICABLE
        # Neither is deleted, downgraded in polarity, or marked unsupported.
        assert old.supports is True
        assert new.supports is True
        assert old.content != new.content