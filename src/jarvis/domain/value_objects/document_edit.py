"""DocumentEdit: a proposed rewrite of a stored document, plus its honest note.

Editing a document through an editor model is the *proposal* side of Vision §38:
the model may suggest the new text, but it never decides to write anything. The
caller (Jarvis) applies the proposal deterministically through the documents
capability and derives the ``note`` from the actual before/after diff, so the
companion is told what really changed, never what the model says changed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DocumentEdit:
    """A decided rewrite: the complete new text and a derived change note.

    ``content`` is the full revised document (what will be stored). ``note`` is a
    short, deterministic framing of the diff (e.g. "3 line(s) removed, 2 added"),
    computed by the decider from the two texts -- never asserted by the model.
    """

    content: str
    note: str