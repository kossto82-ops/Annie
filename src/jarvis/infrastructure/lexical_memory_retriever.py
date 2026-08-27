"""LexicalMemoryRetriever: a deliberately simple, offline MemoryRetriever.

This is NOT the intelligence -- it is the seam (mirrors KeywordPerception,
Vision §32, §35). It ranks what Jarvis already holds (see
:mod:`jarvis.infrastructure.memory_candidates`) by plain token overlap with the
query. It knows nothing about meaning: a query and a memory that share no surface
tokens simply do not match (honest silence, Vision §37), rather than a forced guess.

Its whole purpose is to prove the boundary and make memory *usable* in conversation:
a semantic (embedding-backed) retriever drops in behind the same
:class:`MemoryRetriever` Protocol without the cognitive core changing (Vision §38,
D11). Everything here is deterministic and offline (D8): no clocks, no randomness, no
network -- the same stores and query always yield the same ranking.

It only *surfaces candidates* carrying provenance; folding a recalled item into an
episode, and deriving any confidence from it, stays the executive's job.
"""

from __future__ import annotations

import re

from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.repositories.belief_repository import BeliefRepository
from jarvis.domain.repositories.episode_repository import EpisodeRepository
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.infrastructure.memory_candidates import gather_candidates

# Tokens shorter than this carry too little signal to rank on (articles, "me",
# single letters). A short, language-agnostic floor -- not a stopword list.
_MIN_TOKEN_LEN = 2

_WORD = re.compile(r"\w+")


def _tokens(text: str) -> set[str]:
    """The set of scoreable tokens in ``text`` -- lowercased, short ones dropped."""
    return {word for word in _WORD.findall(text.lower()) if len(word) >= _MIN_TOKEN_LEN}


def _relevance(query_tokens: set[str], text: str) -> float:
    """Fraction of the query's tokens the memory shares -- 0.0 when disjoint."""
    if not query_tokens:
        return 0.0
    shared = query_tokens & _tokens(text)
    return len(shared) / len(query_tokens)


class LexicalMemoryRetriever:
    """Ranks Jarvis's stored memories by token overlap with a query."""

    def __init__(
        self,
        beliefs: BeliefRepository,
        episodes: EpisodeRepository,
        companion: CompanionModel,
        goals: BeliefRepository,
    ) -> None:
        self._beliefs = beliefs
        self._episodes = episodes
        self._companion = companion
        self._goals = goals

    def recall(self, query: str, *, limit: int = 5) -> tuple[RecalledMemory, ...]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return ()
        scored: list[RecalledMemory] = []
        for match_text, content, kind, provenance, confidence in gather_candidates(
            self._beliefs, self._episodes, self._companion, self._goals
        ):
            relevance = _relevance(query_tokens, match_text)
            if relevance <= 0.0:
                continue
            scored.append(
                RecalledMemory(
                    content=content,
                    kind=kind,
                    provenance=provenance,
                    relevance=relevance,
                    source_confidence=confidence,
                )
            )
        # Most relevant first; ties broken by the more confident memory, then by
        # content so the order is fully deterministic (D8) without leaning on time.
        scored.sort(key=lambda m: (-m.relevance, -(m.source_confidence or 0.0), m.content))
        return tuple(scored[: max(0, limit)])
