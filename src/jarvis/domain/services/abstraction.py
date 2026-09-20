"""Abstraction service — detecting patterns across episodes and beliefs.

Turns individual experiences into higher-order knowledge (semantic memories).
Each pattern must be grounded in at least ``min_sources`` independent episodes
or beliefs, so confidence stays derived and the pattern never outruns its
evidence.

Design (reworked for semantic generalization):
- Conceptual vocabulary: common English supply-chain stems AND a small bilingual
  (Spanish/English) everyday set map to canonical concept tokens (e.g. "miss" ->
  FAIL, "build"/"construyendo" -> BUILD). General-purpose, not domain-specific.
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
from functools import lru_cache
from typing import TYPE_CHECKING

from jarvis.domain.entities.semantic_memory import SemanticMemory
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.repositories.semantic_memory_repository import SemanticMemoryRepository
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence

if TYPE_CHECKING:
    from jarvis.domain.entities.belief import Belief

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
CONCEPT_MAP: dict[str, str] = {
    # Failure / breach
    "miss": "FAIL", "breach": "FAIL", "fail": "FAIL", "break": "FAIL",
    "negate": "FAIL", "violate": "FAIL", "missed": "FAIL", "failed": "FAIL",
    "breached": "FAIL", "broken": "FAIL", "negated": "FAIL", "violated": "FAIL",
    "missing": "FAIL", "failing": "FAIL", "breaking": "FAIL",
    # Success
    "succeed": "SUCCEED", "meet": "SUCCEED", "achieve": "SUCCEED",
    "accomplish": "SUCCEED", "achieved": "SUCCEED",
    "succeeded": "SUCCEED", "met": "SUCCEED", "accomplished": "SUCCEED",
    "achieving": "SUCCEED", "successfully": "SUCCEED",
    # Delivery / provision
    "deliver": "DELIVER", "delivered": "DELIVER", "delivering": "DELIVER",
    "supply": "DELIVER", "provide": "DELIVER",
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
    "cause": "CAUSE", "lead": "CAUSE", "result": "CAUSE",
    "caused": "CAUSE", "led": "CAUSE", "resulted": "CAUSE",
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
    "redelivered": "DELIVER",
    "preempted": "PREVENT",
    "delivery": "DELIVER", "failure": "FAIL",
    "commitment": "PROMISE", "deadlines": "TIME",
    "dates": "TIME",
    # Irregular past forms -> canonical concept
    "broke": "FAIL", "lost": "FAIL",
    "bought": "COST", "sold": "COST", "repaid": "COST",
    "underpaid": "COST", "overpaid": "COST", "outbid": "COST",
    "brought": "DELIVER",
    "shipped": "DELIVER",
    "chose": "DECIDE", "chosen": "DECIDE", "picked": "DECIDE",
    "selected": "DECIDE",
    "fell": "DECREASE", "shrank": "DECREASE",
    "raised": "INCREASE", "rose": "INCREASE", "doubled": "INCREASE",
    "soared": "INCREASE",
    "won": "SUCCEED", "overcame": "SUCCEED",
    "forbade": "PREVENT", "banned": "PREVENT", "barred": "PREVENT",
    "built": "CAUSE", "sparked": "CAUSE",
    "vowed": "PROMISE", "swore": "PROMISE",
    "threatened": "RISK", "secured": "SAFE",
    "overdue": "TIME",
    # ------------------------------------------------------------------
    # Everyday companion vocabulary (bilingual). A deliberately small set —
    # the words a companion actually uses with Jarvis about itself, its plans
    # and its preferences — so a Spanish memory and an English question (or a
    # paraphrase with no shared words) still meet on the same canonical token.
    # "create/created" stay unmapped on purpose (matter preservation:
    # production != causation); "crear/creando" cover the companion sense.
    # ------------------------------------------------------------------
    # BUILD — making / building something
    "build": "BUILD", "building": "BUILD",
    "construct": "BUILD", "constructing": "BUILD", "constructed": "BUILD",
    "construir": "BUILD", "construyendo": "BUILD", "construyo": "BUILD",
    "construye": "BUILD", "construí": "BUILD", "construi": "BUILD",
    "crear": "BUILD", "creando": "BUILD",
    # LEARN — learning / studying
    "learn": "LEARN", "learning": "LEARN", "learned": "LEARN",
    "aprender": "LEARN", "aprendiendo": "LEARN", "aprendí": "LEARN",
    "aprendi": "LEARN",
    # TRAVEL — trips
    "travel": "TRAVEL", "traveling": "TRAVEL", "travelling": "TRAVEL",
    "trip": "TRAVEL", "trips": "TRAVEL",
    "viaje": "TRAVEL", "viajes": "TRAVEL", "viajar": "TRAVEL",
    "viajando": "TRAVEL",
    # CHALLENGE — contradicting / dissenting (not victory)
    "challenge": "CHALLENGE", "challenges": "CHALLENGE",
    "challenged": "CHALLENGE", "challenging": "CHALLENGE",
    "contradict": "CHALLENGE", "contradicts": "CHALLENGE",
    "contradicted": "CHALLENGE", "contradicting": "CHALLENGE",
    "disagree": "CHALLENGE", "disagrees": "CHALLENGE",
    "disagreed": "CHALLENGE",
    "contradecir": "CHALLENGE", "contradiga": "CHALLENGE",
    "contradigas": "CHALLENGE",
    # WRONG — error / being mistaken
    "wrong": "WRONG", "incorrect": "WRONG", "incorrectly": "WRONG",
    "mistake": "WRONG", "mistakes": "WRONG", "error": "WRONG",
    "errors": "WRONG",
    "equivocado": "WRONG", "equivocada": "WRONG",
    "equivocados": "WRONG", "equivocadas": "WRONG",
    # AGREE — consenting / conceding
    "agree": "AGREE", "agrees": "AGREE", "agreed": "AGREE",
    "agreeing": "AGREE",
    # REMEMBER — recalling / keeping
    "remember": "REMEMBER", "remembered": "REMEMBER",
    "remembering": "REMEMBER",
    "recordar": "REMEMBER", "recuerda": "REMEMBER",
    "recuerdo": "REMEMBER", "recuerde": "REMEMBER",
    "recuerdas": "REMEMBER",
    # HISTORY — the shared story / past
    "history": "HISTORY", "historic": "HISTORY",
    "historia": "HISTORY", "historias": "HISTORY",
    # COMPANION — the counterpart
    "companion": "COMPANION", "companions": "COMPANION",
    "compañero": "COMPANION", "compañera": "COMPANION",
    "compañeros": "COMPANION",
    # PURPOSE — an endeavor / what something is for (a long-term project
    # and its goal share this token on purpose)
    "purpose": "PURPOSE", "purposes": "PURPOSE", "goal": "PURPOSE",
    "propósito": "PURPOSE", "proposito": "PURPOSE", "objetivo": "PURPOSE",
    "objetivos": "PURPOSE", "proyecto": "PURPOSE", "project": "PURPOSE",
    # Spanish forms of the existing dimensions (the everyday set only)
    "crecer": "INCREASE", "creciendo": "INCREASE",
    "reducir": "DECREASE", "reducido": "DECREASE",
    "costo": "COST", "costos": "COST", "pagar": "COST",
    "falla": "FAIL",
    "decidir": "DECIDE", "decisión": "DECIDE", "decision": "DECIDE",
    "prevenir": "PREVENT",
    "retraso": "TIME", "retrasar": "TIME",
}

# Role nouns → ROLE (entity-independent)
_ROLE_WORDS: frozenset[str] = frozenset({
    "supplier", "vendor", "contractor", "provider", "client", "customer",
    "user", "staff", "member", "team", "company", "firm", "agency",
    "department", "manager", "lead", "director", "developer", "engineer",
})

# Explicit lemma restorations for e-drop / y→ies roots that suffix stripping
# over-consumes ("causing" -> "caus", "deliveries" -> "deliveri"). Each entry
# restores a stripped stem to a lemma that ALREADY exists in CONCEPT_MAP; the
# concept assignment still comes from CONCEPT_MAP, so this layer is ontology-
# neutral (estimate, create, receive, cancel, stop and give are deliberately
# absent and therefore resolve to None).
_E_DROP_LEMMAS: dict[str, str] = {
    "caus": "cause",  # causing -> CAUSE
    "secur": "secure",  # securing -> SAFE
    "schedul": "schedule",  # scheduling -> TIME
    "requir": "require",  # requiring -> REQUEST
    "pric": "price",  # pricing -> COST
    "deliveri": "delivery",  # deliveries -> DELIVER
}

# Negation markers: the single authoritative contract shared with the keyword
# perception seam. "can't" expands to "cannot", so the canonical marker set is
# the full-form words only. Parity of these markers decides clause polarity.
NEGATION_MARKERS: frozenset[str] = frozenset({"not", "never", "no", "cannot"})

# Contracted negation forms expanded before tokenization so their negation is
# visible to the parity counter ("didn't" -> "did not"). The expansions insert
# only words that carry no concept, so matter identity is unchanged. This also
# prevents tokenization corruption: without expansion "won't" splits into
# "won" -> SUCCEED, injecting false positive matter.
_CONTRACTIONS: dict[str, str] = {
    "didn't": "did not",
    "doesn't": "does not",
    "don't": "do not",
    "isn't": "is not",
    "wasn't": "was not",
    "weren't": "were not",
    "can't": "cannot",
    "won't": "will not",
    "couldn't": "could not",
    "shouldn't": "should not",
    "wouldn't": "would not",
    "mustn't": "must not",
}


def expand_contractions(text: str) -> str:
    """Lowercase and expand known contracted negation forms."""
    lowered = text.lower()
    for contraction, full in _CONTRACTIONS.items():
        lowered = lowered.replace(contraction, full)
    return lowered

# Sentence-start position threshold
_MIN_CONCEPT_LEN = 2

# Only the most recent episodes feed consolidation, so repeated think() calls
# re-cluster a bounded slice instead of rescaling the whole history.
_CONSOLIDATION_WINDOW = 50


def _normalise_token(word: str) -> str | None:
    """Normalise a single token to a concept or None (stopword/negation/entity).

    Returns the canonical concept token for words that map, else None.
    """
    low = word.lower()
    # Negation detection (callers handle the marker parity separately)
    if low in NEGATION_MARKERS:
        return None
    # Role detection
    if low in _ROLE_WORDS:
        return "ROLE"
    # Concept mapping (exact form first)
    if low in CONCEPT_MAP:
        return CONCEPT_MAP[low]
    # Stemmed candidates: try each suffix strip; the first stem that resolves wins
    # (e.g. "promises" -> "promise", "misses" -> "miss", not "promis"/"misse").
    for suffix in _STEM_SUFFIXES:
        if low.endswith(suffix) and len(low) - len(suffix) >= _MIN_CONCEPT_LEN:
            stemmed = low[: -len(suffix)]
            if stemmed in CONCEPT_MAP:
                return CONCEPT_MAP[stemmed]
            lemma = _E_DROP_LEMMAS.get(stemmed)
            if lemma is not None and lemma in CONCEPT_MAP:
                return CONCEPT_MAP[lemma]
    return None


def _count_negation_markers(words: list[str]) -> int:
    """Count negation markers; parity decides whether the clause is negated.

    Multiple markers carry semantic weight: "didn't ever not fail" contains
    three negations, so per parity (odd -> negated) it reads positively, and
    the alternating count is a first-class signal rather than a single flag.
    """
    return sum(1 for w in words if w.lower() in NEGATION_MARKERS)


def episode_signature(trigger: str) -> frozenset[str]:
    """Compute canonical concept signature for a trigger string.

    Entity tokens (ROLE) are excluded from the signature — clustering is
    entity-independent.
    """
    return _signature_for_trigger(trigger)


def conceptual_tokens(text: str) -> frozenset[str]:
    """The canonical concept tokens for arbitrary text (entity-independent).

    Used both for episode clustering (pattern abstraction) and by the memory
    retriever to match a query against concept-token patterns.
    """
    tokens = re.findall(r"\w+", expand_contractions(text))
    concepts: set[str] = set()
    for tok in tokens:
        concept = _normalise_token(tok)
        if concept is not None and concept not in ("ROLE",):
            concepts.add(concept)
    return frozenset(concepts)


def surface_overlap(query: str, text: str) -> float:
    """Fraction of the query's scoreable tokens the text shares -- 0.0 when disjoint.

    The plain-word channel. Tokens shorter than ``_MIN_CONCEPT_LEN`` carry too
    little signal to rank on (articles, "me"): a short, language-agnostic floor,
    not a stopword list.
    """
    query_tokens = {
        word for word in re.findall(r"\w+", query.lower()) if len(word) >= _MIN_CONCEPT_LEN
    }
    if not query_tokens:
        return 0.0
    text_tokens = {
        word for word in re.findall(r"\w+", text.lower()) if len(word) >= _MIN_CONCEPT_LEN
    }
    return len(query_tokens & text_tokens) / len(query_tokens)


def concept_relevance(query: str, text: str) -> float:
    """Fraction of the query's canonical concepts the text shares -- 0.0 when either
    side carries none.

    The meaning channel. The CONCEPT_MAP is bilingual, so a Spanish text and an
    English query that share no surface words still meet on the canonical token
    (e.g. "build" and "construyendo" both resolve to BUILD).
    """
    query_concepts = conceptual_tokens(query)
    if not query_concepts:
        return 0.0
    kept_concepts = conceptual_tokens(text)
    if not kept_concepts:
        return 0.0
    return len(query_concepts & kept_concepts) / len(query_concepts)


def relatedness(query: str, text: str) -> float:
    """How strongly ``text`` bears on ``query``, by words or by concept -- whichever
    is stronger.

    The offline bridge across paraphrase and language used by the memory
    retrievers and the companion-trait bridge: one channel can be zero while
    the other still grounds a match. 0.0 means no signal at all -- honest
    silence (Vision §37), never a forced guess.
    """
    return max(surface_overlap(query, text), concept_relevance(query, text))


def valence(trigger: str) -> str:
    """Valence of a trigger: negative for fail-like, positive for succeed-like."""
    tokens = re.findall(r"\w+", expand_contractions(trigger))
    negated = _count_negation_markers(tokens) % 2 == 1
    has_fail = any(
        _normalise_token(t) == "FAIL" for t in tokens
    )
    has_succeed = any(
        _normalise_token(t) == "SUCCEED" for t in tokens
    )
    if negated:
        # "did not fail" = positive; "did not succeed" = negative
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


# ---------------------------------------------------------------------------
# Memoization cache: trigger text -> normalised signature
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1024)
def _signature_for_trigger(trigger: str) -> frozenset[str]:
    """The signature is a pure function of the trigger text, so the memo key is
    the trigger itself -- identical triggers share one cache entry.
    """
    return conceptual_tokens(trigger)


def cached_signature(episode: EpisodeRecord) -> frozenset[str]:
    """Return the signature for an episode's trigger (memoized per trigger)."""
    return episode_signature(episode.trigger)


