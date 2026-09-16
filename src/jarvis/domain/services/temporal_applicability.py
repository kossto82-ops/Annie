"""Query-relative temporal applicability of evidence (TEMPORAL VALIDITY v1).

This is the temporal gate's minimal semantics seam: a *pure, deterministic,
query-relative* answer to "is this evidence temporally applicable to the
question being asked?", evaluated at an explicit ``reference_time``.

The seam exists to keep three dimensions honest and separate (Vision §10):

* **Freshness** -- how current the evidence is *for a question* (this module).
* **Truth**     -- whether the claim is true (this module NEVER answers that).
* **Confidence**-- how strongly supported it is (``derived`` elsewhere).

Therefore the verdict vocabulary is about *question-applicability only*:
``APPLICABLE``, ``POSSIBLY_APPLICABLE``, ``STALE_FOR_QUERY``, ``HISTORICAL``,
``FUTURE``, ``UNKNOWN``. There is deliberately **no "false" member**: staleness
is the relationship between the evidence's temporal meaning and the current
question; it is never a truth, falsity, contradiction, or deletion verdict
(Phase 3/4/11).

The evaluation rests on what the architecture genuinely knows:

1. **Explicit in-content temporal anchors** (``claim_temporal_anchor``): a
   claim that says "in 2024", "as of January 2024", "last year" is *about* that
   past time; "by 2027", "next year" is about a future time. Detection is
   deliberately conservative -- only explicit year/month-year markers and
   next/last year, *never* an invented date and never bare numbers (Phase 21).
2. **Temporal origin** (``_source_time``): the newest *content-bearing* time
   known for the evidence, chosen as ``updated_at`` > ``published_at`` >
   ``retrieved_at`` > ``observed_at``. This is a read-only *selection* for
   evaluation; nothing is overwritten (Phase 5/6).
3. **The question's temporal intent** (``QueryTemporalContext``): CURRENT,
   HISTORICAL, or UNKNOWN -- supplied by the caller, because capability-level
   currentness cues stop at the request trace today and do not reach the
   evidence layer (documented seam, Phase 19).

Age alone never degrades a claim (Phase 3): an *explicit* ``recency_window`` is
an opt-in caller choice (default ``None``), so there is no automatic,
hard-coded expiration (Phase 5/27). And nothing here mutates, re-weights, or
deletes evidence; conflicting old and new claims simply coexist and may carry
different applicability labels (Phase 11/16).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

from jarvis.domain.value_objects.evidence import Evidence

_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_MONTH_RE = f"({'|'.join(m[:3] for m in _MONTHS)}|{'|'.join(_MONTHS)})"

# An explicit historical/future month-year claim: "in January 2024", "by Dec 2027".
_MONTH_YEAR = re.compile(
    rf"\b(in|as of|during|for|by) {_MONTH_RE} (\d{{4}})\b"
)
# An explicit historical/future year claim: "in 2024", "during 2023", "by 2027".
_YEAR_ONLY = re.compile(r"\b(in|as of|during|for|by) (\d{4})\b")
_LAST_YEAR = re.compile(r"\blast year\b")
_NEXT_YEAR = re.compile(r"\bnext year\b")

_MONTH_TO_INDEX = {
    form: i + 1 for i, m in enumerate(_MONTHS) for form in (m, m[:3])
}


class QueryTemporalContext(Enum):
    """The temporal *intent* of the question being asked of the evidence."""

    CURRENT = "current"
    HISTORICAL = "historical"
    UNKNOWN = "unknown"


class ClaimTemporalAnchor(Enum):
    """Whether and how the claim's content pins itself to a time."""

    HISTORICAL = "historical"
    FUTURE = "future"
    UNANCHORED = "unanchored"


@dataclass(frozen=True, slots=True, kw_only=True)
class TemporalAnchor:
    """A claim's explicit temporal anchor, when its content provides one.

    ``anchor_date`` is the earliest explicit time the claim names (a year-only
    claim is taken as January 1st of that year); it is used only to decide
    whether a future anchor's moment has already passed. It is read from the
    claim's own words -- never invented (Phase 21).
    """

    anchor: ClaimTemporalAnchor
    anchor_date: datetime | None = None


class TemporalApplicability(Enum):
    """How applicable evidence is to a question at a reference time.

    Question-relative only. ``STALE_FOR_QUERY`` means the claim does not answer
    *this* question (it is too old for a CURRENT question, or it is explicitly
    past-anchored while the question is CURRENT); it is NOT "false",
    "unsupported", or "deleted". ``POSSIBLY_APPLICABLE`` is an honest "cannot
    decide from available temporal information, and nothing rules it out".
    ``UNKNOWN`` is reserved for evidence with no temporal origin at all
    (unreachable today because ``Evidence`` always carries ``observed_at``).
    """

    APPLICABLE = "applicable"
    POSSIBLY_APPLICABLE = "possibly_applicable"
    STALE_FOR_QUERY = "stale_for_query"
    HISTORICAL = "historical"
    FUTURE = "future"
    UNKNOWN = "unknown"


