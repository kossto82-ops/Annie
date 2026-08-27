"""LexicalMemoryRetriever: a deliberately simple, offline MemoryRetriever.

This is NOT the intelligence -- it is the seam (mirrors KeywordPerception,
Vision §32, §35). It ranks what Jarvis already holds -- world beliefs, episodic
records, companion traits, goal reachability -- by plain token overlap with the
query. It knows nothing about meaning: a query and a memory that share no surface
tokens simply do not match (honest silence, Vision §37), rather than a forced
guess.

Its whole purpose is to prove the boundary and make memory *usable* in
conversation: a semantic (embedding-backed) retriever can drop in behind the same
:class:`MemoryRetriever` Protocol without the cognitive core changing (Vision §38,
D11). Everything here is deterministic and offline (D8): no clocks, no randomness,
no network -- the same stores and query always yield the same ranking.

It only *surfaces candidates* carrying provenance; folding a recalled item into an
episode as evidence, and deriving any confidence from it, stays the executive's
job in a later step.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.repositories.belief_repository import BeliefRepository
from jarvis.domain.repositories.episode_repository import EpisodeRepository
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.executive.executive_controller import subject_of

# Tokens shorter than this carry too little signal to rank on (articles, "me",
# single letters). A short, language-agnostic floor -- not a stopword list.
_MIN_TOKEN_LEN = 2

# The template Jarvis stores a goal's reachability belief under; stripped back to
# the goal's own words so recall matches the goal, not the bookkeeping wrapper.
_GOAL_PREFIX = "The goal '"
_GOAL_SUFFIX = "' is reachable"

_WORD = re.compile(r"\w+")

# One raw candidate before scoring: the text to match against, the text to show,
# its kind, a provenance note, and the underlying belief's confidence if any.
_Candidate = tuple[str, str, MemoryKind, str, float | None]


def _tokens(text: str) -> set[str]:
    """The set of scoreable tokens in ``text`` -- lowercased, short ones dropped."""
    return {word for word in _WORD.findall(text.lower()) if len(word) >= _MIN_TOKEN_LEN}


def _relevance(query_tokens: set[str], text: str) -> float:
    """Fraction of the query's tokens the memory shares -- 0.0 when disjoint."""
    if not query_tokens:
        return 0.0
    shared = query_tokens & _tokens(text)
    return len(shared) / len(query_tokens)


def _goal_subject(statement: str) -> str:
    """The goal's own words behind its reachability-belief statement."""
    if statement.startswith(_GOAL_PREFIX) and statement.endswith(_GOAL_SUFFIX):
        return statement[len(_GOAL_PREFIX) : -len(_GOAL_SUFFIX)]
    return statement


def _looks_like_question(text: str) -> bool:
    """A question is something Jarvis was asked, not knowledge it can recall.

    Recalling a past question ("do you know my name?") as if it were an answer is
    noise, so question-shaped memories are not offered as recall.
    """
    return text.strip().endswith("?")


def _evidence_text(belief: Belief) -> str:
    """The words behind a belief -- the observations that formed it.

    A belief is often findable by the phrasing that taught it ("me llamo Raúl")
    even when its statement is worded differently ("is named Raúl"). Matching the
    evidence, not only the statement, bridges that gap (still surface tokens, D11).
    """
    return " ".join(evidence.content for evidence in belief.evidence)


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
        for match_text, content, kind, provenance, confidence in self._candidates():
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

    def _candidates(self) -> Iterator[_Candidate]:
        """Every memory that could match, as (match_text, content, kind, note, conf).

        Belief-backed memories match on both their statement and the words that
        formed them (the evidence), so a belief can be recalled by how it was
        taught. Question-shaped memories are skipped -- a past question is not
        knowledge to recall.
        """
        for belief in self._beliefs.all_beliefs():
            subject = subject_of(belief.statement)
            if _looks_like_question(subject):
                continue
            match_text = f"{subject} {_evidence_text(belief)}"
            yield (
                match_text,
                subject,
                MemoryKind.WORLD_BELIEF,
                "world belief",
                belief.confidence.value,
            )
        for record in self._episodes.history():
            # Match on, and show, the companion's own words (the trigger) plus the
            # goal it was toward -- what a person recognises as "what we talked
            # about". The internal decision text ("Insufficient evidence …") is
            # machine bookkeeping and would make a poor thing to recall.
            if _looks_like_question(record.trigger):
                continue
            match_text = (
                record.trigger
                if record.goal is None
                else f"{record.trigger} {record.goal}"
            )
            yield (
                match_text,
                record.trigger,
                MemoryKind.EPISODE,
                "episode",
                record.conclusion_confidence.value,
            )
        for belief in self._companion.beliefs():
            match_text = f"{belief.statement} {_evidence_text(belief)}"
            yield (
                match_text,
                belief.statement,
                MemoryKind.COMPANION_TRAIT,
                "companion trait",
                belief.confidence.value,
            )
        for belief in self._goals.all_beliefs():
            subject = _goal_subject(belief.statement)
            match_text = f"{subject} {_evidence_text(belief)}"
            yield (match_text, subject, MemoryKind.GOAL, "goal", belief.confidence.value)
