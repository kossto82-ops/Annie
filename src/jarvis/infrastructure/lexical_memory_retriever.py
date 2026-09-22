"""LexicalMemoryRetriever: a deliberately simple, offline MemoryRetriever.

This is NOT the intelligence -- it is the seam (mirrors KeywordPerception,
Vision §32, §35). It ranks what Jarvis already holds (see
:mod:`jarvis.infrastructure.memory_candidates`) by token overlap with the
query. It knows nothing about meaning: a query and a memory that share no surface
tokens simply do not match (honest silence, Vision §37), rather than a forced guess.

The one deliberate, still-deterministic exception is the *concept* channel: every
durable candidate (beliefs, episodes, traits, goals, semantic patterns) is also
scored against the query's canonical concepts. The concept vocabulary is bilingual
(``CONCEPT_MAP``), so a paraphrase or a Spanish memory for an English question --
different surface words, same idea -- surfaces the memory instead of honest silence.
The query and a memory that share neither words nor concepts still do not match.
Short-term ``CONVERSATION`` turns stay surface-only: reciting a recent turn by
meaning would echo the topic back even when the wording differs.

Its whole purpose is to prove the boundary and make memory *usable* in conversation:
a semantic (embedding-backed) retriever drops in behind the same
:class:`MemoryRetriever` Protocol without the cognitive core changing (Vision §38,
D11). Everything here is deterministic and offline (D8): no randomness, no
network -- when a *decaying weighting policy* is explicitly wired the ranking
also fades stale memories by recency (F2), which remains deterministic because
the policy's clock is injected. The same stores and query always yield the same
ranking.

It only *surfaces candidates* carrying provenance; folding a recalled item into an
episode, and deriving any confidence from it, stays the executive's job.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.repositories.belief_repository import BeliefRepository
from jarvis.domain.repositories.episode_repository import EpisodeRepository
from jarvis.domain.services.abstraction import (
    concept_relevance as concept_relevance,  # re-exported for the semantic tests
)
from jarvis.domain.services.abstraction import relatedness
from jarvis.domain.services.evidence_weighting import DecayingWeightingPolicy
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.infrastructure.memory_candidates import gather_candidates

if TYPE_CHECKING:
    from jarvis.domain.repositories.conversation_repository import (
        ConversationRepository,
    )
    from jarvis.domain.repositories.semantic_memory_repository import (
        SemanticMemoryRepository,
    )

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
        semantic_memories: SemanticMemoryRepository | None = None,
        conversation: ConversationRepository | None = None,
        decay: DecayingWeightingPolicy | None = None,
    ) -> None:
        self._beliefs = beliefs
        self._episodes = episodes
        self._companion = companion
        self._goals = goals
        self._semantic_memories = semantic_memories
        self._conversation = conversation
        # The optional recency bias (F2): when a decaying weighting policy is wired,
        # durable memories rank not only by relevance but by how recent they still
        # are, so a stale, rarely-touched topic ranks below an equally-relevant fresh
        # one -- the same honest forgetting the belief engine applies, on the read
        # side. Reads stay read-only: nothing here mutates the stores.
        self._decay = decay

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[RecalledMemory, ...]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return ()
        scored: list[RecalledMemory] = []
        for match_text, content, kind, provenance, confidence, observed_at in gather_candidates(
            self._beliefs,
            self._episodes,
            self._companion,
            self._goals,
            semantic_memories=self._semantic_memories,
            conversation=self._conversation,
        ):
            if since is not None and (observed_at is None or observed_at < since):
                continue
            if until is not None and (observed_at is None or observed_at > until):
                continue
            if kind is MemoryKind.CONVERSATION:
                # Short-term turns stay surface-only: matching them by meaning would
                # echo the recent topic back as recall even when it was phrased
                # differently. Long-term memory is what paraphrase should reach.
                relevance = _relevance(query_tokens, match_text)
            else:
                # Every durable candidate is reachable by words OR by meaning (the
                # bilingual concept channel), so a paraphrase or a different language
                # surfaces the same memory. Both channels empty = honest silence.
                relevance = relatedness(query, match_text)
                # Recency bias for durable memories (F2): when a decaying policy is
                # wired, an old memory's contribution fades below an equally-relevant
                # fresh one. A topic with no observed_at keeps its full relevance --
                # there is no clock to judge it by, and silence about it would be
                # a guess, not a memory (Vision §37).
                if self._decay is not None and observed_at is not None:
                    relevance *= self._decay.recency(observed_at)
            if relevance <= 0.0:
                continue
            scored.append(
                RecalledMemory(
                    content=content,
                    kind=kind,
                    provenance=provenance,
                    relevance=relevance,
                    source_confidence=confidence,
                    observed_at=observed_at,
                )
            )
        # Most relevant first; ties broken by the more confident memory, then by
        # content so the order is fully deterministic (D8) without leaning on
        # time. At an exact relevance tie the distilled semantic pattern outranks
        # the concrete copies it generalizes over: when a question fully matches
        # the pattern's meaning it has already matched each copy's meaning, so the
        # canonical form answers rather than a redundant residue (relevance always
        # dominates -- concrete sheets rank above a faint pattern, never below).
        scored.sort(
            key=lambda m: (
                -m.relevance,
                -(m.kind is MemoryKind.SEMANTIC),
                -(m.source_confidence or 0.0),
                m.content,
            )
        )
        return tuple(scored[: max(0, limit)])
