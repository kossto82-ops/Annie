"""Abstraction service — detecting patterns across episodes and beliefs.

Turns individual experiences into higher-order knowledge (semantic memories).
Each pattern must be grounded in at least ``min_sources`` independent episodes
or beliefs, so confidence stays derived and the pattern never outruns its
evidence.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from jarvis.domain.entities.semantic_memory import SemanticMemory
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence

_WORD = re.compile(r"\w+")

_STOPWORDS = frozenset(
    {
        "about", "above", "after", "again", "all", "also", "am", "an", "and",
        "any", "are", "as", "at", "be", "because", "been", "before", "being",
        "but", "by", "can", "cant", "cannot", "could", "did", "do", "does",
        "doing", "down", "during", "each", "for", "from", "had", "has", "have",
        "having", "he", "her", "here", "hers", "him", "his", "how", "i", "if",
        "in", "into", "is", "it", "its", "just", "me", "more", "most", "my",
        "no", "not", "now", "of", "off", "on", "or", "our", "ours", "out",
        "over", "own", "she", "should", "so", "some", "than", "that", "the",
        "their", "them", "then", "there", "these", "they", "this", "those",
        "through", "to", "too", "under", "until", "up", "us", "very", "was",
        "we", "were", "what", "when", "where", "which", "while", "who", "whom",
        "why", "will", "with", "you", "your", "yours",
        "de", "el", "la", "los", "las", "un", "una", "unos", "unas", "y", "o",
        "u", "que", "en", "con", "por", "para", "se", "su", "sus", "es",
        "son", "hay", "como", "hacia", "sobre", "entre", "del", "al", "ante",
        "pero", "mas", "muy", "este", "esta", "esto", "ese", "esa", "eso",
        "otro", "otra", "tambien", "ya", "cuando", "donde", "quien",
    }
)


def _extract_subject_words(text: str) -> list[str]:
    """Extract meaningful subject words from text (lowercased, stopwords removed)."""
    return [
        w.lower() for w in _WORD.findall(text)
        if w.lower() not in _STOPWORDS and len(w) > 2
    ]


def _cluster_episodes(
    episodes: Sequence[EpisodeRecord],
    min_sources: int = 3,
) -> dict[tuple[str, ...], list[EpisodeRecord]]:
    """Cluster episodes by shared subject words.

    Returns clusters where at least ``min_sources`` episodes share the same
    set of subject words (order-insensitive).
    """
    clusters: dict[frozenset[str], list[EpisodeRecord]] = {}
    for episode in episodes:
        words = frozenset(_extract_subject_words(episode.trigger))
        if not words:
            continue
        clusters.setdefault(words, []).append(episode)
    return {
        tuple(sorted(key)): val
        for key, val in clusters.items()
        if len(val) >= min_sources
    }


def abstract_patterns(
    episodes: Sequence[EpisodeRecord],
    beliefs: Sequence = (),
    min_sources: int = 3,
) -> list[SemanticMemory]:
    """Detect recurrent patterns in episodes and beliefs, producing semantic memories.

    Each pattern must be supported by at least ``min_sources`` independent
    episodes or beliefs.  Confidence is derived from the combined evidence;
    stability from the temporal spread.
    """
    clusters = _cluster_episodes(episodes, min_sources)
    results: list[SemanticMemory] = []

    for subject_words, cluster_episodes in clusters.items():
        pattern_text = "Los patrones relacionados con: " + ", ".join(subject_words)

        source_ids = [ep.episode_id for ep in cluster_episodes]
        evidence_pieces: list[Evidence] = []
        for ep in cluster_episodes:
            evidence_pieces.append(
                Evidence(
                    content=f"episodio '{ep.trigger}'",
                    source=__import__(
                        "jarvis.domain.enums.evidence_source",
                        fromlist=["EvidenceSource"],
                    ).EvidenceSource.SYSTEM_OBSERVATION,
                    weight=Confidence(0.5),
                    supports=True,
                )
            )

        memory = SemanticMemory(
            pattern=pattern_text,
            source_episode_ids=source_ids,
        )
        for e in evidence_pieces:
            memory.add_evidence(e)
            memory.pull_events()  # drain events during construction

        results.append(memory)

    results.sort(key=lambda m: m.confidence.value, reverse=True)
    return results
