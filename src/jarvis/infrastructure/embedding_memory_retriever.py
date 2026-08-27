"""EmbeddingMemoryRetriever: recall by *meaning*, not surface words (Vision §3, D11).

The honest fix for the lexical retriever's limit: "¿sabes mi nombre?" shares no words
with "me llamo Raúl", yet means the same thing. This retriever embeds the query and
each remembered candidate with a `TextEmbedder` (e.g. bge-m3 on a local ollama) and
ranks by cosine similarity, so meaning-close memories surface even when the wording
differs or the language changes.

It drops in behind the same :class:`MemoryRetriever` Protocol -- the executive and the
surface are unchanged (Vision §38). It stays a *capability that surfaces candidates*:
it never decides truth, and confidence is still derived by the domain.

Robust by design: candidate vectors are cached per text (embedded once per session),
and if the embedder is unreachable (ollama down) it falls back to a wrapped retriever
-- lexical recall rather than no recall -- so a local outage degrades, never breaks
(Vision §37).
"""

from __future__ import annotations

import math

from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.repositories.belief_repository import BeliefRepository
from jarvis.domain.repositories.episode_repository import EpisodeRepository
from jarvis.domain.retrieval.memory_retriever import MemoryRetriever
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.infrastructure.memory_candidates import gather_candidates
from jarvis.infrastructure.text_embedder import TextEmbedder

# Below this cosine similarity a memory is not meaning-close enough to surface.
# Calibrated against real bge-m3: identity-related queries score ~0.46-0.67 and clearly
# unrelated ones ~0.29-0.37, so 0.45 separates them. Model-specific and tunable (the
# same role the token-overlap floor plays for lexical recall).
_MIN_SIMILARITY = 0.45


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Cosine similarity of two vectors; 0.0 when either is empty or zero-length."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class EmbeddingMemoryRetriever:
    """Ranks Jarvis's stored memories by embedding similarity to a query."""

    def __init__(
        self,
        beliefs: BeliefRepository,
        episodes: EpisodeRepository,
        companion: CompanionModel,
        goals: BeliefRepository,
        embedder: TextEmbedder,
        *,
        fallback: MemoryRetriever | None = None,
    ) -> None:
        self._beliefs = beliefs
        self._episodes = episodes
        self._companion = companion
        self._goals = goals
        self._embedder = embedder
        self._fallback = fallback
        self._cache: dict[str, tuple[float, ...]] = {}

    def recall(self, query: str, *, limit: int = 5) -> tuple[RecalledMemory, ...]:
        if not query.strip():
            return ()
        candidates = list(
            gather_candidates(self._beliefs, self._episodes, self._companion, self._goals)
        )
        if not candidates:
            return ()
        try:
            query_vector = self._embed(query)
            vectors = self._embed_all(tuple(match_text for match_text, *_ in candidates))
        except Exception:  # noqa: BLE001 - embedder/network boundary; degrade, don't break
            return self._fallback.recall(query, limit=limit) if self._fallback else ()
        scored: list[RecalledMemory] = []
        for (_, content, kind, provenance, confidence), vector in zip(
            candidates, vectors, strict=True
        ):
            similarity = _cosine(query_vector, vector)
            if similarity < _MIN_SIMILARITY:
                continue
            scored.append(
                RecalledMemory(
                    content=content,
                    kind=kind,
                    provenance=provenance,
                    relevance=max(0.0, min(1.0, similarity)),
                    source_confidence=confidence,
                )
            )
        scored.sort(key=lambda m: (-m.relevance, -(m.source_confidence or 0.0), m.content))
        return tuple(scored[: max(0, limit)])

    def _embed(self, text: str) -> tuple[float, ...]:
        """Embed one text, using the per-session cache."""
        return self._embed_all((text,))[0]

    def _embed_all(self, texts: tuple[str, ...]) -> list[tuple[float, ...]]:
        """Embed many texts, embedding only the ones not already cached."""
        missing = tuple(dict.fromkeys(text for text in texts if text not in self._cache))
        if missing:
            for text, vector in zip(missing, self._embedder.embed(missing), strict=True):
                self._cache[text] = vector
        return [self._cache[text] for text in texts]
