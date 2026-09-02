"""ResearchReport: the structured result of a deep-research run (Vision §38).

A research report is what an :class:`~jarvis.domain.retrieval.research_source
.ResearchSource` returns when Jarvis asks it to look something up in depth. It is
deliberately a *retrieval* artifact, not a conclusion: it gathers cited documents
(which carry provenance) and a plain-language summary of what was found, but it
never asserts, weighs, or decides anything about them (D6, Vision §32, §38).

Turning the gathered material into standing evidence, and deriving confidence from
it, is the cognitive core's job -- exactly as with :class:`RetrievedDocument`.
Each cited document keeps its own provenance (source/url/title), so Jarvis can
tell external research apart from internal knowledge and from what the companion
simply said (Vision §8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from jarvis.domain.value_objects.retrieved_document import RetrievedDocument


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class ResearchReport:
    """One deep-research run: a summary plus the cited documents behind it."""

    query: str
    summary: str
    documents: tuple[RetrievedDocument, ...] = ()
    retrieved_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.query or not self.query.strip():
            raise ValueError("a ResearchReport requires a non-empty query")

    @property
    def sources(self) -> tuple[RetrievedDocument, ...]:
        """The cited documents, kept separate so the core can weigh each one."""
        return self.documents