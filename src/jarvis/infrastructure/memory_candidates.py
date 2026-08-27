"""Shared candidate gathering for memory retrievers (Vision §3).

Every retriever ranks the *same* set of remembered items -- world beliefs, episodes,
companion traits, goals -- and only the *scoring* differs (surface tokens vs. meaning).
So gathering them, and the rules for what is recallable, live here once: match a belief
by the words that formed it (its evidence), not only its statement; and never surface a
past *question* as if it were knowledge. Keeping this shared keeps the lexical and the
embedding retriever in lockstep.
"""

from __future__ import annotations

from collections.abc import Iterator

from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.repositories.belief_repository import BeliefRepository
from jarvis.domain.repositories.episode_repository import EpisodeRepository
from jarvis.executive.executive_controller import subject_of

_GOAL_PREFIX = "The goal '"
_GOAL_SUFFIX = "' is reachable"

# One raw candidate before scoring: the text to match against, the text to show, its
# kind, a provenance note, and the underlying belief's confidence if any.
Candidate = tuple[str, str, MemoryKind, str, float | None]


def looks_like_question(text: str) -> bool:
    """A question is something Jarvis was asked, not knowledge it can recall."""
    return text.strip().endswith("?")


def _evidence_text(belief: Belief) -> str:
    """The words behind a belief -- the observations that formed it."""
    return " ".join(evidence.content for evidence in belief.evidence)


def _goal_subject(statement: str) -> str:
    """The goal's own words behind its reachability-belief statement."""
    if statement.startswith(_GOAL_PREFIX) and statement.endswith(_GOAL_SUFFIX):
        return statement[len(_GOAL_PREFIX) : -len(_GOAL_SUFFIX)]
    return statement


def gather_candidates(
    beliefs: BeliefRepository,
    episodes: EpisodeRepository,
    companion: CompanionModel,
    goals: BeliefRepository,
) -> Iterator[Candidate]:
    """Every memory that could match, as (match_text, content, kind, note, conf).

    Belief-backed memories match on both their statement and the words that formed
    them (the evidence). Question-shaped memories are skipped.
    """
    for belief in beliefs.all_beliefs():
        subject = subject_of(belief.statement)
        if looks_like_question(subject):
            continue
        yield (
            f"{subject} {_evidence_text(belief)}",
            subject,
            MemoryKind.WORLD_BELIEF,
            "world belief",
            belief.confidence.value,
        )
    for record in episodes.history():
        if looks_like_question(record.trigger):
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
    for belief in companion.beliefs():
        yield (
            f"{belief.statement} {_evidence_text(belief)}",
            belief.statement,
            MemoryKind.COMPANION_TRAIT,
            "companion trait",
            belief.confidence.value,
        )
    for belief in goals.all_beliefs():
        subject = _goal_subject(belief.statement)
        yield (
            f"{subject} {_evidence_text(belief)}",
            subject,
            MemoryKind.GOAL,
            "goal",
            belief.confidence.value,
        )
