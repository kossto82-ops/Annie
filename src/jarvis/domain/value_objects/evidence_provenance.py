"""EvidenceProvenance: where externally gathered evidence really came from.

A claim perceived from a web document must retain where it came from and when
it was obtained (Vision §8; the external-evidence gate's central rule), so the
relationship stays recoverable:

    Evidence -> EvidenceProvenance -> URL / provider / retrieved_at

This is *temporal and locational provenance*, not reliability: a recent page is
not truer and an old page is not false (freshness ≠ confidence). ``published_at``
and ``updated_at`` are carried only when the originating source actually provides
them -- never invented. If the source is silent, they stay ``None`` and a later
consumer can still distinguish old vs recent *retrieval* through ``retrieved_at``
(or a claim's own ``observed_at``).

Only the optional, known-sized subset of document metadata is promoted here. For
a :class:`RetrievedDocument`, the builder reads the standard keys the edge
providers already stamp (``provider``, ``backend``) plus ``published_at`` /
``updated_at`` when present; anything else stays in the document's own metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from jarvis.domain.value_objects.retrieved_document import RetrievedDocument


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _stamp(label: str | None) -> datetime | None:
    """Parse a metadata timestamp; malformed/absent dates never fabricate time."""
    if not label:
        return None
    try:
        parsed = datetime.fromisoformat(label.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceProvenance:
    """Structured origin of one piece of externally perceived evidence."""

    provider: str | None = None
    backend: str | None = None
    channel: str | None = None
    url: str | None = None
    retrieved_at: datetime | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_document(cls, document: RetrievedDocument) -> EvidenceProvenance:
        """Derive provenance from a fetched document, using only known metadata.

        ``provider``/``backend`` are read from the document's stamped metadata
        (e.g. ``agent_reach`` / ``jina-reader``); ``published_at`` and
        ``updated_at`` are promoted only when present and parseable. Nothing is
        invented: a value the source did not provide stays ``None``.
        """
        metadata = document.metadata
        return EvidenceProvenance(
            provider=_clean(metadata.get("provider")),
            backend=_clean(metadata.get("backend")),
            channel=_clean(document.source or None),
            url=_clean(document.url or None),
            retrieved_at=document.retrieved_at,
            published_at=_stamp(metadata.get("published_at") or metadata.get("date")),
            updated_at=_stamp(metadata.get("updated_at")),
        )