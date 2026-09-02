"""External retrieval: finding what bears on a query, inside memory or beyond.

The domain owns the *contracts*: :class:`MemoryRetriever` for recall of what
Jarvis already holds, :class:`ExternalSource` for read/search access to the
Internet, and :class:`ResearchSource` for in-depth investigation. Concrete
implementations live in :mod:`jarvis.infrastructure`, exactly like perception.
Retrieval surfaces candidates carrying provenance; it never decides (Vision §32,
§38).
"""

from __future__ import annotations

from jarvis.domain.retrieval.external_source import (
    ChannelStatus,
    ExternalSource,
)
from jarvis.domain.retrieval.research_source import ResearchSource

__all__ = ["ChannelStatus", "ExternalSource", "ResearchSource"]
