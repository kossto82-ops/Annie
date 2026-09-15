"""Abstraction service — detecting patterns across episodes and beliefs.

Turns individual experiences into higher-order knowledge (semantic memories).
Each pattern must be grounded in at least ``min_sources`` independent episodes
or beliefs, so confidence stays derived and the pattern never outruns its
evidence.

Design (reworked for semantic generalization):
- Conceptual vocabulary: common English stems map to canonical concept tokens
  (e.g. "miss" -> FAIL, "deliver" -> DELIVER). General-purpose, not domain-specific.
- Normalization: lowercase -> stem -> concept-map -> entity detection.
- Episode signature: frozenset of canonical concept tokens (entity-independent).
- Clustering: Jaccard(signature_a, signature_b) >= 0.3 AND shared non-entity concepts >= 1.
- Pattern key: English string "recurrence: {sorted concepts}" (no Spanish).
- Evidence: each matching episode adds evidence; negative/positive outcomes recorded
  in evidence content so the reasoner sees mixed-outcome context.
- Memoization: per-episode signatures cached to avoid O(H^2) on repeated think() calls.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from jarvis.domain.entities.semantic_memory import SemanticMemory
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence

# ---------------------------------------------------------------------------
# Conceptual vocabulary: stem -> canonical concept token
# ---------------------------------------------------------------------------

# Simple suffix-stripping stemmer for English
_STEM_SUFFIXES: tuple[str, ...] = (
    "ness", "ment", "tion", "sion", "ence", "ance", "able", "ible",
    "ous", "ive", "ful", "less", "ling", "ally", "ily", "ment",
    "ating", "izing", "ised", "ized", "edly", "ily", "ing", "ily",
    "ation", "ity", "ship", "dom", "ism", "ist", "er", "ed", "ly",
    "es", "s",
)

# Canonical concept tokens derived from common English verbs/adjectives
_CONCEPT_MAP: dict[str, str] = {
    # Failure / breach
    "miss": "FAIL", "breach": "FAIL", "fail": "FAIL", "break": "FAIL",
    "negate": "FAIL", "violate": "FAIL", "missed": "FAIL", "failed": "FAIL",
    "breached": "FAIL", "broken": "FAIL", "negated": "FAIL", "violated": "FAIL",
    "missing": "FAIL", "failing": "FAIL", "breaking": "FAIL",
    # Success
    "succeed": "SUCCEED", "meet": "SUCCEED", "achieve": "SUCCEED",
    "accomplish": "SUCCEED", "delivered": "SUCCEED", "achieved": "SUCCEED",
    "succeeded": "SUCCEED", "met": "SUCCEED", "accomplished": "SUCCEED",
    "delivering": "SUCCEED", "achieving": "SUCCEED",
    # Delivery / provision
    "deliver": "DELIVER", "supply": "DELIVER", "provide": "DELIVER",
    "send": "DELIVER", "fulfill": "DELIVER", "fulfilled": "DELIVER",
    "supplied": "DELIVER", "provided": "DELIVER", "sent": "DELIVER",
    "supplying": "DELIVER", "providing": "DELIVER", "sending": "DELIVER",
    "fulfilling": "DELIVER",
    # Promise / commitment
    "promise": "PROMISE", "commit": "PROMISE", "pledge": "PROMISE",
    "guarantee": "PROMISE", "vow": "PROMISE", "promised": "PROMISE",
    "committed": "PROMISE", "pledged": "PROMISE", "guaranteed": "PROMISE",
    "promising": "PROMISE", "committing": "PROMISE",
    # Request / demand
    "request": "REQUEST", "demand": "REQUEST", "ask": "REQUEST",
    "require": "REQUEST", "insist": "REQUEST", "requested": "REQUEST",
    "demanded": "REQUEST", "asked": "REQUEST", "required": "REQUEST",
    "insisted": "REQUEST", "requesting": "REQUEST",
    # Decrease / decline
    "reduce": "DECREASE", "decrease": "DECREASE", "drop": "DECREASE",
    "decline": "DECREASE", "shrink": "DECREASE", "lower": "DECREASE",
    "diminish": "DECREASE", "reduced": "DECREASE", "decreased": "DECREASE",
    "dropped": "DECREASE", "declined": "DECREASE", "shrunk": "DECREASE",
    "lowered": "DECREASE", "diminished": "DECREASE",
    "reducing": "DECREASE", "decreasing": "DECREASE", "dropping": "DECREASE",
    # Increase / growth
    "increase": "INCREASE", "grow": "INCREASE", "rise": "INCREASE",
    "expand": "INCREASE", "boost": "INCREASE", "improve": "INCREASE",
    "increased": "INCREASE", "grew": "INCREASE", "risen": "INCREASE",
    "expanded": "INCREASE", "boosted": "INCREASE", "improved": "INCREASE",
    "increasing": "INCREASE", "growing": "INCREASE", "improving": "INCREASE",
    # Risk / threat
    "risk": "RISK", "danger": "RISK", "threat": "RISK", "hazard": "RISK",
    "risky": "RISK", "dangerous": "RISK", "threatening": "RISK",
    # Safe / reliable
    "safe": "SAFE", "secure": "SAFE", "reliable": "SAFE", "stable": "SAFE",
    "safely": "SAFE", "securely": "SAFE", "reliably": "SAFE",
    # Decision / conclusion
    "decide": "DECIDE", "conclude": "DECIDE", "determine": "DECIDE",
    "decided": "DECIDE", "concluded": "DECIDE", "determined": "DECIDE",
    "deciding": "DECIDE", "concluding": "DECIDE",
    # Cause / prevent
    "cause": "CAUSE", "lead": "CAUSE", "result": "CAUSE", "create": "CAUSE",
    "caused": "CAUSE", "led": "CAUSE", "resulted": "CAUSE", "created": "CAUSE",
    "prevent": "PREVENT", "block": "PREVENT", "avoid": "PREVENT",
    "stopped": "PREVENT", "prevented": "PREVENT", "blocked": "PREVENT",
    "avoided": "PREVENT",
    # Time / schedule
    "time": "TIME", "schedule": "TIME", "deadline": "TIME", "late": "TIME",
    "delay": "TIME", "timely": "TIME",
    "delayed": "TIME", "scheduled": "TIME", "timed": "TIME",
    # Money / cost
    "cost": "COST", "price": "COST", "budget": "COST", "expense": "COST",
    "spend": "COST", "pay": "COST", "paid": "COST", "spent": "COST",
    "costly": "COST", "priced": "COST",
    # Reliability / consistency
    "dependable": "SAFE",
    "unreliable": "FAIL", "undependable": "FAIL", "inconsistent": "FAIL",
    "consistent": "SAFE", "dependably": "SAFE",
    # Compound forms with common prefixes
    "overpromised": "PROMISE", "overpromise": "PROMISE",
    "underpromised": "PROMISE", "underdelivered": "DELIVER",
    "overdelivered": "DELIVER", "misdelivered": "DELIVER",
    "underestimated": "DECREASE", "overestimated": "INCREASE",
    "restarted": "SUCCEED", "redelivered": "DELIVER",
    "preempted": "PREVENT",
    "delivery": "DELIVER", "failure": "FAIL",
    "commitment": "PROMISE", "deadlines": "TIME",
    "dates": "TIME", "estimat": "TIME",
}

# Role nouns → ROLE (entity-independent)
_ROLE_WORDS: frozenset[str] = frozenset({
    "supplier", "vendor", "contractor", "provider", "client", "customer",
    "user", "staff", "member", "team", "company", "firm", "agency",
    "department", "manager", "lead", "director", "developer", "engineer",
})

# Negation markers
_NEGATION: frozenset[str] = frozenset({"not", "never", "no", "nt"})

# Sentence-start position threshold
_MIN_CONCEPT_LEN = 2

# Only the most recent episodes feed consolidation, so repeated think() calls
# re-cluster a bounded slice instead of rescaling the whole history.
_CONSOLIDATION_WINDOW = 50


def _stem(word: str) -> str:
    """Minimal English suffix-stripping stemmer."""
    if len(word) <= _MIN_CONCEPT_LEN:
        return word
    for suffix in _STEM_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= _MIN_CONCEPT_LEN:
            return word[: -len(suffix)]
    return word


def _normalise_token(word: str) -> str | None:
    """Normalise a single token to a concept or None (stopword/negation/entity).

    Returns the canonical concept token for words that map, else None.
    """
    low = word.lower()
    # Negation detection
    if low in _NEGATION:
        return None  # caller handles negation separately
    # Role detection
    if low in _ROLE_WORDS:
        return "ROLE"
    # Concept mapping (exact form first)
    if low in _CONCEPT_MAP:
        return _CONCEPT_MAP[low]
    # Stemmed candidates: try each suffix strip; the first stem that resolves wins
    # (e.g. "promises" -> "promise", "misses" -> "miss", not "promis"/"misse").
    for suffix in _STEM_SUFFIXES:
        if low.endswith(suffix) and len(low) - len(suffix) >= _MIN_CONCEPT_LEN:
            stemmed = low[: -len(suffix)]
            if stemmed in _CONCEPT_MAP:
                return _CONCEPT_MAP[stemmed]
    return None


def _detect_negation(words: list[str]) -> bool:
    """True if any negation marker appears in the word list."""
    return any(w.lower() in _NEGATION for w in words)


def _episode_signature(trigger: str) -> frozenset[str]:
    """Compute canonical concept signature for a trigger string.

    Entity tokens (ROLE) are excluded from the signature — clustering is
    entity-independent.
    """
    return conceptual_tokens(trigger)


def conceptual_tokens(text: str) -> frozenset[str]:
    """The canonical concept tokens for arbitrary text (entity-independent).

    Used both for episode clustering (pattern abstraction) and by the memory
    retriever to match a query against concept-token patterns.
    """
    tokens = re.findall(r"\w+", text)
    concepts: set[str] = set()
    for tok in tokens:
        concept = _normalise_token(tok)
        if concept is not None and concept not in ("ROLE",):
            concepts.add(concept)
    return frozenset(concepts)


def _valence(trigger: str) -> str:
    """Valence of a trigger: negative for fail-like, positive for succeed-like."""
    tokens = re.findall(r"\w+", trigger)
    has_negation = _detect_negation(tokens)
    has_fail = any(
        _normalise_token(t) == "FAIL" for t in tokens
    )
    has_succeed = any(
        _normalise_token(t) == "SUCCEED" for t in tokens
    )
    if has_negation:
        # "not fail" = positive; "not succeed" = negative
        if has_fail:
            return "positive"
        if has_succeed:
            return "negative"
        return "neutral"
    if has_fail:
        return "negative"
    if has_succeed:
        return "positive"
    return "neutral"


def _concept_tokens_for_clustering(trigger: str) -> frozenset[str]:
    """Full concept set including ROLE for clustering (but signature is entity-independent)."""
    tokens = re.findall(r"\w+", trigger)
    concepts: set[str] = set()
    for tok in tokens:
        concept = _normalise_token(tok)
        if concept is not None:
            concepts.add(concept)
    return frozenset(concepts)


# ---------------------------------------------------------------------------
# Memoization cache: episode_id -> normalised signature
# ---------------------------------------------------------------------------

_sig_cache: dict[str, frozenset[str]] = {}


def _cached_signature(episode: EpisodeRecord) -> frozenset[str]:
    """Return the signature for an episode's trigger, computing if needed.

    The signature is a pure function of the trigger text, so the memo key is the
    trigger itself -- identical triggers share, and a colliding ``episode_id``
    can never serve a stale signature for a different trigger.
    """
    trigger = episode.trigger
    if trigger not in _sig_cache:
        _sig_cache[trigger] = _episode_signature(trigger)
    return _sig_cache[trigger]


def clear_signature_cache() -> None:
    """Clear the memoization cache (for tests or memory pressure)."""
    _sig_cache.clear()


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------

def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity between two sets."""
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _cluster_episodes(
    episodes: Sequence[EpisodeRecord],
    min_sources: int = 3,
    jaccard_threshold: float = 0.2,
) -> list[list[EpisodeRecord]]:
    """Cluster episodes by shared conceptual similarity.

    Uses Jaccard similarity on the concept set (entity-independent), requiring
    at least min_sources episodes and jaccard >= threshold with >= 1 shared
    non-entity concept.

    Returns a list of clusters (each cluster is a list of EpisodeRecords).
    """
    if not episodes:
        return []

    # Compute signatures
    sigs = [_cached_signature(ep) for ep in episodes]

    # Union-find for clustering
    parent = list(range(len(episodes)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i in range(len(episodes)):
        for j in range(i + 1, len(episodes)):
            if not sigs[i] or not sigs[j]:
                continue
            shared = sigs[i] & sigs[j]
            if not shared:
                continue
            if _jaccard(sigs[i], sigs[j]) >= jaccard_threshold:
                union(i, j)

    # Collect clusters
    groups: dict[int, list[int]] = {}
    for i in range(len(episodes)):
        root = find(i)
        groups.setdefault(root, []).append(i)

    clusters: list[list[EpisodeRecord]] = []
    for members in groups.values():
        if len(members) >= min_sources:
            clusters.append([episodes[i] for i in members])

    return clusters


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def abstract_patterns(
    episodes: Sequence[EpisodeRecord],
    beliefs: Sequence[Belief] = (),
    min_sources: int = 3,
) -> list[SemanticMemory]:
    """Detect recurrent patterns in episodes, producing semantic memories.

    Each pattern must be supported by at least ``min_sources`` independent
    episodes. Confidence is derived from the number of supporting episodes;
    the pattern key is an English canonical string (no Spanish).

    Beliefs are accepted for API compatibility but are not used for clustering
    (episode triggers carry richer signal).
    """
    if not episodes:
        return []

    clusters = _cluster_episodes(episodes, min_sources)
    results: list[SemanticMemory] = []

    for cluster_eps in clusters:
        # Compute shared concept set (entity-independent)
        cluster_sigs = [_cached_signature(ep) for ep in cluster_eps]
        shared_concepts: frozenset[str] = cluster_sigs[0]
        for sig in cluster_sigs[1:]:
            shared_concepts = shared_concepts & sig

        if not shared_concepts:
            continue

        # Pattern key: English canonical string
        sorted_concepts = sorted(shared_concepts)
        pattern_text = "recurrence: " + ", ".join(sorted_concepts)

        # Build semantic memory
        source_ids = [ep.episode_id for ep in cluster_eps]
        memory = SemanticMemory(
            pattern=pattern_text,
            source_episode_ids=source_ids,
        )

        # Feed evidence from each source episode. Valence decides direction:
        # an episode whose outcome is negative reinforces the failure-tendency
        # reading of the pattern; a positive outcome contests it (SemanticMemory
        # emits SemanticMemoryContested via supports=False), so contradictions
        # stay representable and confidence cannot collapse to a certainty.
        for ep in cluster_eps:
            valence = _valence(ep.trigger)
            supports = valence != "positive"
            evidence_content = (
                f"episode '{ep.trigger}' (outcome: {valence})"
            )
            memory.add_evidence(
                Evidence(
                    content=evidence_content,
                    source=EvidenceSource.SYSTEM_OBSERVATION,
                    weight=Confidence(0.5),
                    supports=supports,
                )
            )
            memory.pull_events()

        results.append(memory)

    results.sort(key=lambda m: m.confidence.value, reverse=True)
    return results


def consolidate_semantic_memories(
    episodes: Sequence[EpisodeRecord],
    store,  # SemanticMemoryRepository
    min_sources: int = 3,
    window: int = _CONSOLIDATION_WINDOW,
) -> list[SemanticMemory]:
    """Compute abstraction over recent episodes and persist into the semantic store.

    SemanticMemory.save() is an upsert by pattern key: existing memories get
    additional evidence, new patterns create fresh memories.

    Only the most recent ``window`` episodes feed new clustering (matching the
    bounded-attention philosophy): stored memories persist and keep growing, but
    each call re-clusters a fixed slice instead of rescaling the whole history, so
    a long-lived session never turns into quadratic work. A store that reloaded
    older episodes is unaffected — they stay only as already-persisted evidence.

    Returns the list of memories that were stored/updated.
    """
    if not episodes:
        return []

    recent = episodes[-window:]
    memories = abstract_patterns(recent, min_sources=min_sources)
    stored: list[SemanticMemory] = []
    by_id: dict[str, EpisodeRecord] = {ep.episode_id: ep for ep in recent}

    for mem in memories:
        existing = store.get_by_pattern(mem.pattern)
        if existing is not None:
            # Merge: add source episodes from the new computation
            existing_sources = set(existing.source_episode_ids)
            new_sources = [sid for sid in mem.source_episode_ids if sid not in existing_sources]
            for sid in new_sources:
                ep = by_id.get(sid)
                if ep is None:
                    continue
                valence = _valence(ep.trigger)
                existing.add_evidence(
                    Evidence(
                        content=f"episode '{ep.trigger}' (outcome: {valence})",
                        source=EvidenceSource.SYSTEM_OBSERVATION,
                        weight=Confidence(0.5),
                        supports=valence != "positive",
                    )
                )
                existing.pull_events()
            existing.source_episode_ids = list(
                set(existing.source_episode_ids) | set(mem.source_episode_ids)
            )
            store.save(existing)
            stored.append(existing)
        else:
            store.save(mem)
            stored.append(mem)

    return stored
