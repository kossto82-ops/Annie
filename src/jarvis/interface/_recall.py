"""Recall/memory handlers — the memory search surface."""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.jarvis import Jarvis

if TYPE_CHECKING:
    pass

# A reply the UI can render and (optionally) speak; some commands add extra fields.
Reply = dict[str, object]

# Episodes this far apart start a new session arc (an honest, documented
# grouping heuristic: the store keeps no session id, so a quiet hour splits).
_SESSION_GAP_SECONDS = 3600.0


def _conversations_block(jarvis: Jarvis, session_limit: int = 12) -> list[Reply]:
    """Past episodes grouped into session arcs, newest first (F5).

    A session is a maximal run of episodes less than an hour apart -- memory,
    never belief: trigger, outcome and time per episode, so the surface can
    recap an arc without asserting any of it.
    """
    try:
        history = sorted(jarvis.episodes.history(), key=lambda r: r.recorded_at)
    except Exception:  # noqa: BLE001 - the store boundary
        return []
    sessions: list[list[EpisodeRecord]] = []
    for record in history:
        if (
            sessions
            and (record.recorded_at - sessions[-1][-1].recorded_at).total_seconds()
            <= _SESSION_GAP_SECONDS
        ):
            sessions[-1].append(record)
        else:
            sessions.append([record])
    block: list[Reply] = []
    for index, run in enumerate(reversed(sessions[-session_limit:])):
        first = run[0]
        last = run[-1]
        block.append(
            {
                "id": index,
                "start": first.recorded_at.isoformat(),
                "end": last.recorded_at.isoformat(),
                "count": len(run),
                "episodes": [
                    {
                        "trigger": episode.trigger,
                        "outcome": episode.outcome.name,
                        "recorded_at": episode.recorded_at.isoformat(),
                    }
                    for episode in run
                ],
            }
        )
    return block


def _conversations(jarvis: Jarvis, payload: Reply) -> Reply:
    """List past episode sessions so the surface can recap one (F5).

    Returns the session arcs, each with its episodes, so the surface can post
    one back to the chat -- framed as remembered, never re-asserted.
    """
    _ = payload
    sessions = _conversations_block(jarvis)
    if not sessions:
        return {
            "reply": "No past conversations yet — talk to me and they will land here.",
            "speak": False,
            "sessions": [],
        }
    lines = [
        f"- sesión {s['id']}: {s['count']} episodios ({s['start']} → {s['end']})"
        for s in sessions
    ]
    return {
        "reply": "Past sessions:\n" + "\n".join(lines),
        "speak": False,
        "sessions": sessions,
    }


def _recall(jarvis: Jarvis, payload: Reply) -> Reply:
    """Actively search Jarvis's memory for what bears on a query (F5).

    Runs the recall seam (lexical offline, meaning-backed when an embedder is
    wired) and reports candidates with their match strength and provenance --
    candidates, never a verdict. Nothing is written: recall reads only.
    """
    query = str(payload.get("query", "")).strip()
    if not query:
        return {"reply": "Ask what to search my memory for.", "speak": False}
    try:
        limit = int(payload.get("limit", 5))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        limit = 5
    limit = max(1, min(limit, 20))
    recalled = jarvis.recall(query)[:limit]
    if not recalled:
        return {
            "reply": f"Nothing in my memory bears on {query!r} yet.",
            "speak": False,
            "memories": [],
        }
    entries = [
        {
            "content": item.content,
            "kind": item.kind.name,
            "provenance": item.provenance,
            "relevance": round(item.relevance, 4),
            "source_confidence": item.source_confidence,
        }
        for item in recalled
    ]
    lines = [
        f"{i}. [{e['kind']}] {e['content']} (match {e['relevance']:.2f}, {e['provenance']})"
        for i, e in enumerate(entries, 1)
    ]
    return {
        "reply": f"What my memory surfaces for {query!r} (candidates, not verdicts):\n"
        + "\n".join(lines),
        "speak": False,
        "memories": entries,
    }
