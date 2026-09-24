"""PassageHit: one passage of a stored document surfaced as relevant to a query.

A passage search mirrors recall at passage granularity (Vision §3, §32, §38):
deterministic sliding-window chunking on the ``DocumentStore`` seam turns a text
document into fixed-overlap chunks (vocabulary-only, D18-faithful), and each
matching chunk is *surfaced* with the byte offsets that locate it inside the
document's stored bytes (document id + byte offsets) -- never a verdict about
the document. Because the whole seam is lexical and deterministic, the offsets
are honest and re-sliceable: ``read_document(name)[start:end]`` reproduces the
passage.

* ``name``     -- the document name the companion chose (auditable provenance).
* ``snippet``  -- the passage text: the exact window that matched (whitespace-
                 collapsed for display), not a whole-document excerpt.
* ``start``/``end`` -- byte offsets of the passage into the document's utf-8
                 bytes; a binary (never chuncked) document carries offsets of a
                 name match --- 0/0 --- so no bytes were ever quoted.
* ``relevance``-- the ``relatedness`` ranking score in ``[0, 1]``. A match
                 strength, NOT a truth or confidence claim.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class PassageHit:
    """A passage inside a stored document judged relevant to a query."""

    name: str
    snippet: str
    start: int
    end: int
    relevance: float