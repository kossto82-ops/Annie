"""Reasoning: producing a provisional answer when memory and belief have none.

The domain owns the *contract* for reasoning (:class:`Reasoner`); concrete reasoners
live in :mod:`jarvis.infrastructure`, like perception and retrieval. A reasoner
proposes a candidate answer; it never decides truth (Vision §38, D6).
"""

from __future__ import annotations
