"""Persistent Jarvis factory functions.

Two factory functions that wire every store under one directory for full
cross-restart continuity.  They return a dict of keyword arguments ready to
unpack into ``Jarvis(…)`` — keeping the ``Jarvis`` class free of
infrastructure imports at the module level.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jarvis.domain.services.evidence_weighting import EvidenceWeightingPolicy
from jarvis.infrastructure.agent_reach_source import (
    build_web_source,
    llm_search_from_model,
)
from jarvis.infrastructure.document_store import build_document_store
from jarvis.infrastructure.env_settings import settings_from_env
from jarvis.infrastructure.in_memory_conversation_store import InMemoryConversationStore
from jarvis.infrastructure.json_belief_store import JsonBeliefStore
from jarvis.infrastructure.json_capability_store import JsonCapabilityStore
from jarvis.infrastructure.json_episode_store import JsonEpisodeStore
from jarvis.infrastructure.json_episode_trace import JsonEpisodeTrace
from jarvis.infrastructure.json_refutation_store import JsonRefutationStore
from jarvis.infrastructure.language_model_registry import build_language_model
from jarvis.infrastructure.odysseus_search_source import build_odysseus_search_source
from jarvis.infrastructure.speech_perception import EchoSpeechPerception
from jarvis.infrastructure.sqlite_conversation_store import SqliteConversationStore
from jarvis.infrastructure.sqlite_database import build_sqlite_repositories
from jarvis.infrastructure.sqlite_episode_trace import SqliteEpisodeTrace

# Provider names that mean "no real model": they must never back a live web-search
# capability (a scripted/stub model does not actually search the web).
_OFFLINE_PROVIDERS: frozenset[str] = frozenset({"", "scripted", "stub", "keyword"})


def build_persistent_kwargs(
    directory: str | Path,
    weighting_policy: EvidenceWeightingPolicy | None = None,
    default_belief_policy: EvidenceWeightingPolicy | None = None,
) -> dict[str, Any]:
    """Return kwargs for ``Jarvis(…)`` backed by JSON files under *directory*.

    Wires every store — beliefs, episodes, companion model, action learning,
    reversibility, goal reachability, sub-goal links, capability acquisitions
    (Odysseus), recognised capability needs, reflective-cycle refutations and
    the companion's documents — plus the decision-provenance trace to files
    under ``directory``, so a single call gives full continuity across restarts
    (Vision §3, §21, §26).  It composes the JSON stores and the JSONL trace log.
    """
    base = Path(directory)
    settings = settings_from_env()
    search_model = (
        build_language_model(settings)
        if settings.model and settings.provider not in _OFFLINE_PROVIDERS
        else None
    )
    source = build_web_source(
        llm_search_from_model(search_model) if search_model is not None else None
    )
    research = build_odysseus_search_source()
    return dict(
        beliefs=JsonBeliefStore(base / "beliefs.json", weighting_policy),
        episodes=JsonEpisodeStore(base / "episodes.json"),
        companion_store=JsonBeliefStore(base / "companion.json"),
        actions_store=JsonBeliefStore(base / "actions.json"),
        reversibility_store=JsonBeliefStore(base / "reversibility.json"),
        goals_store=JsonBeliefStore(base / "goals.json"),
        subgoals_store=JsonBeliefStore(base / "subgoals.json"),
        capabilities_store=JsonCapabilityStore(base / "capabilities.json"),
        needs_store=JsonBeliefStore(base / "needs.json"),
        refutations_store=JsonRefutationStore(base / "refutations.json"),
        trace=JsonEpisodeTrace(base / "trace.jsonl"),
        weighting_policy=weighting_policy,
        default_belief_policy=default_belief_policy,
        external_source=source,
        research_source=research,
        speech_perception=EchoSpeechPerception(),
        documents_store=build_document_store(base / "docs"),
        conversation_repository=InMemoryConversationStore(),
    )


def build_database_kwargs(
    directory: str | Path,
    weighting_policy: EvidenceWeightingPolicy | None = None,
    default_belief_policy: EvidenceWeightingPolicy | None = None,
) -> dict[str, Any]:
    """Return kwargs for ``Jarvis(…)`` backed by one SQLite database (D10).

    The companion item to :func:`build_persistent_kwargs`: every store — beliefs,
    episodes, companion model, action learning, reversibility, goal reachability,
    sub-goal links, capability acquisitions (Odysseus), recognised capability
    needs, reflective-cycle refutations and the decision-provenance trace are
    committed to a single transactional ``jarvis.db`` file under ``directory``,
    with the documents kept next to it under ``docs``.  Storage is an actual
    database (SQLite's durable transactions) behind the same repository
    contracts; confidence and stability are still re-derived from stored
    evidence on every read, never persisted as assertions.
    """
    base = Path(directory)
    base.mkdir(parents=True, exist_ok=True)
    wide = base / "jarvis.db"
    repositories = build_sqlite_repositories(wide, weighting_policy)
    settings = settings_from_env()
    search_model = (
        build_language_model(settings)
        if settings.model and settings.provider not in _OFFLINE_PROVIDERS
        else None
    )
    source = build_web_source(
        llm_search_from_model(search_model) if search_model is not None else None
    )
    research = build_odysseus_search_source()
    return dict(
        beliefs=repositories.beliefs,
        episodes=repositories.episodes,
        companion_store=repositories.companion,
        actions_store=repositories.actions,
        reversibility_store=repositories.reversibility,
        goals_store=repositories.goals,
        subgoals_store=repositories.subgoals,
        capabilities_store=repositories.capabilities,
        needs_store=repositories.needs,
        refutations_store=repositories.refutations,
        trace=SqliteEpisodeTrace(repositories.connection),
        weighting_policy=weighting_policy,
        default_belief_policy=default_belief_policy,
        external_source=source,
        research_source=research,
        speech_perception=EchoSpeechPerception(),
        documents_store=build_document_store(base / "docs"),
        conversation_repository=SqliteConversationStore(repositories.connection),
    )
