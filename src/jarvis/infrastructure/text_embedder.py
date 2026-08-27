"""TextEmbedder: the swappable seam to an embedding model (Vision §32, §38).

The minimal interface for turning text into vectors -- "texts in, vectors out". A
local ollama model (bge-m3), a hosted embeddings API, or a test fake are all just
`TextEmbedder`s. Like :class:`LanguageModel`, nothing above this line knows which one
it is, so switching the embedding provider is a composition/config change, never a
change to retrieval or the cognitive core.

Embeddings are a *capability* used to rank recalled candidates by meaning; they never
decide anything (Vision §38). Batch in, batch out, in the same order.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TextEmbedder(Protocol):
    """Turns a batch of texts into their embedding vectors, in input order."""

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        """Return one vector per input text, in the same order."""
        ...
