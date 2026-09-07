"""DocumentMeta: the recorded provenance of one stored document (Vision §26).

A companion asks Jarvis questions that bytes alone cannot answer: "when did I
give you that file?", "is that something you wrote, or something I handed you?".
:class:`DocumentMeta` is the store's honest record of attribution and time -- who
the document belongs to, when it was first stored, when it was last updated, and
the size recorded at that write. It deliberately makes no claim about the content
(visibility into what a file *is* stays the surface's honest report), and it never
pretends to know anything about a file that predates provenance tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from jarvis.domain.enums.document_owner import DocumentOwner


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentMeta:
    """Attribution and timing recorded for a stored document."""

    name: str
    owner: DocumentOwner
    size_bytes: int
    stored_at: datetime
    updated_at: datetime