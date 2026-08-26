"""The command center's brain: pure request handling over a Jarvis (Vision §30, §40).

Two layers, both pure and hermetic:

* :func:`handle` maps a command name + payload to a JSON-serializable reply by
  calling Jarvis's ordinary public methods — perceive, reflect, introspect, tune
  energy. It invents nothing; every reply traces to what Jarvis actually did or
  holds. Each result carries a fresh :func:`snapshot` so the UI stays live.
* :func:`route` maps an HTTP method + path + body to a :class:`Response` — serving
  the page, ``GET /api/state``, and ``POST /api/<command>`` — with zero sockets, so
  the whole surface is unit-testable without a network.

The socket lives in :mod:`jarvis.interface.server` and only carries these bytes.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from jarvis.domain.entities.belief import Belief
from jarvis.domain.events.belief_events import (
    BeliefStrengthened,
    BeliefWeakened,
    ContradictionDetected,
)
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.events.episode_events import EpisodeCompleted, EpisodeStarted
from jarvis.domain.events.evidence_events import EvidenceAdded
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.executive.executive_controller import working_statement
from jarvis.jarvis import Jarvis

_CONSOLE_HTML = Path(__file__).with_name("console.html")

# A reply the UI can render and (optionally) speak; some commands add extra fields.
Reply = dict[str, object]
Command = Callable[[Jarvis, Reply], Reply]


@dataclass(frozen=True, slots=True)
class Response:
    """A ready-to-send HTTP response, decided without touching a socket."""

    status: int
    content_type: str
    body: bytes


def snapshot(jarvis: Jarvis) -> Reply:
    """A JSON-ready snapshot of everything Jarvis currently holds (Vision §21, §30).

    Every field traces to real state via :meth:`Jarvis.state_summary` and the energy
    surface; a fresh Jarvis produces an all-empty snapshot with zero energy. This is
    the live model the control center renders after every turn.
    """
    summary = jarvis.state_summary()
    return {
        "episodes": summary.episode_count,
        "energy": {
            "spent": jarvis.energy_spent(),
            "remaining": jarvis.energy_remaining(),
            "conserving": jarvis.is_conserving(),
        },
        "self": [{"statement": s, "confidence": c} for s, c in summary.self_tendencies],
        "companion": [
            {"statement": s, "confidence": c} for s, c in summary.companion_traits
        ],
        "goals": [{"goal": g, "count": n} for g, n in summary.recurring_goals],
        "actions": [
            {"description": a.description, "confidence": a.confidence, "stance": a.stance.name}
            for a in summary.learned_actions
        ],
    }


def _evidence_json(evidence: Evidence) -> Reply:
    """One piece of evidence as the panel renders it — content, provenance, weight."""
    return {
        "content": evidence.content,
        "source": evidence.source.name,
        "weight": evidence.weight.value,
    }


def _provenance(belief: Belief) -> Reply:
    """Why a belief is held: its derived confidence and the evidence for and against
    it (Vision §8, §40) — the grounds the reasoning panel shows, so the surface
    reveals *why*, not just *what*.
    """
    explanation = belief.explain()
    return {
        "statement": explanation.statement,
        "confidence": explanation.confidence.value,
        "supporting": [_evidence_json(e) for e in explanation.supporting],
        "contradicting": [_evidence_json(e) for e in explanation.contradicting],
    }


def _trace_steps(events: tuple[CognitiveEvent, ...]) -> list[Reply]:
    """An episode's cognitive events as ordered, human-readable steps (Vision §26) —
    the chain the panel draws so you can watch the reasoning, not just read the reply.
    """
    steps: list[Reply] = []
    for event in events:
        if isinstance(event, EpisodeStarted):
            steps.append({"step": "started", "detail": event.trigger})
        elif isinstance(event, EvidenceAdded):
            steps.append(
                {"step": "weighed evidence", "detail": "for" if event.supports else "against"}
            )
        elif isinstance(event, BeliefStrengthened):
            steps.append({"step": "belief strengthened", "detail": f"{event.confidence.value:.2f}"})
        elif isinstance(event, BeliefWeakened):
            steps.append({"step": "belief weakened", "detail": f"{event.confidence.value:.2f}"})
        elif isinstance(event, ContradictionDetected):
            steps.append({"step": "contradiction noted", "detail": "a held belief was opposed"})
        elif isinstance(event, EpisodeCompleted):
            steps.append({"step": "concluded", "detail": event.result})
        else:
            steps.append({"step": type(event).__name__, "detail": ""})
    return steps


def _say(jarvis: Jarvis, payload: Reply) -> Reply:
    """Perceive what the companion said and reply with what Jarvis honestly concludes,
    carrying the reasoning behind it (provenance + the episode's step trace).
    """
    text = str(payload.get("text", "")).strip()
    if not text:
        return {"reply": "I'm here — say something and I'll reason about it.", "speak": False}
    episode = jarvis.perceive(text, trigger=text)
    trace = _trace_steps(jarvis.trace_of(episode))
    belief = episode.working_belief
    if belief is not None:
        return {
            "reply": belief.explain().narrate(),
            "speak": True,
            "confidence": belief.confidence.value,
            "provenance": _provenance(belief),
            "trace": trace,
        }
    return {
        "reply": "I don't have enough grounded evidence to form a view on that yet.",
        "speak": True,
        "provenance": None,
        "trace": trace,
    }


def _explain(jarvis: Jarvis, payload: Reply) -> Reply:
    """Explain what Jarvis believes about a topic and *why* (Vision §8) — a stateless
    'why?' over the working belief it already holds, or an honest "no view yet".
    """
    topic = str(payload.get("topic", "")).strip()
    if not topic:
        return {"reply": "Name a topic and I'll explain what I believe about it.", "speak": False}
    belief = jarvis.beliefs.get_by_statement(working_statement(topic))
    if belief is None:
        return {
            "reply": f'I don\'t hold a view on "{topic}" yet.',
            "speak": True,
            "provenance": None,
        }
    return {
        "reply": belief.explain().narrate(),
        "speak": True,
        "confidence": belief.confidence.value,
        "provenance": _provenance(belief),
    }


def _reflect(jarvis: Jarvis, _payload: Reply) -> Reply:
    """Run the whole reflective cycle and report what it produced (Vision §31)."""
    cycle = jarvis.reflect_cycle()
    if cycle.reflection is None:
        return {
            "reply": "I looked across what I know, but nothing yet connects strongly "
            "enough to reflect on.",
            "speak": True,
            "cycle": None,
        }
    parts = [
        f"I notice that '{cycle.reflection.observation}' underlies several of my beliefs."
    ]
    if cycle.hypothesis is not None:
        parts.append(f"I wonder if {cycle.hypothesis}.")
    if cycle.learned is not None:
        parts.append(f"So I've come to believe: {cycle.learned}.")
    return {
        "reply": " ".join(parts),
        "speak": True,
        "cycle": {
            "observation": cycle.reflection.observation,
            "hypothesis": cycle.hypothesis,
            "learned": cycle.learned,
            "produced_insight": cycle.produced_insight,
        },
    }


def _introspect(jarvis: Jarvis, _payload: Reply) -> Reply:
    """A plain-language account of who Jarvis is, from real state (Vision §29, §30)."""
    return {"reply": jarvis.introspect(), "speak": True}


def _wonder(jarvis: Jarvis, _payload: Reply) -> Reply:
    """Let Jarvis follow its own curiosity, if anything is pulling at it (Vision §16)."""
    impulse = jarvis.feel_curious()
    if impulse is None:
        return {"reply": "Nothing is pulling at my curiosity right now.", "speak": True}
    jarvis.pursue(impulse)
    return {"reply": f"I find myself wondering: {impulse.trigger}", "speak": True}


def _rest(jarvis: Jarvis, _payload: Reply) -> Reply:
    """Restore energy to full (Vision §15) — fatigue, not a hard cap."""
    jarvis.rest()
    return {"reply": "I've rested; my energy is restored.", "speak": False}


def _energy_budget(jarvis: Jarvis, payload: Reply) -> Reply:
    """Tune how hard Jarvis is willing to think, at runtime (Vision §15, §40)."""
    raw = payload.get("budget")
    if raw is None or raw == "":
        jarvis.set_energy_budget(None)
        return {"reply": "Energy budget cleared — I'll think freely.", "speak": False}
    budget = int(raw) if isinstance(raw, int | float | str) else 0
    jarvis.set_energy_budget(budget)
    return {"reply": f"Energy budget set to {budget}.", "speak": False}


def _state(_jarvis: Jarvis, _payload: Reply) -> Reply:
    """Just the live snapshot (added by :func:`handle`); no side effects."""
    return {}


_COMMANDS: dict[str, Command] = {
    "say": _say,
    "explain": _explain,
    "reflect": _reflect,
    "introspect": _introspect,
    "wonder": _wonder,
    "rest": _rest,
    "energy_budget": _energy_budget,
    "state": _state,
}


def handle(jarvis: Jarvis, command: str, payload: Reply) -> Reply:
    """Run one command against ``jarvis`` and return a JSON-ready reply + live state.

    An unknown command is a clear error, never a silent no-op. Every reply carries a
    fresh :func:`snapshot`, so a single round-trip updates the whole control center.
    """
    run = _COMMANDS.get(command)
    if run is None:
        return {"error": f"unknown command: {command}", "state": snapshot(jarvis)}
    result = run(jarvis, payload)
    result["state"] = snapshot(jarvis)
    return result


def _parse(body: bytes) -> Reply:
    """Best-effort JSON object from a request body; anything else is an empty payload."""
    if not body:
        return {}
    try:
        loaded: object = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return cast("Reply", loaded) if isinstance(loaded, dict) else {}


def _json(payload: Reply) -> bytes:
    return json.dumps(payload).encode("utf-8")


def route(jarvis: Jarvis, method: str, path: str, body: bytes) -> Response:
    """Decide the response for one HTTP request — pure, no socket (Vision §30).

    Serves the console page at ``/``, the live snapshot at ``GET /api/state``, and a
    command at ``POST /api/<command>``. This is the whole HTTP contract, testable
    without binding a port; :mod:`jarvis.interface.server` only moves the bytes.
    """
    clean = path.split("?", 1)[0]
    if method == "GET" and clean in ("/", "/index.html"):
        return Response(200, "text/html; charset=utf-8", _CONSOLE_HTML.read_bytes())
    if clean.startswith("/api/"):
        command = clean[len("/api/") :].strip("/") or "state"
        payload = _parse(body) if method == "POST" else {}
        result = handle(jarvis, command, payload)
        status = 400 if "error" in result else 200
        return Response(status, "application/json; charset=utf-8", _json(result))
    return Response(404, "application/json; charset=utf-8", _json({"error": f"not found: {clean}"}))
