"""EpisodeRecord: an immutable memory of one completed cognitive episode.

This is *memory*, not *belief* (Vision §22). It records what happened -- what
triggered the episode, what was decided, which belief it reasoned toward, and
when -- without asserting any of it is true. Beliefs carry the epistemology; this
carries the history Jarvis can later look back on (Vision §21) and eventually
reason about itself with (Vision §6, §31: "what mistakes do I repeat?").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from jarvis.domain.enums.episode_state import EpisodeState


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class EpisodeRecord:
    """A snapshot of a completed episode, kept in episodic memory."""

    episode_id: str
    trigger: str
    decision: str
    working_belief_id: str
    outcome: EpisodeState
    recorded_at: datetime = field(default_factory=_now)
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
