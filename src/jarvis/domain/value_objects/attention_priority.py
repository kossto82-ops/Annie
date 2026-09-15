"""AttentionPriority: a derived saliency ranking for one topic.

Attention priority says *what to attend to next* -- a ranked importance Jarvis
learns from its own accumulated experience (Vision §16, audit §2.1). It is
re-derived on every read from the recorded episodes, never persisted as a score,
so it cannot outlive or contradict the evidence it summarises.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AttentionPriority:
    """One topic's bounded saliency, derived from the recent episode history.

    ``topic`` is the topic's canonical identity (its conceptual signature, or
    the bootstrap trigger for a concept-free topic) -- never the raw trigger of
    one episode.  ``priority`` is a deterministic, bounded number in ``[0, 1]``;
    higher means Jarvis should attend to ``topic`` sooner.
    ``episodes_on_topic``, ``unresolved``, ``revised`` and ``last_episode_recency``
    expose the raw signals so an observer can see *why* the topic earned its
    rank.  ``representative`` is *display* metadata only: the most recent
    episode's trigger, shown to the companion, never used as identity.
    """

    topic: str
    priority: float
    episodes_on_topic: int
    unresolved: int
    revised: bool
    last_episode_recency: float
    representative: str