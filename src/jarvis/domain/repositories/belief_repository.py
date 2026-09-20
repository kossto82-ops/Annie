"""The contract for persisting and retrieving beliefs across episodes.

Continuity is the point of Jarvis (Vision §3): a belief must be able to outlive
the episode that formed it, so a later episode can retrieve it and add new
evidence rather than starting from zero.

This is a domain-level *interface* (a Protocol). Concrete storage lives in
``jarvis.infrastructure``. Crucially, a repository stores beliefs *with their
evidence* -- it never stores a truth flag. Confidence is always re-derived from
that evidence, so "memory" never becomes "truth" (Vision §22).

Belief addressing (Model B -- topic-anchored beliefs, BELIEF ADDRESSING v1):

    belief identity = canonical topic identity
    statement       = representative/display metadata
    episode trigger = original immutable observation

A working-conclusion statement carries its episode's original trigger after a
machine prefix, so a belief's address is a *pure function of its statement*:
``belief_topic_id`` projects the trigger onto its canonical topic identity
(``topic_resolution.topic_id_of``).  Different surface forms of the same matter
("supplier failed to deliver", "supplier succeeded in delivering", "didn't
deliver") therefore address ONE belief, while each stays readable through its
own historical statement.  Concept-free triggers resolve to their own trigger
(the topic-resolution fallback), so raw-trigger addressing is preserved without
inventing topics.  The authoritative semantic identity remains
``topic_resolution.topic_id_of``; nothing here is a second source of truth.

``reconcile_topic`` is the deterministic legacy-handling seam: persisted
statement-keyed beliefs that now resolve to one topic (pre-addressing data) are
reconstructed into a single topic-anchored belief without losing any evidence.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Protocol

from jarvis.domain.entities.belief import Belief
from jarvis.domain.services.topic_resolution import topic_id_of
from jarvis.domain.value_objects.evidence import Evidence

# The internal identity prefix for a working conclusion. It disambiguates working
# beliefs from other belief kinds and keeps retrieval deterministic (D17) — but it is
# machine bookkeeping, never shown to the companion (use `subject_of` at the surface).
WORKING_PREFIX = "Working conclusion about: "


def belief_topic_id(statement: str) -> str:
    """The deterministic belief address of a stored statement (Model B).

    A working-conclusion statement encodes the episode's original trigger after
    the machine prefix; the address is that trigger's canonical topic identity,
    so the same matter reached through different surface forms addresses one
    belief.  Concept-free triggers resolve to their own trigger (the topic
    resolution fallback), preserving raw-trigger addressing.  Statements without
    the working prefix (goal/action/companion beliefs) address by their own
    text's topic identity; their stores never route through ``get_by_topic``.
    """
    about = statement.removeprefix(WORKING_PREFIX)
    return topic_id_of(about)


def reconcile_topic(beliefs: Sequence[Belief]) -> Belief | None:
    """Deterministically reconstruct the one topic-anchored belief of a group.

    Legacy persistence may hold several raw-trigger beliefs that all resolve to
    one topic (data written before topic-anchored addressing).  Reconciliation
    folds them into a single belief without losing anything:

    * leader = the earliest-formed belief (the statement is the lexical
      tie-break) -- it contributes the address, id, formed_at and the
      representative statement, all display metadata rather than identity;
    * evidence = the stable chronological union (by evidence id, deduped) of
      every fragment's evidence -- direction, neutrality, provenance and
      timestamps are preserved as the identical persisted objects; nothing is
      invented.

    The result is a pure function of the group, so reloads reconstruct the same
    belief and repeated load/save cannot duplicate evidence.  The original
    fragments stay in the repository, so their historical statements remain
    retrievable through ``get_by_statement``.
    """
    if not beliefs:
        return None
    ordered = sorted(beliefs, key=lambda b: (b.formed_at, b.statement))
    leader = ordered[0]
    seen: set[str] = set()
    pool: list[Evidence] = []
    for belief in ordered:
        for piece in belief.evidence:
            if piece.id in seen:
                continue
            seen.add(piece.id)
            pool.append(piece)
    pool.sort(key=lambda evidence: evidence.observed_at)
    return Belief(
        statement=leader.statement,
        id=leader.id,
        formed_at=leader.formed_at,
        weighting_policy=leader.weighting_policy,
        _evidence=pool,
        precedents=list(leader.precedents),
    )


def resolve_belief_for(repository: BeliefRepository, trigger: str) -> Belief | None:
    """The topic-anchored belief a working conclusion for ``trigger`` addresses.

    Resolves by the trigger's canonical topic identity first (Model B), and
    falls back to the statement address for backward compatibility.  For a
    concept-free trigger the two addresses coincide (topic resolution falls
    back to the raw trigger), so the fallback is only a compat net.
    """
    topic = belief_topic_id(working_statement(trigger))
    belief = repository.get_by_topic(topic)
    if belief is None:
        belief = repository.get_by_statement(working_statement(trigger))
    return belief


def belief_registry(beliefs: Iterable[Belief]) -> dict[str, Belief]:
    """The topic-anchored index of beliefs: topic identity -> single belief.

    Stored statements that resolve to the same topic (legacy statement-keyed
    data) are folded into the reconstructed topic belief via
    :func:`reconcile_topic`, so a topic never indexes more than one belief.
    """
    grouped: dict[str, list[Belief]] = {}
    for belief in beliefs:
        grouped.setdefault(belief_topic_id(belief.statement), []).append(belief)
    registry: dict[str, Belief] = {}
    for topic, group in grouped.items():
        if len(group) == 1:
            registry[topic] = group[0]
        else:
            merged = reconcile_topic(group)
            assert merged is not None  # group is non-empty
            registry[topic] = merged
    return registry


def working_statement(trigger: str) -> str:
    """The representative statement of the belief an episode reasons toward.

    Deterministic, so the same trigger retrieves the same belief across episodes.
    """
    return f"{WORKING_PREFIX}{trigger}"


def subject_of(statement: str) -> str:
    """The natural subject behind a working-conclusion statement, for display.

    Strips the internal prefix so the surface can name what a belief is *about*
    in the companion's own words, never the machine label.  A statement without
    the prefix (a self-tendency, a companion trait) is returned unchanged.
    """
    return statement.removeprefix(WORKING_PREFIX)


class BeliefRepository(Protocol):
    """Persists beliefs and retrieves them by their topic-anchored address."""

    def get_by_topic(self, topic: str) -> Belief | None:
        """The single topic-anchored belief for ``topic``, or None if unknown.

        When several stored statement-keyed beliefs resolve to the same topic
        (legacy data), the reconstructed topic belief is returned deterministically
        via :func:`reconcile_topic`; the fragments remain retrievable by statement.
        """
        ...

    def get_by_statement(self, statement: str) -> Belief | None:
        """Return the stored belief with this exact statement, or None if unknown.

        Compatibility address: the authoritative address for concept-bearing
        working beliefs is the topic identity; statement lookup stays available
        for historical statements and non-working belief kinds.
        """
        ...

    def save(self, belief: Belief) -> None:
        """Persist (insert or update) a belief."""
        ...

    def all_beliefs(self) -> tuple[Belief, ...]:
        """Every belief currently stored."""
        ...

    def beliefs_formed_between(
        self, start: datetime, end: datetime
    ) -> tuple[Belief, ...]:
        """Beliefs whose ``formed_at`` falls within the given range (inclusive)."""
        ...

    def beliefs_about(self, subject_pattern: str) -> tuple[Belief, ...]:
        """Beliefs whose statement contains the given subject pattern (case-insensitive)."""
        ...

    def forget(self, statement: str) -> bool:
        """Remove a belief by statement. Returns True if found and removed."""
        ...