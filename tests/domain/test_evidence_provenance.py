"""EXTERNAL EVIDENCE v1 domain tests: provenance value object + identity.

Covers the structured provenance container, its derivation from a fetched
document (never inventing dates/backends), and how provenance participates in
``same_observation``: two identical claims from different documents are
independent confirmations, re-perception of the same document collapses, and
provenance-less evidence keeps the historical behaviour unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.evidence_identity import same_observation
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.evidence_provenance import EvidenceProvenance
from jarvis.domain.value_objects.retrieved_document import RetrievedDocument


def _doc(
    content: str = "prices will rise in October",
    url: str | None = "https://example.com/article",
    retrieved_at: datetime | None = None,
    metadata: dict[str, str] | None = None,
) -> RetrievedDocument:
    return RetrievedDocument(
        content=content,
        source="web",
        url=url,
        retrieved_at=retrieved_at or datetime(2026, 9, 1, tzinfo=UTC),
        metadata=metadata or {"provider": "agent_reach", "backend": "jina-reader"},
    )


def _ev(provenance: EvidenceProvenance | None = None) -> Evidence:
    return Evidence(
        content="prices will rise in October",
        source=EvidenceSource.EXTERNAL_SOURCE,
        weight=Confidence(0.5),
        provenance=provenance,
    )


class TestProvenanceFromDocument:
    def test_provider_backend_channel_url_and_retrieved_at_survive(self) -> None:
        prov = EvidenceProvenance.from_document(_doc())
        assert prov.provider == "agent_reach"
        assert prov.backend == "jina-reader"
        assert prov.channel == "web"
        assert prov.url == "https://example.com/article"
        assert prov.retrieved_at == datetime(2026, 9, 1, tzinfo=UTC)

    def test_published_time_is_promoted_only_when_present(self) -> None:
        assert EvidenceProvenance.from_document(_doc()).published_at is None
        prov = EvidenceProvenance.from_document(
            _doc(metadata={"published_at": "2026-08-01T00:00:00+00:00"})
        )
        assert prov.published_at == datetime(2026, 8, 1, tzinfo=UTC)

    def test_published_is_distinct_from_retrieved(self) -> None:
        prov = EvidenceProvenance.from_document(
            _doc(
                metadata={
                    "published_at": "2026-08-01T00:00:00+00:00",
                    "updated_at": "2026-08-30T00:00:00+00:00",
                }
            )
        )
        # The document is not "new" merely because Jarvis fetched it today.
        assert prov.published_at == datetime(2026, 8, 1, tzinfo=UTC)
        assert prov.updated_at == datetime(2026, 8, 30, tzinfo=UTC)
        assert prov.retrieved_at == datetime(2026, 9, 1, tzinfo=UTC)

    def test_malformed_dates_never_fabricate_time(self) -> None:
        prov = EvidenceProvenance.from_document(
            _doc(metadata={"published_at": "not-a-date", "updated_at": "also-bad"})
        )
        assert prov.published_at is None
        assert prov.updated_at is None


class TestEvidenceCarriesProvenance:
    def test_provenance_defaults_to_none(self) -> None:
        assert _ev().provenance is None

    def test_provenance_rides_the_value_object(self) -> None:
        prov = EvidenceProvenance.from_document(_doc())
        piece = _ev(prov)
        assert piece.provenance is not None
        assert piece.provenance.url == "https://example.com/article"


class TestProvenanceIdentity:
    def test_identical_claims_from_different_urls_are_independent(self) -> None:
        piece_a = _ev(
            EvidenceProvenance.from_document(_doc(url="https://a.example.com"))
        )
        piece_b = _ev(
            EvidenceProvenance.from_document(_doc(url="https://b.example.com"))
        )
        # Same text, same day, same channel -- but a different origin story is a
        # different observation (independent confirmation, not a duplicate).
        assert same_observation(piece_a, piece_b) is False

    def test_reperceiving_the_same_document_is_a_duplicate(self) -> None:
        prov = EvidenceProvenance.from_document(_doc())
        assert same_observation(_ev(prov), _ev(prov)) is True

    def test_provenance_less_evidence_keeps_historical_behaviour(self) -> None:
        # No provenance on either side: identical fingerprint and day collapse,
        # exactly as before the provenance field existed.
        assert same_observation(_ev(None), _ev(None)) is True
        different_day = Evidence(
            content="prices will rise in October",
            source=EvidenceSource.EXTERNAL_SOURCE,
            weight=Confidence(0.5),
            observed_at=datetime(2026, 9, 2, tzinfo=UTC),
        )
        assert same_observation(_ev(None), different_day) is False

    def test_contradictory_claims_never_dedup_each_other(self) -> None:
        # Different content ("price is 100" vs "price is 120") is not the same
        # observation in the first place -- both must coexist.
        a = Evidence(
            content="the price is 100.", source=EvidenceSource.EXTERNAL_SOURCE,
            weight=Confidence(0.5),
        )
        b = Evidence(
            content="the price is 120.", source=EvidenceSource.EXTERNAL_SOURCE,
            weight=Confidence(0.5),
        )
        assert same_observation(a, b) is False


def test_retrieved_at_distance_is_recoverable() -> None:
    recent = datetime(2026, 9, 15, tzinfo=UTC)
    old = datetime(2026, 1, 1, tzinfo=UTC)
    prov = EvidenceProvenance.from_document(_doc(retrieved_at=old))
    assert prov.retrieved_at is not None
    delta = recent - prov.retrieved_at
    assert delta == timedelta(days=257)