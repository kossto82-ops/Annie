"""RetrievedDocument: one item of external information Jarvis brought back.

This is the value object that carries the answer to "Jarvis went looking on the
Internet" -- it is what an :class:`ExternalSource` returns. It deliberately keeps
the provenance that lets Jarvis tell *external information* apart from internal
knowledge or something the companion simply told it (Vision §8: provenance is
first-class):

* ``content`` -- the retrieved text, ready to reason over.
* ``source``  -- which channel/provided it (e.g. ``"web"``, ``"exa_search"``).
* ``url``     -- where it came from, when known.
* ``title``   -- a short title, when available.
* ``retrieved_at`` -- when it was fetched.
* ``metadata`` -- other available fields (date, author, ...), never secrets.

Bringing a document back is *only retrieval*: it does not assert or weigh anything.
Turning it into standing evidence, and deriving confidence from it, is the cognitive
core's job (mirrors the PerceptionSource / MemoryRetriever boundary, Vision §38).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievedDocument:
    """One piece of external information an :class:`ExternalSource` returned."""

    content: str
    source: str
    url: str | None = None
    title: str | None = None
    retrieved_at: datetime = field(default_factory=_now)
    metadata: dict[str, str] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise ValueError("a RetrievedDocument requires non-empty content")
