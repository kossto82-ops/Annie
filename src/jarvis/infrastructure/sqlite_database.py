"""Composition root for a SQLite-backed Jarvis memory (Vision §3, §21, D10).

Lines up one SQLite database -- ``jarvis.db`` -- behind every cognitive storage
contract at once. A single connection owns every table, so a Jarvis built from
these repositories has one durable, transactional memory instead of many
independent JSON files. The connection is opened with ``check_same_thread=False``
so the composition root (e.g. the threaded command center server) may share it;
SQLite still serialises writers, so cross-store saves stay safe.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from jarvis.domain.services.evidence_weighting import EvidenceWeightingPolicy
from jarvis.infrastructure.sqlite_belief_store import SqliteBeliefStore
from jarvis.infrastructure.sqlite_capability_store import SqliteCapabilityStore
from jarvis.infrastructure.sqlite_episode_store import SqliteEpisodeStore
from jarvis.infrastructure.sqlite_refutation_store import SqliteRefutationStore


@dataclass(frozen=True)
class SqliteRepositories:
    """Every repository contract, all backed by the one database."""

    connection: sqlite3.Connection
    beliefs: SqliteBeliefStore
    episodes: SqliteEpisodeStore
    companion: SqliteBeliefStore
    actions: SqliteBeliefStore
    reversibility: SqliteBeliefStore
    goals: SqliteBeliefStore
    subgoals: SqliteBeliefStore
    needs: SqliteBeliefStore
    capabilities: SqliteCapabilityStore
    refutations: SqliteRefutationStore

    def close(self) -> None:
        """Release the underlying connection (call when the Jarvis shuts down)."""
        self.connection.close()


def build_sqlite_repositories(
    path: str | Path,
    weighting_policy: EvidenceWeightingPolicy | None = None,
) -> SqliteRepositories:
    """Open ``path`` (created if missing) as the memory of a whole Jarvis."""
    connection = sqlite3.connect(str(Path(path)), check_same_thread=False)
    connection.execute("PRAGMA foreign_keys = ON")
    return SqliteRepositories(
        connection=connection,
        beliefs=SqliteBeliefStore(
            connection, table="beliefs", weighting_policy=weighting_policy
        ),
        episodes=SqliteEpisodeStore(connection),
        companion=SqliteBeliefStore(
            connection, table="companion", weighting_policy=weighting_policy
        ),
        actions=SqliteBeliefStore(
            connection, table="actions", weighting_policy=weighting_policy
        ),
        reversibility=SqliteBeliefStore(
            connection, table="reversibility", weighting_policy=weighting_policy
        ),
        goals=SqliteBeliefStore(
            connection, table="goals", weighting_policy=weighting_policy
        ),
        subgoals=SqliteBeliefStore(
            connection, table="subgoals", weighting_policy=weighting_policy
        ),
        needs=SqliteBeliefStore(
            connection, table="needs", weighting_policy=weighting_policy
        ),
        capabilities=SqliteCapabilityStore(connection),
        refutations=SqliteRefutationStore(connection),
    )