def clear_signature_cache() -> None:
    """Clear the memoization cache (for tests or memory pressure)."""
    _signature_for_trigger.cache_clear()


def signature_cache_info() -> tuple[int, int, int | None, int]:
    """(hit, miss, maxsize, currsize) of the trigger-signature memo cache."""
    info = _signature_for_trigger.cache_info()
    return (info.hits, info.misses, info.maxsize, info.currsize)


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
    sigs = [cached_signature(ep) for ep in episodes]

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

    Only externally-triggered episodes (``TriggerOrigin.COMPANION``) feed
    abstraction: internal cognition (e.g. a curiosity pursuit) must not
    manufacture semantic memories out of its own echoes.
    """
    if not episodes:
        return []

    external = [ep for ep in episodes if ep.origin is TriggerOrigin.COMPANION]
    if not external:
        return []

    clusters = _cluster_episodes(external, min_sources)
    results: list[SemanticMemory] = []

    for cluster_eps in clusters:
        # Compute shared concept set (entity-independent)
        cluster_sigs = [cached_signature(ep) for ep in cluster_eps]
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
        # Valence-less episodes contribute *neutral* evidence: it neither
        # strengthens nor contests the pattern, and is skipped by confidence
        # derivation (P6).
        pattern_evidence: list[Evidence] = []
        for ep in cluster_eps:
            val = valence(ep.trigger)
            pattern_evidence.append(
                Evidence(
                    content=f"episode '{ep.trigger}' (outcome: {val})",
                    source=EvidenceSource.SYSTEM_OBSERVATION,
                    weight=Confidence(0.5),
                    supports=val != "positive",
                    is_neutral=val == "neutral",
                )
            )
        for evidence_item in pattern_evidence:
            memory.add_evidence(evidence_item)
        memory.pull_events()

        results.append(memory)

    results.sort(key=lambda m: m.confidence.value, reverse=True)
    return results


def consolidate_semantic_memories(
    episodes: Sequence[EpisodeRecord],
    store: SemanticMemoryRepository,
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
                val = valence(ep.trigger)
                existing.add_evidence(
                    Evidence(
                        content=f"episode '{ep.trigger}' (outcome: {val})",
                        source=EvidenceSource.SYSTEM_OBSERVATION,
                        weight=Confidence(0.5),
                        supports=val != "positive",
                        is_neutral=val == "neutral",
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