def claim_temporal_anchor(content: str, reference_time: datetime) -> TemporalAnchor:
    """Extract the explicit temporal anchor a claim's content states.

    Deterministic and conservative: only explicit year, month-year, and
    next/last year markers count. A claim naming the reference year itself (e.g.
    "in 2026" at refere-time 2026) stays ``UNANCHORED`` -- the year alone does
    not say past or future. Bare numbers ("$145 in 2023" without "in") never
    anchor a claim.
    """
    text = " ".join(content.lower().split())
    if _LAST_YEAR.search(text) is not None:
        return TemporalAnchor(
            anchor=ClaimTemporalAnchor.HISTORICAL,
            anchor_date=datetime(reference_time.year - 1, 1, 1, tzinfo=UTC),
        )
    if _NEXT_YEAR.search(text) is not None:
        return TemporalAnchor(
            anchor=ClaimTemporalAnchor.FUTURE,
            anchor_date=datetime(reference_time.year + 1, 1, 1, tzinfo=UTC),
        )
    month_match = _MONTH_YEAR.search(text)
    if month_match is not None:
        month = _MONTH_TO_INDEX[month_match.group(2)]
        year = int(month_match.group(3))
        anchor_date = datetime(year, month, 1, tzinfo=UTC)
        # Compare at month granularity: a claim naming the reference's own year
        # and month ("in September 2026") does not say past or future.
        if (year, month) < (reference_time.year, reference_time.month):
            return TemporalAnchor(
                anchor=ClaimTemporalAnchor.HISTORICAL, anchor_date=anchor_date
            )
        if (year, month) > (reference_time.year, reference_time.month):
            return TemporalAnchor(
                anchor=ClaimTemporalAnchor.FUTURE, anchor_date=anchor_date
            )
        return TemporalAnchor(anchor=ClaimTemporalAnchor.UNANCHORED)
    year_match = _YEAR_ONLY.search(text)
    if year_match is not None:
        year = int(year_match.group(2))
        anchor_date = datetime(year, 1, 1, tzinfo=UTC)
        if year < reference_time.year:
            return TemporalAnchor(
                anchor=ClaimTemporalAnchor.HISTORICAL, anchor_date=anchor_date
            )
        if year > reference_time.year:
            return TemporalAnchor(
                anchor=ClaimTemporalAnchor.FUTURE, anchor_date=anchor_date
            )
        return TemporalAnchor(anchor=ClaimTemporalAnchor.UNANCHORED)
    return TemporalAnchor(anchor=ClaimTemporalAnchor.UNANCHORED)


def _source_time(evidence: Evidence) -> datetime | None:
    """The newest *content-bearing* time known for this evidence.

    Prefers the source's own content markers (``updated_at`` -- the content may
    have been revised; ``published_at`` -- when it first appeared) over the
    fetch time (``retrieved_at`` -- when Jarvis fetched a page, which says
    nothing about how old its content is) and finally ``observed_at`` (when
    Jarvis weighed it). Read-only selection: nothing is overwritten.
    """
    provenance = evidence.provenance
    if provenance is not None:
        if provenance.updated_at is not None:
            return provenance.updated_at
        if provenance.published_at is not None:
            return provenance.published_at
        if provenance.retrieved_at is not None:
            return provenance.retrieved_at
    return evidence.observed_at


def temporal_applicability(
    evidence: Evidence,
    *,
    reference_time: datetime,
    query_context: QueryTemporalContext,
    recency_window: timedelta | None = None,
) -> TemporalApplicability:
    """Judge how temporally applicable ``evidence`` is to a question.

    ``reference_time`` is the explicit "now" (deterministic evaluation).
    ``query_context`` is the question's temporal intent. ``recency_window`` is
    an opt-in caller policy: when ``None`` (default) age alone never degrades a
    CURRENT answer; when supplied, an unanchored claim whose newest content time
    falls outside the window is ``STALE_FOR_QUERY`` -- still true, still
    present, just not an answer to *this* "what's current" question.

    Never mutates evidence, never re-derives confidence, never deletes or flips
    anything (Phase 3/4/11).
    """
    anchor = claim_temporal_anchor(evidence.content, reference_time)
    verdict: TemporalApplicability
    if anchor.anchor is ClaimTemporalAnchor.HISTORICAL:
        if query_context is QueryTemporalContext.CURRENT:
            verdict = TemporalApplicability.STALE_FOR_QUERY
        elif query_context is QueryTemporalContext.HISTORICAL:
            verdict = TemporalApplicability.HISTORICAL
        else:
            verdict = TemporalApplicability.POSSIBLY_APPLICABLE
        return verdict
    if anchor.anchor is ClaimTemporalAnchor.FUTURE:
        if anchor.anchor_date is not None and reference_time >= anchor.anchor_date:
            # The claim's moment has passed; its meaning is unchanged, but its
            # application window is over. Still not false.
            return TemporalApplicability.POSSIBLY_APPLICABLE
        return TemporalApplicability.FUTURE
    if query_context is QueryTemporalContext.CURRENT:
        if recency_window is None:
            return TemporalApplicability.POSSIBLY_APPLICABLE
        source_time = _source_time(evidence)
        if source_time is None:
            return TemporalApplicability.UNKNOWN
        if reference_time - source_time <= recency_window:
            return TemporalApplicability.APPLICABLE
        return TemporalApplicability.STALE_FOR_QUERY
    return TemporalApplicability.POSSIBLY_APPLICABLE