"""DocumentStore: the seam between Jarvis and a store of documents (project files).

A document is any file the companion gives Jarvis -- a log, config, code snippet,
export, or manual -- kept by a bounded, relative name (``runbook.md`` or
``docs/api.md``) so it can be listed and read back on request. The store is a
bounded, file-backed seam at the edge: it only keeps and returns bytes with
provenance (the name the companion chose); it never reasons about the content
(D6) and never writes to Jarvis's beliefs or memory by itself. Binary files are
accepted and kept intact; whether their content is legible to Jarvis is the
surface's honest report (text is readable, images/PDFs are kept but still opaque).
"""

from __future__ import annotations

from typing import Protocol

from jarvis.domain.enums.document_owner import DocumentOwner
from jarvis.domain.value_objects.document_hit import DocumentHit
from jarvis.domain.value_objects.document_meta import DocumentMeta


class DocumentStore(Protocol):
    """Gives Jarvis read and write access to the files the companion shares."""

    def list_documents(self) -> tuple[str, ...]:
        """Every document name Jarvis holds, sorted.

        An empty tuple is an honest "no documents yet", never an error.
        """
        ...

    def read_document(self, name: str) -> bytes:
        """The raw bytes of the document named ``name``.

        Raises a clear error when no such document exists. Bytes keep every file
        intact regardless of type; decoding is the caller's (the core reads text,
        the surface reports binary honestly).
        """
        ...

    def write_document(
        self,
        name: str,
        content: bytes,
        *,
        owner: DocumentOwner = DocumentOwner.COMPANION,
    ) -> None:
        """Store (or replace) the document ``name`` with ``content``.

        Names are bounded, relative, forward-slash paths -- never absolute and
        never ``.``/``..`` -- so a stored file can never escape the store's
        bounded root. ``owner`` attributes the document (Vision §26): who gave
        Jarvis this artifact.
        """
        ...

    def remove_document(self, name: str) -> None:
        """Delete the document ``name``; a no-op when it does not exist."""
        ...

    def document_meta(self, name: str) -> DocumentMeta | None:
        """The recorded provenance of ``name``, or None when none was recorded.

        Attribution and timing (Vision §26) -- who owns the document and when it
        was stored/updated. Honest ``None`` means the store keeps no provenance
        for that file; it is never a guess.
        """
        ...

    def search_documents(self, query: str, *, limit: int = 5) -> tuple[DocumentHit, ...]:
        """The documents whose name or text matches ``query``, most relevant first.

        Surfaces candidates only -- each hit carries a snippet and a match strength,
        never a verdict (mirrors recall, Vision §3, §32). Binary documents can be
        found by the tokens in their name; what they *are* stays the surface's honest
        report. An empty tuple is an honest "no matching documents".
        """
        ...