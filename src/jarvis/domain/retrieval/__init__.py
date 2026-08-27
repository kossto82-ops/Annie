"""Memory retrieval: finding what Jarvis already holds that bears on a query.

The domain owns the *contract* for recall (:class:`MemoryRetriever`); concrete
retrievers live in :mod:`jarvis.infrastructure`, exactly like perception. Retrieval
surfaces candidates carrying provenance; it never decides (Vision §32, §38).
"""

from __future__ import annotations
