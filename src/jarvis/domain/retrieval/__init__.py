"""External retrieval: finding what bears on a query, inside memory or beyond.

The domain owns the *contracts*: :class:`MemoryRetriever` for recall of what
Jarvis already holds, :class:`ExternalSource` for read/search access to the
Internet, :class:`ResearchSource` for in-depth investigation, and
:class:`MailBox` for the email capability at the edge. Concrete implementations
live in :mod:`jarvis.infrastructure`, exactly like perception.
Retrieval surfaces candidates carrying provenance; it never decides (Vision §32,
§38).
"""

from __future__ import annotations

from jarvis.domain.retrieval.external_source import (
    ChannelStatus,
    ExternalSource,
)
from jarvis.domain.retrieval.mail_source import MailBox
from jarvis.domain.retrieval.research_source import ResearchSource
from jarvis.domain.retrieval.task_agent_source import TaskAgent

__all__ = [
    "ChannelStatus",
    "ExternalSource",
    "MailBox",
    "ResearchSource",
    "TaskAgent",
]
