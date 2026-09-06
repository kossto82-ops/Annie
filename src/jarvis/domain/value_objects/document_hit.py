"""DocumentHit: one stored document surfaced as relevant to a query.

A document search mirrors recall (Vision §3, §32, §38): the store *surfaces*
candidates carrying provenance and a match strength; it never decides. Because a
document is bytes, the hit carries a ``snippet`` -- a short, honest sample of what
matched -- so the cognitive core and the surface can see *why* the document was
surfaced without the core reaching into the store's raw bytes.

* ``name``     -- the document name the companion chose (auditable provenance).
* ``snippet``  -- a bounded excerpt of the document's text around the match
                 (or the name alone when the file is binary and only the name
                 matched).
* ``relevance``-- the ranking score for this query, in ``[0, 1]``. A match
                 strength, NOT a truth or confidence claim.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentHit:
    """A stored document judged relevant to a query, with a sample of why."""

    name: str
    snippet: str
    relevance: float