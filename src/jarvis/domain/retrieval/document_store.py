"""DocumentStore: the seam between Jarvis and a store of documents (project files).

A document is any file the companion gives Jarvis -- a log, config, code snippet,
export, or manual -- kept by name so it can be listed and read back on request.
The store is a bounded, file-backed seam at the edge: it only keeps and returns
bytes with provenance (the name the companion chose); it never reasons about the
content (D6) and never writes to Jarvis's beliefs or memory by itself. Binary files
are accepted and kept intact; whether their content is legible to Jarvis is the
surface's honest report (text is readable, images/PDFs are kept but still opaque).
"""

from __future__ import annotations

from typing import Protocol


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

    def write_document(self, name: str, content: bytes) -> None:
        """Store (or replace) the document ``name`` with ``content``.

        Names are flat (no path separators), so a stored file can never escape the
        store's bounded root.
        """
        ...

    def remove_document(self, name: str) -> None:
        """Delete the document ``name``; a no-op when it does not exist."""
        ...