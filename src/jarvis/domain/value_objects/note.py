"""Note: a note stored or retrieved through the notes capability (Odysseus #8).

A note is a *material*, low-risk, reversible artifact -- text the user asked Jarvis
to keep. It is deliberately plain content with provenance and a stable identity
(``id``), never a conclusion. A retrieved note becomes candidate evidence the core
weighs (D6); creating/updating/deleting are reversible material actions the surface
requests, not decisions Jarvis makes on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class Note:
    """One stored note: identity, title, body, tags and timestamps, unvetted."""

    id: str
    title: str
    body: str
    tags: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.title and not self.body:
            raise ValueError("a Note requires a title and/or a body")

    @property
    def provenance(self) -> str:
        """A plain description of the note's origin, for the episode trace."""
        label = self.title or "(untitled)"
        return f"note {self.id} '{label}'"
