"""DocumentEditor: the seam for proposing a rewrite of a stored document (§38).

Documents are the companion's files, but rewriting their text by hand is not what
chat is for -- "hazle este cambio" should work. Like :class:`Reasoner`, this is a
domain-level Protocol: an editor is a capability provider that *proposes candidate
text*. It is NEVER the decider -- the caller applies the proposal through the
documents capability, and the change note comes from the real diff, not from the
model (Vision §38, D7).

An offline default that proposes nothing is the honest baseline; an LLM-backed
editor drops in behind this Protocol without the core changing. Proposing nothing
is a valid answer (Vision §37): an editor that cannot help returns None rather than
a fabricated rewrite.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DocumentEditor(Protocol):
    """Proposes the full revised text for a document, or None to decline."""

    def propose(self, source_text: str, instruction: str) -> str | None:
        """Return the complete revised document text applying ``instruction``,
        or None when the editor cannot propose a concrete rewrite. Proposals are
        initially deciding nothing; applying them stays in the caller.
        """
        ...