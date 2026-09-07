"""SilentDocumentEditor: the default editor proposes nothing (Vision §37, §38).

Without a live model there is no honest way to rewrite a document from a free-form
instruction. This editor is the offline default that always declines: Jarvis can
still keep, read, and replace documents exactly (``save``), but a chat edit has no
grounded proposal to apply. It mirrors :class:`SilentReasoner` -- producing nothing
is a valid, honest answer.
"""

from __future__ import annotations


class SilentDocumentEditor:
    """An editor that proposes no rewrites (the honest offline default)."""

    def propose(self, source_text: str, instruction: str) -> None:
        """Decline: without a live model there is no grounded rewrite to propose."""
        return None