"""NotesStore: the seam between Jarvis and a store of notes (Odysseus #8).

Notes are a *material*, low-risk, reversible capability Jarvis may gain (Vision
§34, and the revised D1: delegating actions is allowed, delegating cognition is
not). Like ``ExternalSource``/``MailBox``/``TaskAgent``, this is a domain Protocol
behind which a concrete store adapter lives in ``infrastructure`` (D7): the
storage back-end and its transport stay at the edge, the transport is injectable,
and tests stay deterministic and offline (D8).

A ``NotesStore`` *stores* and *returns* plain note content with provenance. It
never reasons about the notes (D6) and never writes to Jarvis's beliefs or memory
on its own. Creating/updating/deleting are reversible material actions the caller
must have gated; reading is retrieval that becomes candidate evidence.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jarvis.domain.value_objects.note import Note


@runtime_checkable
class NotesStore(Protocol):
    """Gives Jarvis read and write access to a store of notes on request."""

    def list_notes(self, *, limit: int = 100) -> tuple[Note, ...]:
        """Return up to ``limit`` notes, newest first, as retrieval artifacts.

        An empty tuple is an honest "no notes here", not an error. Each note
        carries provenance; Jarvis weighs them as candidate evidence (D6).
        """
        ...

    def get_note(self, note_id: str) -> Note:
        """Return one note by its id, or raise when it cannot be retrieved.

        Raises only on a real failure of the underlying store; an unknown id is a
        clear error, never a fabricated note.
        """
        ...

    def create_note(
        self, *, title: str, body: str = "", tags: tuple[str, ...] = ()
    ) -> Note:
        """Create and return a note; a reversible material action on request."""
        ...

    def update_note(
        self,
        note_id: str,
        *,
        title: str,
        body: str,
        tags: tuple[str, ...],
    ) -> Note:
        """Update a note's fields and return the refreshed note."""
        ...

    def delete_note(self, note_id: str) -> None:
        """Delete a note by its id; a reversible material action on request."""
        ...

    def search_notes(self, query: str, *, limit: int = 10) -> tuple[Note, ...]:
        """Return up to ``limit`` notes matching ``query``, or () when none match.

        An empty tuple is an honest "nothing matched", not an error.
        """
        ...
