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

import base64
import json
import os
import re
import shutil
import time
import urllib.parse
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import cast

from jarvis.domain.conversation.intent import (
    ConversationIntent,
    classify,
    remembered_content,
)
from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.action_stance import ActionStance
from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.enums.deliberation_value import DeliberationValue
from jarvis.domain.enums.document_owner import DocumentOwner
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.services.capability_scout import catalog
from jarvis.domain.services.model_compare import ModelRun
from jarvis.domain.value_objects.capability import Capability
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.domain.value_objects.research_report import ResearchReport
from jarvis.domain.value_objects.retrieved_document import RetrievedDocument
from jarvis.domain.value_objects.tool_call_result import ToolCallResult
from jarvis.domain.value_objects.tool_spec import ToolSpec
from jarvis.executive.executive_controller import subject_of, working_statement
from jarvis.infrastructure import google_calendar, llm_config_store
from jarvis.infrastructure.env_settings import settings_from_env, speech_perception_from_env
from jarvis.infrastructure.language_model_registry import build_language_model
from jarvis.infrastructure.perceiver_factory import (
    available_providers,
    build_companion_perceiver,
    build_document_editor,
    build_embedder,
    build_perceiver,
    build_reasoner,
    build_renderer,
    describe,
    saved_models,
)
from jarvis.infrastructure.provider_settings import ProviderSettings
from jarvis.infrastructure.response_renderer import uses_spanish
from jarvis.jarvis import Jarvis

_OFFLINE_PERCEIVERS = frozenset({"", "keyword", "scripted", "stub"})

# A short reply that just affirms or denies is read as confirming (or correcting) the
# last thing Jarvis said, so a provisional reasoned answer can mature (Vision §18, §20).
_AFFIRM = frozenset(
    {"sí", "si", "exacto", "correcto", "cierto", "eso", "vale", "claro", "perfecto",
     "yes", "right", "correct", "exactly", "true", "ok", "okay", "yep", "yeah"}
)
_DENY = frozenset(
    {"no", "incorrecto", "falso", "nope", "wrong", "incorrect", "false", "nah"}
)
# Light connectors/politeness allowed inside a *bare* yes/no ("no, gracias"; "sí, exacto"),
# so a real sentence that merely starts with "no" ("no funcionas bien") is NOT a correction.
_CONFIRMATION_FILLER = frozenset(
    {"y", "pero", "pues", "bueno", "gracias", "por", "favor", "totalmente",
     "the", "that", "please", "thanks", "really", "not"}
)
_MAX_CONFIRMATION_WORDS = 5
_WORD = re.compile(r"\w+")

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


def _provider_stats(jarvis: Jarvis) -> dict[str, object]:
    """Live-provider instrumentation (Phase 4): counts, time, tokens.

    A read-only, deterministic view of the shared collector: how many observable
    live calls, honest successes, wall-clock totals and consumed tokens. Zero when
    no live edge has ever run (offline Jarvis stays all-zero, not surprising).
    """
    stats = jarvis.provider_stats()
    return {
        "calls": stats.calls,
        "successes": stats.successes,
        "failures": stats.failures,
        "success_rate": round(stats.success_rate, 4),
        "chat_calls": stats.chat_calls,
        "agent_calls": stats.agent_calls,
        "total_seconds": round(stats.total_seconds, 4),
        "avg_seconds": round(stats.total_seconds / stats.calls, 4) if stats.calls else 0.0,
        "slowest_seconds": round(stats.slowest_seconds, 4),
        "tokens": stats.usage.total_tokens,
    }


def snapshot(jarvis: Jarvis) -> Reply:
    """A JSON-ready snapshot of everything Jarvis currently holds (Vision §21, §30).

    Every field traces to real state via :meth:`Jarvis.state_summary` and the energy
    surface; a fresh Jarvis produces an all-empty snapshot with zero energy. This is
    the live model the control center renders after every turn.
    """
    summary = jarvis.state_summary()
    return {
        "episodes": summary.episode_count,
        "perceiver": {
            **describe(jarvis.perception),
            "available": list(available_providers()),
            "models": saved_models(),  # per-provider remembered model, for UI auto-fill
        },
        "energy": {
            "spent": jarvis.energy_spent(),
            "remaining": jarvis.energy_remaining(),
            "conserving": jarvis.is_conserving(),
            "deliberation_value": jarvis.deliberation_value().value,
        },
        "provider": _provider_stats(jarvis),
        "speech": _speech_block(jarvis),
        "tunables": {
            "grounded_confidence": jarvis.knobs().grounded_confidence,
            "insight_confidence": jarvis.knobs().insight_confidence,
            "max_goal_reflections": jarvis.knobs().max_goal_reflections,
        },
        "self": [{"statement": s, "confidence": c} for s, c in summary.self_tendencies],
        "companion": [
            {"statement": s, "confidence": c} for s, c in summary.companion_traits
        ],
        "companion_name": _companion_name(jarvis),
        "goals": [{"goal": g, "count": n} for g, n in summary.recurring_goals],
        "actions": [
            {"description": a.description, "confidence": a.confidence, "stance": a.stance.name}
            for a in summary.learned_actions
        ],
        "capabilities": _capability_catalog(jarvis, summary),
        "needs": [
            {"statement": s, "confidence": c} for s, c in summary.capability_needs
        ],
        "ready": list(jarvis.usable_capabilities()),
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "requires_approval": spec.requires_approval,
                "permission": spec.permission.name,
                "args": dict(spec.args),
                "origin": jarvis.tool_origin(spec.name),
            }
            for spec in jarvis.tool_channels()
        ],
        "documents": _document_names(jarvis),
        "reasoning": [
            {
                "trigger": thread.trigger,
                "proposal": thread.statement,
                "posture": thread.posture.name,
            }
            for thread in jarvis.reasoning_span()
        ],
        "activity": _recent_activity(jarvis),
        "providers": _providers_block(jarvis),
        "agents": _agents_block(jarvis),
        "environment": _environment_block(),
        "calendar_events": _upcoming_events(jarvis),
        "calendar": _calendar_block(jarvis),
        "upcoming_tasks": _upcoming_tasks(jarvis),
        "notes": _notes_block(jarvis),
        "mail": _mail_block(jarvis),
        "recall": _recall_block(jarvis),
        "workflows": _workflows_block(jarvis),
        "memory": _memory_block(jarvis, summary),
    }


def _speech_block(jarvis: Jarvis) -> Reply:
    """The ear the console hears through, as a self-describing snapshot block.

    ``live`` is a promise, not a guess: an ear that turns raw audio into real text
    (a Whisper backer) reports ``can_hear_audio``; the browser's echo pass-through
    cannot, so it reports ``live: False`` and the console keeps its in-browser Web
    Speech path. ``endpoint`` is where a live console records audio to.
    """
    source = jarvis.speech_perception
    if source is None:
        return {
            "provider": None,
            "model": None,
            "live": False,
            "endpoint": "/api/speech/transcribe",
        }
    return {
        "provider": source.provider,
        "model": source.model,
        "live": source.can_hear_audio,
        "endpoint": "/api/speech/transcribe",
    }


def _document_names(jarvis: Jarvis, limit: int = 200) -> list[str]:
    """The names of every document Jarvis keeps, or ``[]`` when offline.

    The surface renders the list so the companion can see, open, and re-read the
    files shared so far. A wired store lists them; offline means no file edge, so
    the empty list is honest (D8).
    """
    store = jarvis.documents_store
    if store is None:
        return []
    return list(store.list_documents())[:limit]


def _recent_activity(jarvis: Jarvis, limit: int = 6) -> list[Reply]:
    """The tail of episodic memory, newest first, for the intelligence feed.

    A *memory*, never a belief: these are the recorded episode headers (trigger,
    outcome, when), so the dashboard narrates what happened without asserting it.
    Defensive: a store half-wired offline simply yields an empty feed.
    """
    try:
        history = list(jarvis.episodes.history())[-limit:]
    except Exception:  # noqa: BLE001 - the store boundary
        return []
    history.reverse()
    return [
        {
            "trigger": record.trigger,
            "outcome": record.outcome.name,
            "recorded_at": record.recorded_at.isoformat(),
        }
        for record in history
    ]


def _providers_block(jarvis: Jarvis) -> Reply:
    """The provider landscape the LLM panel renders: active + selectable + live stats.

    ``active`` is the perceiver currently in the loop; ``available`` is every
    provider the surface can switch to; ``stats`` mirrors the live instrumentation
    block. All from existing seams -- nothing asserted here.
    """
    perception = describe(jarvis.perception)
    kind = perception.get("kind") or ""
    active = perception.get("provider") or perception.get("model") or kind
    return {
        "active": active,
        "model": perception.get("model"),
        "kind": kind,
        "available": list(available_providers()),
        "stats": _provider_stats(jarvis),
    }


def _agent_reason(
    *,
    active: bool,
    seam_present: bool | None,
    capability: str | None,
    held: dict[str, CapabilityStatus],
    hint: str,
) -> str:
    """Why an edge reads standby, derived from the seam — never hard-coded.

    ``active`` means acquired + live-backed (``can_do``). Otherwise the reason
    names the actionable prerequisite: a missing seam names its ``JARVIS_*``
    env var; a present seam without an acquired capability points at
    ``capability scout/acquire``; an acquired-but-unusable seam reports a
    disconnected provider. ``seam_present=None`` means no public seam to
    inspect (reasoner/recall), so the reason derives from held/ready only.
    """
    if active:
        return "activo y respaldado por un proveedor vivo"
    if seam_present is False:
        return f"en espera — necesita {hint}"
    if capability is None:
        return f"en espera — necesita {hint}"
    if capability not in held:
        if seam_present is True:
            return "borde presente pero capacidad sin adquirir — usa capability scout/acquire"
        return f"en espera — necesita {hint} y adquirir la capacidad"
    if held[capability] is not CapabilityStatus.ACQUIRED:
        return "capacidad sin adquirir — usa capability acquire (solo sugerencia)"
    return "proveedor no conectado"


def _agents_block(jarvis: Jarvis) -> list[Reply]:
    """The real edge agents Jarvis runs on, honestly labelled (one per seam).

    ``active`` derives from ``can_do`` -- an acquired capability with a live backing
    provider in this composition; a seam that is absent or present-but-unusable reads
    standby. Every edge also carries a derived ``reason`` naming the actionable
    prerequisite (the ``JARVIS_*`` env var, the capability acquisition, or the
    provider), so "En espera" always has an honest, checkable why. A fresh offline
    Jarvis reports every edge as standby: nothing pretended.
    This is the *control plane* (the wired seams), not the capability *catalog*.
    """
    perception = describe(jarvis.perception)
    ready = set(jarvis.usable_capabilities())
    held = {
        cap.name: cap.status for cap in jarvis.capabilities()
    }
    kind = perception.get("kind") or "keyword"
    perceiving = kind not in _OFFLINE_PERCEIVERS
    edges: list[Reply] = [
        {
            "label": "Percepción",
            "capability": None,
            "description": "Lee el mundo y lo que dices",
            "active": perceiving,
            "reason": (
                "activo y respaldado por un proveedor vivo"
                if perceiving
                else "en espera — necesita JARVIS_LLM_* (proveedor y modelo)"
            ),
        }
    ]
    # (label, capability, description, seam-present, env hint). seam-present comes
    # from the public seam accessor; None means no public seam (reason derived
    # from held/ready only). The Ejecutor has no catalog capability: its seam IS
    # the instruction agent (JARVIS_AGENT_ROOT), so capability is None.
    speech = jarvis.speech_perception
    seams: list[tuple[str, str | None, str, bool | None, str]] = [
        ("Razonador", "reason with a language model",
         "Razona provisionalmente y propone respuestas", None, "JARVIS_LLM_*"),
        ("Memoria", "recall by meaning", "Recuerda por significado con el retriever",
         None, "JARVIS_EMBED_*"),
        ("Web", "search the web", "Busca y lee páginas externas",
         jarvis.external_source is not None,
         "JARVIS_LLM_* (backend de búsqueda) o JINA_API_KEY"),
        ("Investigación", "deep research", "Investiga en profundidad en el borde",
         jarvis.research_source is not None, "SEARXNG_INSTANCE"),
        ("Comparador", "compare language models", "Compara modelos a ciegas",
         jarvis.model_compare is not None, "JARVIS_COMPARE_MODELS"),
        ("Correo", "send and read email", "Lee y envía correo en el borde",
         jarvis.mail_source is not None,
         "MAIL_IMAP_HOST + MAIL_EMAIL + MAIL_PASSWORD"),
        ("Delegación", "delegate to an agent", "Delega tareas ya decididas",
         jarvis.task_agent is not None, "JARVIS_AGENT_ROOT"),
        ("Ejecutor", None, "Ejecuta instrucciones materiales (agency)",
         jarvis.instruction_agent is not None, "JARVIS_AGENT_ROOT"),
        ("OpenBot", "execute on computer", "Ejecuta en un entorno de computación gobernado",
         jarvis.openbot_agent is not None, "JARVIS_OPENBOT_ENDPOINT"),
        ("Notas", "manage notes", "Notas locales",
         jarvis.notes_store is not None, "JARVIS_NOTES_ROOT"),
        ("Calendario", "manage calendar", "Agenda y eventos",
         jarvis.calendar_store is not None,
         "JARVIS_CALENDAR_ROOT o Google OAuth"),
        ("Tareas", "manage tasks", "Tareas planificadas",
         jarvis.task_scheduler is not None, "JARVIS_TASKS_ROOT"),
        ("Documentos", "work with files", "Archivos compartidos",
         jarvis.documents_store is not None, "JARVIS_HOME/docs"),
        ("Voz", "perceive speech", "Oye y transcribe audio",
         speech is not None, "JARVIS_STT_*"),
    ]
    for label, capability, description, seam_present, hint in seams:
        active = bool(seam_present) if capability is None else capability in ready
        edges.append(
            {
                "label": label,
                "capability": capability,
                "description": description,
                "active": active,
                "reason": _agent_reason(
                    active=active,
                    seam_present=seam_present,
                    capability=capability,
                    held=held,
                    hint=hint,
                ),
            }
        )
    edges.sort(key=lambda edge: (not bool(edge.get("active")), str(edge.get("label"))))
    return edges


# Sampled host metrics (System Monitor): the process CPU share since the last call,
# a lazy estimate that converges, never a fake number. Reset by the server per boot.
_ENV_CPU: dict[str, float | None] = {"at": None, "cpu": None}


def _process_cpu_percent() -> float | None:
    """The command-center process's CPU share in %, or None on the first call."""
    now = time.monotonic()
    cpu = time.process_time()
    last_at = _ENV_CPU["at"]
    last_cpu = _ENV_CPU["cpu"]
    _ENV_CPU["at"] = now
    _ENV_CPU["cpu"] = cpu
    if last_at is None or last_cpu is None or now <= last_at:
        return None
    dt = now - last_at
    delta = cpu - last_cpu
    if dt <= 0 or delta < 0:
        return None
    return round(min(100 * delta / dt, 100.0), 1)


def _host_ram_percent() -> float | None:
    """Host-wide RAM in use (%), via stdlib only; None when the OS won't say."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class _MemStatus(ctypes.Structure):  # noqa: N801 - mirror the Win32 struct
                _fields_ = [
                    ("Length", wintypes.DWORD),
                    ("MemoryLoad", wintypes.DWORD),
                    ("TotalPhys", ctypes.c_ulonglong),
                    ("AvailPhys", ctypes.c_ulonglong),
                    ("TotalPageFile", ctypes.c_ulonglong),
                    ("AvailPageFile", ctypes.c_ulonglong),
                    ("TotalVirtual", ctypes.c_ulonglong),
                    ("AvailVirtual", ctypes.c_ulonglong),
                    ("AvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = _MemStatus()
            status.Length = ctypes.sizeof(_MemStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return float(status.MemoryLoad)
        except (AttributeError, OSError):
            return None
    return None


def _environment_block() -> Reply:
    """The real host the command center runs on: CPU/RAM/Disk of THIS machine.

    Every figure is measured here, not scripted: process CPU share, host RAM (when
    the OS reports it), and the working drive's disk usage. ``None`` reads as
    "n/d" in the UI -- honest when the host won't answer.
    """
    disk = None
    try:
        usage = shutil.disk_usage(os.getcwd())
        disk = round(min(100.0 * usage.used / usage.total, 100.0), 1)
    except OSError:
        disk = None
    return {
        "cpu": _process_cpu_percent(),
        "ram": _host_ram_percent(),
        "disk": disk,
        "cores": os.cpu_count(),
        "platform": os.name,
    }


def _upcoming_events(jarvis: Jarvis, limit: int = 4) -> list[Reply]:
    """The next handful of calendar events, newest-first, for the mission timeline.

    Offline (no store, not earned) honestly reads as an empty timeline.
    """
    store = jarvis.calendar_store
    if store is None:
        return []
    try:
        events = list(store.list_events(limit=limit))
    except Exception:  # noqa: BLE001 - the store boundary
        return []
    return [
        {"title": event.title, "start": event.start.isoformat(), "id": event.id}
        for event in events
    ]


def _upcoming_tasks(jarvis: Jarvis, limit: int = 4) -> list[Reply]:
    """The next handful of scheduled tasks (enabled ones first) for the timeline.

    Offline reads as an empty list, truthfully.
    """
    scheduler = jarvis.task_scheduler
    if scheduler is None:
        return []
    try:
        tasks = list(scheduler.list_tasks(limit=limit))
    except Exception:  # noqa: BLE001 - the store boundary
        return []
    return [
        {
            "name": task.name,
            "enabled": task.enabled,
            "next_run": task.next_run.isoformat() if task.next_run else None,
            "id": task.id,
            "last_run": task.last_run.isoformat() if task.last_run else None,
            "last_status": task.last_status,
            "last_output": task.last_output[:200] if task.last_output else "",
        }
        for task in tasks
    ]


def _calendar_block(jarvis: Jarvis) -> Reply:
    """Which calendar backs the agenda: google, local, or none (F6).

    ``source`` derives from the wired store's kind (a Google store vs any
    other store vs no store); ``connected`` is whether events can be read
    right now. The surface uses it for the connect/disconnect affordance.
    """
    store = jarvis.calendar_store
    if store is None:
        return {"source": "none", "connected": False}
    if isinstance(store, google_calendar.GoogleCalendarStore):
        return {"source": "google", "connected": True}
    return {"source": "local", "connected": True}


def _notes_block(jarvis: Jarvis, limit: int = 5) -> Reply:
    """How many notes Jarvis keeps plus the latest handful (cheap, local).

    The surface lists them and opens the Notes panel; searching/reading go
    through the ``notes`` command.
    """
    store = jarvis.notes_store
    if store is None:
        return {"total": 0, "recent": []}
    try:
        kept = list(store.list_notes(limit=200))
    except Exception:  # noqa: BLE001 - the store boundary
        return {"total": 0, "recent": []}
    return {
        "total": len(kept),
        "recent": [{"id": note.id, "title": note.title} for note in kept[:limit]],
    }


def _mail_block(jarvis: Jarvis) -> Reply:
    """Whether a mailbox is wired -- never a network read in the snapshot.

    Listing or reading mail always hits the mailbox, so the snapshot only
    reports ``configured``; the Mail panel fetches on demand.
    """
    return {"configured": jarvis.mail_source is not None}


def _recall_block(jarvis: Jarvis) -> Reply:
    """How recall works right now: by meaning or by surface tokens (F9).

    ``meaning`` is live only when the embedding edge is wired and earned
    (``can_do``); otherwise recall stays lexical. No scores here -- candidates
    surface through the ``recall`` command.
    """
    mode = "meaning" if jarvis.can_do("recall by meaning") else "lexical"
    return {"mode": mode}


def _episode_series(jarvis: Jarvis, limit: int = 24) -> list[str]:
    """The last episodes' timestamps, chronological, for the memory chart.

    A plain recorded_at series -- the histogram the browser draws is derived only
    from these real timestamps, never scripted. Offline stores yield an empty list.
    """
    try:
        history = list(jarvis.episodes.history())[-limit:]
    except Exception:  # noqa: BLE001 - the store boundary
        return []
    return [record.recorded_at.isoformat() for record in history]


def _memory_block(jarvis: Jarvis, summary: object) -> Reply:
    """The memory read-model for the insights panel, in one honest block.

    ``episodes`` is the durable episodic count; ``beliefs`` counts the grounded
    conclusions; ``reasoning`` is the live session span size; ``provider`` folds
    the instrumentation surface so the panel can show real tool/call activity
    (zero when no live edge ever ran).
    """
    try:
        beliefs = len(jarvis.beliefs.all_beliefs())
    except Exception:  # noqa: BLE001 - the store boundary
        beliefs = 0
    try:
        reasoning = len(jarvis.reasoning_span())
    except Exception:  # noqa: BLE001 - the store boundary
        reasoning = 0
    return {
        "episodes": getattr(summary, "episode_count", 0),
        "beliefs": beliefs,
        "self_tendencies": len(getattr(summary, "self_tendencies", ())),
        "companion_traits": len(getattr(summary, "companion_traits", ())),
        "reasoning": reasoning,
        "turns": len(jarvis.conversation.recent()),
        "calls": _provider_stats(jarvis)["calls"],
        "provider": _provider_stats(jarvis),
        "goals": len(getattr(summary, "recurring_goals", ())),
        "episode_series": _episode_series(jarvis),
    }


def _capability_catalog(jarvis: Jarvis, summary: object) -> list[Reply]:
    """The full capability landscape: catalog entries merged with real state.

    Odysseus reports *held* capabilities (proposed/acquired) and what is ready; this
    also surfaces the wider catalog of what Jarvis could grow to do, so the surface
    is never blank. Each entry is annotated with a status the UI reads directly:
    ``ready`` (acquired + live provider), ``acquired`` (held but not live now),
    ``proposed``/``rejected``, or ``available`` (catalog-only, not yet grown) --
    plus the evidence-derived ``stance`` (suggest/ask_first/withhold) so the
    surface can suggest without deciding (the stance recommends, never acquires).
    """
    ready_names = set(jarvis.usable_capabilities())
    held = {
        name: status for name, status in getattr(summary, "capabilities", ())
    }
    ready: list[Reply] = []
    for cap in catalog():
        name = cap.name
        if name in ready_names:
            status = "ready"
        elif name in held:
            status = held[name].lower()
        else:
            status = "available"
        ready.append(
            {
                "name": name,
                "description": cap.description,
                "requirement": cap.requirement,
                "status": status,
                "stance": jarvis.capability_stance(name).value,
            }
        )
    return ready


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
        # The natural subject, never the internal "Working conclusion about:" label.
        "statement": subject_of(explanation.statement),
        "confidence": explanation.confidence.value,
        "supporting": [_evidence_json(e) for e in explanation.supporting],
        "contradicting": [_evidence_json(e) for e in explanation.contradicting],
    }


def _confirmation(text: str) -> bool | None:
    """Read a short reply as confirming (True), correcting (False), or neither (None).

    Only a brief affirmation/denial counts, so an ordinary sentence that merely contains
    "no" is not mistaken for a correction.
    """
    tokens = _WORD.findall(text.lower())
    if not tokens or len(tokens) > _MAX_CONFIRMATION_WORDS:
        return None
    # Only a *bare* yes/no counts: every word must be an affirmation, a denial, or light
    # filler. A sentence with real content ("no funcionas muy bien") is feedback, not a
    # correction, and must fall through to intent classification.
    allowed = _AFFIRM | _DENY | _CONFIRMATION_FILLER
    if any(token not in allowed for token in tokens):
        return None
    if any(token in _DENY for token in tokens):
        return False
    if any(token in _AFFIRM for token in tokens):
        return True
    return None


def _confirmation_reply(affirm: bool, belief: Belief) -> Reply:
    """Acknowledge that the companion confirmed or corrected the last reasoned answer."""
    confidence = belief.confidence.value
    reply = (
        "Thanks — I'll take that as confirmed and remember it. I hold it more firmly now."
        if affirm
        else "Understood — I'll correct that. I hold it less firmly now."
    )
    return {
        "reply": reply,
        "speak": True,
        "stance": "confirmation",
        "confidence": confidence,
        "provenance": _provenance(belief),
        "trace": [],
    }


def _provider_error(error: Exception) -> str:
    """A clear, actionable message for a language-model failure (Vision §37).

    Surfaces the HTTP status and what it usually means, so a provider misconfiguration
    is self-diagnosing instead of an opaque "HTTPError": 401/403 point at the key or
    an unauthorised model, 404 at a wrong model id (NVIDIA ids look like 'nvidia/…').
    """
    code = getattr(error, "code", None)
    if code == 429:
        return (
            "The language model is rate-limited right now (too many tokens this minute). "
            "Wait a minute and try again, or use a local provider like Ollama."
        )
    if code in (401, 403):
        return (
            f"The provider rejected the request ({code} — authorization failed). The API "
            "key isn't accepted for this model, or the model isn't enabled for your key. "
            "Check the key and model in Tools (get a fresh key from the model's page if "
            "needed), or switch to the keyword perceiver."
        )
    if code == 404:
        return (
            f"The provider returned {code} (not found) for that model — the model id is "
            "almost certainly wrong. Fix it in Tools; NVIDIA ids look like "
            "'nvidia/nemotron-3.5-lightning-30b-a3b', with the 'nvidia/' prefix."
        )
    detail = f"HTTP {code}" if code is not None else type(error).__name__
    return (
        f"I couldn't reach the language model ({detail}). "
        "Check the provider, model, and API key in Tools — or switch to the keyword perceiver."
    )


def _say(jarvis: Jarvis, payload: Reply) -> Reply:
    """Hear what the companion said over both channels (Vision §5, §8): learn about the
    person AND reason about the world, then reply as a companion — not a verdict engine.

    Priority is relational: if the turn taught Jarvis something about *you*, it leads with
    acknowledging that (this is how you "teach" it — it remembers, §5). Otherwise it
    narrates a grounded world-belief, or — when there is nothing to weigh — says so warmly
    and invites more, never scolding "I can't ground a view".
    """
    text = str(payload.get("text", "")).strip()
    if not text:
        return {"reply": "I'm here — tell me something, or ask.", "speak": False}
    try:
        result = _say_core(jarvis, text)
    except Exception as error:  # noqa: BLE001 - the external-provider boundary
        return {"reply": _provider_error(error), "speak": True, "provenance": None, "trace": []}
    # Voice the decided reply in the companion's language (identity offline, Vision §40).
    result["reply"] = jarvis.voice.phrase(str(result["reply"]), like=text)
    return result


def _say_core(jarvis: Jarvis, text: str) -> Reply:
    """Understand the turn, then respond — conversation first, memory only when it fits.

    The pipeline is CONVERSATION → UNDERSTAND INTENT → RESPOND → MEMORY EVALUATION
    (Vision §5, §37): not every message is knowledge. A short yes/no still matures the
    last reasoned answer (the learning loop, §20); otherwise the message's *intent*
    decides. Greetings, small talk, feedback about Jarvis and instructions are answered
    as conversation and never become beliefs; a material directive (an act) is executed
    through the earned-agency executor when one is wired and declined honestly
    otherwise; only an explicit "remember this" or a real
    statement/question reaches perception, memory and reasoning. May raise on a provider
    failure (the caller decides how to surface it).
    """
    jarvis.conversation.record("companion", text)
    # A short "yes"/"no" confirms or corrects the last thing Jarvis reasoned, maturing a
    # provisional answer into a grounded belief (the learning loop, Vision §20) — handled
    # before intent, so the confirmation lands on the previous answer.
    verdict = _confirmation(text)
    history = jarvis.episodes.history()
    if verdict is not None and history:
        belief = jarvis.confirm(history[-1].trigger, affirm=verdict)
        if belief is not None:
            return _turn(jarvis, _confirmation_reply(verdict, belief))

    intent = classify(text)
    if intent is ConversationIntent.GREETING:
        return _turn(jarvis, _greeting_reply(jarvis, text))
    if intent is ConversationIntent.SMALLTALK:
        return _turn(jarvis, _smalltalk_reply(text))
    if intent is ConversationIntent.FEEDBACK:
        return _turn(jarvis, _feedback_reply(text))
    if intent is ConversationIntent.INSTRUCTION:
        return _turn(jarvis, _instruction_reply(jarvis, text))
    if intent is ConversationIntent.ACT:
        return _turn(jarvis, _act_reply(jarvis, text))
    if intent is ConversationIntent.REMEMBER:
        return _turn(jarvis, _remember_reply(jarvis, text))
    return _turn(jarvis, _knowledge_reply(jarvis, text))


def _turn(jarvis: Jarvis, reply: Reply) -> Reply:
    """Record Jarvis's side of the turn in short-term context and return the reply."""
    jarvis.conversation.record("jarvis", str(reply.get("reply", "")))
    return reply


def _plain(reply: str, stance: str) -> Reply:
    """A purely conversational reply: no belief, no memory, no internal metadata."""
    return {"reply": reply, "speak": True, "stance": stance, "provenance": None, "trace": []}


def _greeting_reply(jarvis: Jarvis, text: str) -> Reply:
    name = _companion_name(jarvis)
    if uses_spanish(text):
        opener = f"Hola, {name}" if name else "Hola"
        return _plain(
            f"{opener}. Soy Jarvis, tu compañero. Me alegra verte. ¿Qué tienes en mente?",
            "greeting",
        )
    opener = f"Hi {name}" if name else "Hi"
    return _plain(
        f"{opener} — I'm Jarvis, your companion. Good to see you. What's on your mind?",
        "greeting",
    )


def _smalltalk_reply(text: str) -> Reply:
    if uses_spanish(text):
        return _plain("Bien, aquí estoy. ¿Qué tal tú?", "smalltalk")
    return _plain("I'm here and doing fine — how about you?", "smalltalk")


def _feedback_reply(text: str) -> Reply:
    if uses_spanish(text):
        return _plain(
            "Sí, parece que algo estoy haciendo mal. ¿Qué es lo que más te está fallando?",
            "feedback",
        )
    return _plain(
        "Sounds like I'm getting something wrong. What's failing most for you?", "feedback"
    )


def _instruction_reply(jarvis: Jarvis, text: str) -> Reply:
    """Execute an instruction through an existing capability, or decline honestly.

    A request to check with the configured language model is contextual action, not
    knowledge. The reasoner receives the preceding dialogue so references such as
    "lo" resolve against what the companion and Jarvis were just discussing.
    """
    inference = jarvis.reason(text, conversation=jarvis.conversation.before_current())
    if inference is None:
        unavailable = (
            "Entiendo la instrucción, pero con las capacidades actuales no puedo consultar "
            "otra IA."
            if uses_spanish(text)
            else "I understand the instruction, but I can't consult another AI with the "
            "capabilities currently available."
        )
        return _plain(unavailable, "instruction")
    return _plain(inference.answer, "instruction")


def _act_reply(jarvis: Jarvis, text: str) -> Reply:
    """Perform a *material* instruction through the earned-agency executor, or
    decline honestly when none is wired (Vision §27, §28).

    The companion's words authorize protocol-level acts only: the executor runs a
    sandboxed registry without approval, so locally reversible acts happen and
    external/destructive ones refuse through the gate. Whatever the outcome, the
    reply narrates *what actually happened* -- never a fabricated success.
    """
    if jarvis.instruction_agent is None:
        unavailable = (
            "Entiendo la instrucción, pero ahora mismo no tengo un agente de tareas "
            "configurado para ejecutarla (JARVIS_AGENT_ROOT)."
            if uses_spanish(text)
            else "I understand the instruction, but I have no task agent configured "
            "to execute it right now (JARVIS_AGENT_ROOT)."
        )
        return _plain(unavailable, "act")
    outcome = jarvis.execute(text)
    if outcome.success:
        told = (
            f"Listo — {outcome.summary}."
            if uses_spanish(text)
            else f"Done — {outcome.summary}."
        )
    else:
        told = (
            f"No pude completarlo: {outcome.summary}."
            if uses_spanish(text)
            else f"I couldn't complete it: {outcome.summary}."
        )
    return _plain(told, "act")


def _remember_reply(jarvis: Jarvis, text: str) -> Reply:
    """The one intent that IS memory: store what the companion explicitly asked to keep.

    The fact lands on the relational channel (companion trait) and is ALSO grounded as
    a full cognitive episode (world belief + episode record + trace), so an explicit
    "remember" is durable, shows up in the panel, and gives the yes/no confirmation
    loop an episode to mature (Vision §5, §8, §20).
    """
    fact = remembered_content(text)
    evidence = Evidence(
        content=fact,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(1.0),
        context="the companion explicitly asked to remember this",
    )
    jarvis.observe_companion(fact, evidence)
    jarvis.think(fact, (evidence,), conversation=jarvis.conversation.before_current())
    wording = f"Entendido. Recordaré que {fact}." if uses_spanish(text) else (
        f"Got it — I'll remember that: {fact}."
    )
    reply = _plain(wording, "memory")
    reply["learned"] = [fact]
    return reply


def _knowledge_reply(jarvis: Jarvis, text: str) -> Reply:
    """Answer ordinary conversation without silently converting it into memory.

    Recent dialogue is the primary context. Existing long-term memory may still help,
    but this path writes neither companion traits nor world beliefs; persistence is
    reserved for explicit remember/learn/confirmation actions. Stored documents that
    bear on the turn ride along as honest chips -- the companion sees which of its
    own files Jarvis is drawing from, never a verdict about them.
    """
    recalled = jarvis.recall(text)
    documents = _document_recall(recalled)
    memories = tuple(r for r in recalled if r.kind is not MemoryKind.DOCUMENT)
    inference = jarvis.reason(
        text,
        memory=recalled,
        conversation=jarvis.conversation.before_current(),
    )
    if inference is not None:
        reply = _plain(inference.answer, "conversation")
    elif memories:
        reply = _natural_memory_reply(memories)
    elif documents:
        reply = _document_note(documents)
    else:
        reply = _engage_reply(text, None, [])
    if documents:
        reply["documents"] = [
            {"name": _document_name_from(r), "snippet": r.content} for r in documents
        ]
    return reply


def _document_recall(recalled: tuple[RecalledMemory, ...]) -> tuple[RecalledMemory, ...]:
    """The recalled items that are stored documents, in recall order."""
    return tuple(r for r in recalled if r.kind is MemoryKind.DOCUMENT)


def _document_name_from(memory: RecalledMemory) -> str:
    """The document's name from its provenance (``document: <name>``)."""
    return memory.provenance.removeprefix("document: ") or memory.content


def _document_note(documents: tuple[RecalledMemory, ...]) -> Reply:
    """Honestly surface that Jarvis finds the answer in the companion's own file."""
    first = documents[0]
    name = _document_name_from(first)
    return _plain(
        f"I have a file that bears on that — {name}: \"{first.content}\". "
        "Want me to read it?",
        "conversation",
    )


def _natural_memory_reply(recalled: tuple[RecalledMemory, ...]) -> Reply:
    """Use relevant long-term memory without exposing retrieval mechanics or scores."""
    content = recalled[0].content
    return _plain(f"I remember that {content}. How does that bear on what you mean now?", "memory")


def _engage_reply(text: str, provenance: Reply | None, trace: list[Reply]) -> Reply:
    """Nothing to answer yet — stay in the conversation warmly, never scolding (§37)."""
    if text.strip().endswith("?"):
        reply = "Good question — give me a bit more context and I'll think it through with you."
    else:
        reply = "I'm with you — tell me more and we'll reason it through together."
    return {
        "reply": reply,
        "speak": True,
        "stance": "conversation",
        "provenance": provenance,
        "trace": trace,
    }


def _companion_name(jarvis: Jarvis) -> str | None:
    """The companion's name if Jarvis has learned it, for a warmer greeting (best effort)."""
    for belief in jarvis.companion.beliefs():
        statement = belief.explain().statement.lower()
        for cue in ("name is ", "llama ", "nombre es ", "soy "):
            if cue in statement:
                name = belief.explain().statement.split()[-1].strip(".,!?")
                return name if name.isalpha() else None
    return None


# One streamed event: an event name and its JSON-ready data.
StreamEvent = tuple[str, Reply]


def stream_say(jarvis: Jarvis, payload: Reply) -> Iterator[StreamEvent]:
    """Stream a `say` turn as events: metadata first, then the reply token by token.

    Yields ``("meta", …)`` (provenance, trace, learned, live state) once the reasoning is
    done, then ``("chunk", {"text": …})`` as the voice renders the reply (all at once when
    the model can't stream), then ``("done", {"reply": full})``. A provider failure or
    empty input yields a single ``("done", …)`` with a clear reply — never a broken stream.
    """
    text = str(payload.get("text", "")).strip()
    if not text:
        yield ("done", {"reply": "I'm here — tell me something, or ask.", "speak": False})
        return
    try:
        result = _say_core(jarvis, text)
    except Exception as error:  # noqa: BLE001 - the external-provider boundary
        yield (
            "done",
            {"reply": _provider_error(error), "speak": True, "provenance": None, "trace": []},
        )
        return
    canonical = str(result["reply"])
    meta = {key: value for key, value in result.items() if key != "reply"}
    meta["state"] = snapshot(jarvis)
    yield ("meta", meta)
    voiced: list[str] = []
    for piece in jarvis.voice.phrase_stream(canonical, like=text):
        voiced.append(piece)
        yield ("chunk", {"text": piece})
    yield ("done", {"reply": "".join(voiced)})


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
            "reply": jarvis.voice.phrase(f'I don\'t hold a view on "{topic}" yet.', like=topic),
            "speak": True,
            "provenance": None,
        }
    explanation = belief.explain()
    return {
        "reply": jarvis.voice.phrase(
            explanation.narrate(subject_of(explanation.statement)), like=topic
        ),
        "speak": True,
        "confidence": belief.confidence.value,
        "provenance": _provenance(belief),
    }


# How each action stance reads in the spoken reply (the raw enum value still goes
# to the cycle panel; prose gets a natural phrasing).
_ACTION_PHRASE: dict[ActionStance, str] = {
    ActionStance.SUGGEST: "And I'd suggest an action",
    ActionStance.ASK_FIRST: "And I'd ask before taking an action",
    ActionStance.WITHHOLD: "And I'd hold off on an action",
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
    if cycle.action is not None:
        parts.append(f"{_ACTION_PHRASE[cycle.action.stance]} to check it still holds.")
    return {
        "reply": " ".join(parts),
        "speak": True,
        "cycle": {
            "connections": len(cycle.connections),
            "observation": cycle.reflection.observation,
            "hypothesis": cycle.hypothesis,
            "learned": cycle.learned,
            "produced_insight": cycle.produced_insight,
            "action": cycle.action.stance.value if cycle.action is not None else None,
            "reached_action": cycle.reached_action,
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


def _deliberation(jarvis: Jarvis, payload: Reply) -> Reply:
    """Set how much a deliberation is worth by default (Vision §15, §40).

    ``value`` is ``cheap`` (answer simple problems briefly), ``normal`` (the
    default) or ``high`` (keep the full lifecycle even low on energy). With no
    value the current stance is reported. This only tunes how hard Jarvis thinks
    by default -- a per-call ``value`` still overrides it.
    """
    raw = str(payload.get("value", "")).strip().lower()
    if not raw:
        return {
            "reply": f"Deliberation value is currently '{jarvis.deliberation_value().value}'.",
            "speak": False,
        }
    try:
        value = DeliberationValue(raw)
    except ValueError:
        valid = ", ".join(v.value for v in DeliberationValue)
        message = f"unknown deliberation value '{raw}' — use one of: {valid}."
        return {"error": message, "speak": False}
    jarvis.set_deliberation_value(value)
    return {"reply": f"Deliberation value set to '{value.value}'.", "speak": False}


def _tunables(jarvis: Jarvis, payload: Reply) -> Reply:
    """Report or tune the cognition thresholds at runtime.

    With no fields it just reports the current ``grounded_confidence``,
    ``insight_confidence`` and ``max_goal_reflections``. With any of them it
    builds the updated :class:`CognitiveKnobs` (``dataclasses.replace`` keeps the
    untouched dials) and swaps it via :meth:`Jarvis.set_knobs` -- one value object,
    the single source the executive and Jarvis's own gates read. An out-of-range
    value is a clear error, rejected at the value level (D7), never a crash.
    """
    current = jarvis.knobs()
    fields = {
        "grounded_confidence": current.grounded_confidence,
        "insight_confidence": current.insight_confidence,
        "max_goal_reflections": current.max_goal_reflections,
    }
    unknown = sorted(set(payload) - set(fields))
    if unknown:
        return {"error": f"unknown tune knob: {unknown[0]}", "speak": False}
    changes = {name: payload[name] for name in fields if name in payload}
    if not changes:
        return {"reply": "Cognition thresholds:", "tunables": fields, "speak": False}
    try:
        updated = replace(current, **changes)
    except ValueError as error:
        return {"error": str(error), "speak": False}
    jarvis.set_knobs(updated)
    reported = {name: getattr(updated, name) for name in fields}
    return {
        "reply": "Cognition thresholds updated.",
        "tunables": reported,
        "speak": False,
    }


def _perceiver(jarvis: Jarvis, payload: Reply) -> Reply:
    """Report or switch the live perceiver at runtime (Vision §32, §38; Track B).

    With no ``provider`` it just reports (the live perceiver rides in every snapshot).
    With one, it swaps the evidence *producer* -- the keyword rule, or an LLM provider
    from the open registry -- without rebuilding Jarvis.

    An optional ``api_key`` lets the developer hand over a real credential to start
    testing: it is applied to the live process and saved to ``.env`` (so a restart
    resumes), but it is write-only -- never echoed back in the reply or any snapshot.
    Without a key, the factory reads whatever ``JARVIS_LLM_API_KEY`` already holds. A
    misconfigured provider (e.g. real provider, no model) is a clear error, not a crash.
    """
    provider = str(payload.get("provider", "")).strip()
    if not provider:
        return {"reply": "Name a provider to switch the perceiver.", "speak": False}
    # If no model is typed, recall the one this provider used last (per-provider memory),
    # so switching back to a provider doesn't require retyping its model.
    model = str(payload.get("model", "")).strip() or llm_config_store.resolve_model(
        provider.lower(), os.environ
    )
    base_url = str(payload.get("base_url", "")).strip() or None
    # The API key is write-only from the page: it is applied to the live process and
    # saved to .env, but never echoed back in any reply or snapshot.
    api_key = str(payload.get("api_key", "")).strip()
    is_real = provider.lower() not in _OFFLINE_PERCEIVERS
    if is_real and not model:
        # A real provider needs a model — reject before staging/persisting anything.
        return {"error": f"a model id is required for provider {provider!r} (e.g. llama-3.3-70b)"}
    # Apply the choice to the live process and build from it. The key is only-from-env:
    # `stage` sets any provided key (write-only) plus the non-secret provider/model so a
    # bare model fix (no key) also takes effect immediately.
    staged = llm_config_store.stage(provider, model, base_url, api_key)
    try:
        source = build_perceiver(provider, model, base_url)
    except ValueError as error:
        return {"error": str(error)}
    jarvis.set_perception(source)
    # Switch the relational perceiver to the same provider, so talking to Jarvis both
    # reasons about the world and learns about you through one model (Vision §5).
    jarvis.set_companion_perception(build_companion_perceiver(provider, model, base_url))
    # And voice replies in the companion's language through the same model (Vision §40).
    jarvis.set_voice(build_renderer(provider, model, base_url))
    # And reason provisional answers through the same model, so a novel question gets
    # a hedged answer instead of a refusal when a provider is active (Vision §37).
    jarvis.set_reasoner(build_reasoner(provider, model, base_url))
    # And edit documents through the same model, so "hazle este cambio" to a shared
    # file gets a concrete rewrite proposal to apply (Vision §38).
    jarvis.set_document_editor(build_document_editor(provider, model, base_url))
    # Persist on every switch so the choice (and model fixes) survive a restart; the key
    # line is only written when a key was provided, and is never read back into a reply.
    llm_config_store.persist(staged)
    described = describe(jarvis.perception)
    saved = " Key saved to .env." if api_key else ""
    if described.get("kind") == "keyword":
        return {
            "reply": f"Perceiver set to the keyword rule (no LLM in judgment).{saved}",
            "speak": False,
            "saved": bool(api_key),
        }
    named = described.get("model") or described.get("provider")
    return {
        "reply": f"Perceiver set to {described.get('provider')} ({named}).{saved}",
        "speak": False,
        "saved": bool(api_key),
    }


def _provider_health(jarvis: Jarvis, payload: Reply) -> Reply:
    """Probe one provider with a real minimal call and report what happened.

    Builds that provider's model from the UI choice (key read from the
    environment only, never echoed) and runs one tiny ``complete("ok")``,
    timing it. A success reports the latency; a failure reports the
    self-diagnosing provider error. This is a *probe*, not usage: it is not
    recorded in the instrumentation totals, so ``successes`` still counts only
    real work. Offline rules (keyword/scripted/stub) have no live endpoint to
    verify, which is reported honestly instead of faked.
    """
    _ = jarvis
    provider = str(payload.get("provider", "")).strip()
    if not provider:
        return {"error": "Name a provider to probe."}
    if provider.lower() in _OFFLINE_PERCEIVERS:
        return {
            "ok": True,
            "reply": f"{provider} is an offline rule — nothing live to verify (deterministic).",
            "speak": False,
        }
    model = str(payload.get("model", "")).strip() or llm_config_store.resolve_model(
        provider.lower(), os.environ
    )
    if not model:
        return {"error": f"a model id is required to probe {provider!r}"}
    base_url = str(payload.get("base_url", "")).strip() or None
    try:
        timeout = float(os.environ.get("JARVIS_LLM_TIMEOUT", "30"))
    except ValueError:
        timeout = 30.0
    settings = ProviderSettings(
        provider=provider.lower(),
        model=model,
        base_url=base_url,
        api_key=llm_config_store.resolve_api_key(provider.lower(), os.environ),
        timeout=timeout,
        temperature=0.0,
    )
    try:
        model_adapter = build_language_model(settings)
    except ValueError as error:
        return {"ok": False, "reply": str(error), "speak": False}
    started = time.perf_counter()
    try:
        answer = model_adapter.complete("ok")
    except Exception as error:  # noqa: BLE001 - the external-provider boundary
        return {"ok": False, "reply": _provider_error(error), "speak": False}
    latency = round(time.perf_counter() - started, 3)
    head = answer.strip().replace("\n", " ")[:120]
    return {
        "ok": True,
        "reply": f"{provider} ({model}) answered in {latency}s: {head or '(empty reply)'}",
        "speak": False,
        "latency_seconds": latency,
    }


def _reasoner(jarvis: Jarvis, payload: Reply) -> Reply:
    """Report or switch the reasoner seam at runtime (Vision §37, §38).

    With no ``provider`` it reports whether provisional reasoning is live
    (``can_do``) or silent-offline. With one it swaps only the reasoner --
    perception, voice and companion stay as they are -- so the companion can
    aim provisional answers at a different model. Runtime-only: unlike the
    perceiver switch this is not persisted to ``.env`` (the saved config names
    one shared provider), and a restart resumes the perceiver's model.
    """
    provider = str(payload.get("provider", "")).strip()
    if not provider:
        live = jarvis.can_do("reason with a language model")
        state = "live" if live else "silent (offline)"
        return {"reply": f"The reasoner is currently {state}.", "speak": False, "live": live}
    model = str(payload.get("model", "")).strip() or llm_config_store.resolve_model(
        provider.lower(), os.environ
    )
    base_url = str(payload.get("base_url", "")).strip() or None
    try:
        reasoner = build_reasoner(provider, model, base_url)
    except ValueError as error:
        return {"error": str(error)}
    jarvis.set_reasoner(reasoner)
    live = jarvis.can_do("reason with a language model")
    named = model or provider
    return {
        "reply": f"Reasoner set to {provider} ({named}) — "
        + ("live." if live else "silent (offline)."),
        "speak": False,
        "live": live,
    }


def _provider_reset(jarvis: Jarvis, _payload: Reply) -> Reply:
    """Forget every recorded provider call and count from zero (bookkeeping only)."""
    jarvis.reset_provider_stats()
    return {
        "reply": "Provider stats cleared — counting from zero.",
        "speak": False,
    }


def _embeddings(jarvis: Jarvis, payload: Reply) -> Reply:
    """Report or rewire meaning-based recall from ``JARVIS_EMBED_*`` (F9).

    With no action it reports whether recall runs by meaning or stays lexical.
    ``reload`` re-reads the environment and, when an embedder is configured,
    upgrades recall to it at runtime (lexical stays the fallback); when nothing
    is configured it says so honestly instead of pretending. Runtime-only: a
    restart rebuilds from the environment again.
    """
    action = str(payload.get("action", "")).strip().lower()
    if action and action != "reload":
        return {"reply": "Use embeddings with action 'reload' or none.", "speak": False}
    if not action:
        mode = _recall_block(jarvis)["mode"]
        detail = (
            "recall by meaning is live"
            if mode == "meaning"
            else "recall is lexical (set JARVIS_EMBED_MODEL, then reload)"
        )
        return {"reply": f"Recall mode: {mode} — {detail}.", "speak": False, "mode": mode}
    embedder = build_embedder()
    if embedder is None:
        return {
            "reply": "No embedder configured (JARVIS_EMBED_MODEL is empty) — recall stays lexical.",
            "speak": False,
        }
    jarvis.enable_embedding_recall(embedder)
    live = jarvis.can_do("recall by meaning")
    if live:
        return {"reply": "Recall upgraded to meaning-based.", "speak": False}
    return {
        "reply": "Embedder wired but the capability is not earned yet — "
        "recall stays lexical until acquired.",
        "speak": False,
    }


def _speech(jarvis: Jarvis, payload: Reply) -> Reply:
    """Report or rewire the ear from ``JARVIS_STT_*`` (F9).

    With no action it reports which ear hears (a live transcriber or the
    browser echo) and which model it claims. ``reload`` re-reads the
    environment and swaps the ear at runtime; secrets stay in ``.env``
    (this command never takes or echoes a key). Runtime-only.
    """
    action = str(payload.get("action", "")).strip().lower()
    if action and action != "reload":
        return {"reply": "Use speech with action 'reload' or none.", "speak": False}
    if not action:
        return {"reply": _speech_status(jarvis), "speak": False, **_speech_block(jarvis)}
    try:
        jarvis.set_speech_perception(speech_perception_from_env())
    except ValueError as error:
        return {"reply": f"Couldn't rewire the ear: {error}", "speak": False}
    return {"reply": _speech_status(jarvis), "speak": False, **_speech_block(jarvis)}


def _speech_status(jarvis: Jarvis) -> str:
    """One honest line about which ear hears right now."""
    source = jarvis.speech_perception
    if source is None:
        return "No ear wired — voice input is off."
    if source.can_hear_audio:
        model = f" ({source.model})" if source.model else ""
        return f"Live ear: {source.provider or 'server'}{model} — the mic records to it."
    return "Browser ear (Web Speech) — transcription happens in the page."


def _learn(jarvis: Jarvis, payload: Reply) -> Reply:
    """Teach Jarvis about the companion from a pasted profile/notes (Vision §5, §38).

    The deliberate way to "train" Jarvis on who you are: the whole text is read through
    the relational channel in ONE pass (cheap, and it respects a provider's per-minute
    limits) into the companion model as ordinary, revisable beliefs. Needs an LLM
    perceiver — the keyword rule can't read prose into traits. A provider failure is
    surfaced, not a crash.
    """
    text = str(payload.get("text", "")).strip()
    if not text:
        return {"reply": "Paste something about yourself and I'll learn it.", "speak": False}
    try:
        learned = jarvis.note_companion(text)
    except Exception as error:  # noqa: BLE001 - the external-provider boundary
        return {"reply": _provider_error(error), "speak": False}
    traits = [belief.explain().statement for belief in learned]
    if not traits:
        reply = (
            "I read that, but extracted nothing about you — make sure an LLM perceiver "
            "is active in Tools (the keyword rule can't read prose)."
        )
    else:
        reply = f"Learned {len(traits)} things about you. You can see them under Companion."
    return {"reply": reply, "speak": False, "learned": traits}


def _greeting_prompt(facts: list[str], goals: list[str]) -> str:
    """The prompt that voices a warm opening from what Jarvis remembers (memory is
    Jarvis's; the model only phrases it).
    """
    known = "; ".join(facts[:15]) if facts else "nothing yet"
    ongoing = "; ".join(goals[:5]) if goals else "none noted"
    return (
        "You are Jarvis, greeting your companion at the start of a session. "
        f"What you remember about them: {known}. Ongoing goals/projects: {ongoing}. "
        "Write ONE short, warm, natural greeting (at most two sentences). Address them "
        "by name if you know it. If a current project is evident, offer to continue it. "
        "Reply in the language the person appears to use. Output ONLY the greeting."
    )


def _greeting(jarvis: Jarvis, _payload: Reply) -> Reply:
    """A warm opening, grounded in what Jarvis remembers about the companion (Vision §5).

    When an LLM is active it phrases a personalized greeting from the companion model
    (by name, offering to resume a project); otherwise a friendly default. The memory it
    draws on lives in Jarvis, not the model — the model only voices it (§38). Never a
    crash: any failure falls back to the default greeting.
    """
    facts = [belief.explain().statement for belief in jarvis.companion.beliefs()]
    goals = [goal for goal, _ in jarvis.state_summary().recurring_goals]
    if describe(jarvis.perception).get("kind") == "llm":
        try:
            model = build_language_model(settings_from_env())
            spoken = model.complete(_greeting_prompt(facts, goals)).strip()
            if spoken:
                return {"reply": spoken, "speak": False}
        except Exception:  # noqa: BLE001 - a greeting must never break the page
            pass
    if facts:
        reply = "Good to see you again. What are we working on today?"
    else:
        reply = (
            "Hi — I'm Jarvis. Tell me what you're working on, or a bit about yourself, "
            "and I'll remember it and reason it through with you."
        )
    return {"reply": reply, "speak": False}


def _state(_jarvis: Jarvis, _payload: Reply) -> Reply:
    """Just the live snapshot (added by :func:`handle`); no side effects."""
    return {}


# The Internet command (read/search) requires the matching Odysseus capability to
# be *acquired and backed by a provider* -- using it is earned, not automatic.
_EXTERNAL_CAPABILITIES = {
    "read": "read external documents",
    "search": "search the web",
}

_RESEARCH_CAPABILITY = "deep research"
_COMPARE_CAPABILITY = "compare language models"


def _capability_not_ready(jarvis: Jarvis, capability: str) -> Reply:
    """An honest decline when a wired capability is not yet *earned*.

    A capability that is proposed but not acquired reads as "considered but not
    grown" (use `capability acquire`); a capability the scout has not even
    proposed reads as "could gain it" (scout → acquire). Both point forward
    instead of pretending -- acquisition is deliberate and earned (Vision §28).
    """
    known = [c.name for c in jarvis.capabilities()]
    if capability in known:
        prompt = (
            f"I've considered '{capability}' but haven't grown it yet — "
            "use `capability acquire` to accept it."
        )
    else:
        prompt = (
            f"I could gain the '{capability}' capability to do that, but I haven't "
            "proposed or earned it yet — use the `capability` command (scout → acquire)."
        )
    return {"reply": prompt, "speak": False}


def _external_not_ready(jarvis: Jarvis, capability: str) -> Reply:
    """An honest decline when the Internet capability is not usable right now.

    Distinguishes *not wired* (no provider at all -- Jarvis is simply offline)
    from *not earned* (a provider exists but the capability is not yet acquired,
    so using it is a growth the companion has not accepted). When nothing is
    wired, name the exact missing prerequisite (the agent-reach package and, for
    search, JINA_API_KEY) so fixing it is a clear next step, not a mystery.
    """
    if jarvis.external_source is None:
        search_hint = (
            " to search I need a web-search backend (point JARVIS_LLM_* at an "
            "OmniRoute gateway, or set JINA_API_KEY in .env\n"
            "   then 'capability scout'"
        )
        return {
            "reply": (
                "No Internet capability is wired up right now — I can still think "
                "and remember, I just can't fetch from the web. To enable it:\n"
                f"   install the agent-reach package and restart (and {search_hint}"
                "then 'capability acquire'. I can offer these as a growth you accept.)"
            ),
            "speak": False,
        }
    return _capability_not_ready(jarvis, capability)


def _external(jarvis: Jarvis, payload: Reply) -> Reply:
    """Use the Internet capability: read, search, or report channels (Vision §38).

    Jarvis never reaches the Internet on its own for every message -- this command is
    the *deliberate* gate a surface (or an explicit outer decision layer) uses when
    updated/outside information is actually needed. Results carry provenance back to
    Jarvis; it does not write them to memory here. Offline/absent capability or a
    fetch failure is a clear message, never a crash.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {"reply": "Use external with action 'read', 'search' or 'channels'.", "speak": False}
    if action in ("read", "search") and not jarvis.can_do(_EXTERNAL_CAPABILITIES[action]):
        return _external_not_ready(jarvis, _EXTERNAL_CAPABILITIES[action])
    try:
        if action == "channels":
            channels = jarvis.internet_channels()
            if not channels:
                return {
                    "reply": "No Internet capability is wired up right now.",
                    "speak": False,
                }
            lines = [
                f"{c.name}: {c.status}"
                + (f" ({c.active_backend})" if c.active_backend else "")
                for c in channels
            ]
            return {"reply": "External channels:\n" + "\n".join(lines), "speak": False}
        if action == "read":
            url = str(payload.get("url", "")).strip()
            if not url:
                return {"reply": "Provide a url to read.", "speak": False}
            doc = jarvis.read_external(url)
            return {
                "reply": _external_reply(doc),
                "speak": False,
                "source": doc.source,
                "url": doc.url,
            }
        if action == "search":
            query = str(payload.get("query", "")).strip()
            if not query:
                return {"reply": "Provide a query to search.", "speak": False}
            limit_raw = payload.get("limit", 5)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 5
            docs = jarvis.search_external(query, limit=limit)
            return {
                "reply": _external_search_reply(docs),
                "speak": False,
                "count": len(docs),
            }
    except Exception as error:  # noqa: BLE001 - the external-provider boundary
        return {"reply": _external_error(error), "speak": False}
    return {"reply": "Unknown external action.", "speak": False}


def _research(jarvis: Jarvis, payload: Reply) -> Reply:
    """Investigate a question in depth through the research capability (Vision §38).

    Like ``external``, this is a *deliberate* gate: a surface asks for in-depth
    research when outside knowledge is actually needed. The reply is the source's
    plain-language summary plus each cited document's provenance, so the surface
    (and Jarvis) can reason over *what was found* rather than a verdict.
    """
    query = str(payload.get("query", "")).strip()
    if not query:
        return {"reply": "Provide a query to research.", "speak": False}
    if jarvis.research_source is None:
        return {
            "reply": "No research capability is wired up right now — I can still "
            "think and remember, I just can't go look in depth anywhere "
            "(SEARXNG_INSTANCE isn't configured).",
            "speak": False,
        }
    if not jarvis.can_do(_RESEARCH_CAPABILITY):
        return _capability_not_ready(jarvis, _RESEARCH_CAPABILITY)
    try:
        depth_raw = payload.get("depth", 1)
        try:
            depth = int(depth_raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            depth = 1
        report = jarvis.deep_research(query, depth=depth)
        return {
            "reply": _research_reply(report),
            "speak": False,
            "count": len(report.documents),
        }
    except Exception as error:  # noqa: BLE001 - the research-provider boundary
        return {"reply": _research_error(error), "speak": False}


def _research_reply(report: ResearchReport) -> str:
    """A readable summary of a research report, keeping the documents' provenance."""
    lines = [report.summary]
    for i, doc in enumerate(report.documents, 1):
        head = doc.content.strip().replace("\n", " ")
        if len(head) > 200:
            head = head[:200].rstrip() + "…"
        title = f" — {doc.title}" if doc.title else ""
        lines.append(f"{i}. [{doc.source}]{title}\n   {doc.url or '(no url)'}\n   {head}")
    return "\n".join(lines)


def _research_error(error: Exception) -> str:
    """A clear message for a research-capability failure (never a crash)."""
    detail = type(error).__name__
    return (
        f"I couldn't complete that research ({detail}). "
        "It might be a network issue or an unreachable SearXNG instance. "
        "My reasoning and memory are unaffected."
    )


def _compare(jarvis: Jarvis, payload: Reply) -> Reply:
    """Ask several language models the same question and gather their replies blind.

    Like ``external`` and ``research``, this is a *deliberate* gate: a surface calls
    it when it actually wants a model cross-check (Vision §33). The reply names each
    model and shows its text verbatim -- it is candidate evidence for the surface to
    reason over, never a verdict the adapter picked.
    """
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        return {"reply": "Provide a prompt to compare.", "speak": False}
    if jarvis.model_compare is None:
        return {
            "reply": "No model comparison is wired up right now — I can't ask "
            "several models the same question (no comparator configured).",
            "speak": False,
        }
    if not jarvis.can_do(_COMPARE_CAPABILITY):
        return _capability_not_ready(jarvis, _COMPARE_CAPABILITY)
    try:
        selected = payload.get("models")
        models = None
        if isinstance(selected, list):
            raw = cast("list[object]", selected)
            clean = [str(m).strip() for m in raw if str(m).strip()]
            models = clean or None
        runs = jarvis.compare_models(prompt, models=models)
        return {
            "reply": _compare_reply(runs),
            "speak": False,
            "count": len(runs),
        }
    except Exception as error:  # noqa: BLE001 - the model-provider boundary
        return {"reply": _compare_error(error), "speak": False}


def _compare_reply(runs: tuple[ModelRun, ...]) -> str:
    """Each model's reply, labelled by model -- raw candidate evidence, no verdict."""
    if not runs:
        return "No models to compare."
    lines: list[str] = []
    for run in runs:
        text = run.response.strip() or "(empty reply)"
        lines.append(f"{run.model}:\n{text}")
    return "\n\n".join(lines)


def _compare_error(error: Exception) -> str:
    """A clear message for a model-comparison failure (never a crash)."""
    detail = type(error).__name__
    return (
        f"I couldn't complete that comparison ({detail}). "
        "One of the models may be unreachable or misconfigured. "
        "My reasoning and memory are unaffected."
    )


def _external_error(error: Exception) -> str:
    """A clear message for an Internet-capability failure (never a crash).

    Kept apart from the LLM failure phrasing: an external fetch/search can fail
    because no capability is wired, no search provider is configured, a URL is
    unreachable/blocked, or the network is down -- and none of those should read as
    a broken *language model*.
    """
    code = getattr(error, "code", None)
    detail = f"HTTP {code}" if code is not None else type(error).__name__
    return (
        f"I couldn't fetch that from the Internet ({detail}). "
        "It might be a network issue, an unreachable site, or a missing "
        "search/read configuration. My reasoning and memory are unaffected."
    )


def _external_reply(doc: RetrievedDocument) -> str:
    """A short readable summary of one fetched document (provenance plus head)."""
    head = doc.content.strip()
    if len(head) > 400:
        head = head[:400].rstrip() + "…"
    out = f"Source: {doc.source}\nURL: {doc.url or '(n/a)'}"
    if doc.title:
        out += f"\nTitle: {doc.title}"
    return out + f"\n\n{head}"


def _external_search_reply(docs: tuple[RetrievedDocument, ...]) -> str:
    """A readable summary of search results, keeping their provenance."""
    if not docs:
        return "Nothing found for that search."
    parts: list[str] = []
    for i, doc in enumerate(docs, 1):
        head = doc.content.strip().replace("\n", " ")
        if len(head) > 200:
            head = head[:200].rstrip() + "…"
        parts.append(f"{i}. ({doc.source}) {head}")
    return "Search results:\n" + "\n".join(parts)


def _capability(jarvis: Jarvis, payload: Reply) -> Reply:
    """Give Jarvis tools to grow — scout, propose, and acquire capabilities
    (Odysseus, Vision §34, §28).

    Actions: ``scout`` (recognise a need and propose candidates for it),
    ``acquire`` (mark a proposed capability as now-available), ``reject``
    (decline a proposal so it is not re-proposed), ``notice`` (turn recurringly
    unanswered subjects into evidence-grounded needs — the self-initiated half
    of Odysseus), ``list`` (what Jarvis proposes/has), and
    ``recommend``/``stance`` (the evidence-derived stance on acquiring a named
    capability). Acquisition is deliberate and earned; the surface only ever
    *suggests* via the derived stance.
    """
    action = str(payload.get("action", "")).strip().lower()
    name = str(payload.get("name", "")).strip()
    statement = str(payload.get("statement", "")).strip()
    rationale = str(payload.get("rationale", "")).strip()

    if not action:
        capabilities = jarvis.capabilities()
        if not capabilities:
            return {
                "reply": "I have no proposed or acquired capabilities yet — tell me "
                "a capability you think I'd grow from and I'll scout for it.",
                "speak": False,
            }
        lines = [
            f"- {c.name} ({c.status.value}){_ready_marker(jarvis, c.name)}"
            for c in capabilities
        ]
        reply = "Capabilities I know of:\n" + "\n".join(lines)
        recommendations = {c.name: jarvis.capability_stance(c.name).value for c in capabilities}
        return {"reply": reply, "speak": False, "recommendations": recommendations}

    if action == "list":
        capabilities = jarvis.capabilities()
        if not capabilities:
            return {"reply": "No capabilities proposed or acquired yet.", "speak": False}
        lines = [
            f"- {c.name} ({c.status.value}){_ready_marker(jarvis, c.name)}"
            for c in capabilities
        ]
        return {
            "reply": "Capabilities I know of:\n" + "\n".join(lines),
            "speak": False,
            "recommendations": {
                c.name: jarvis.capability_stance(c.name).value for c in capabilities
            },
        }

    if action == "scout":
        if not statement:
            return {
                "reply": "Tell me the capability you'd like (e.g. 'search the web').",
                "speak": False,
            }
        candidates = jarvis.need_capability(statement, rationale or statement)
        if not candidates:
            return {
                "reply": f"I don't yet see a candidate in my toolkit for '{statement}'.",
                "speak": False,
            }
        # Persist the proposals so the companion can later acquire or reject them
        # without re-scouting (repeated needs are recognised, not re-proposed).
        for candidate in candidates:
            jarvis.remember_capability(candidate)
        proposals = [c for c in candidates if c.status is CapabilityStatus.PROPOSED]
        lines = [f"- {c.name}" for c in candidates]
        reply = (
            f"I could grow the ability to '{statement}' by:\n" + "\n".join(lines)
        )
        recommendation = (
            jarvis.capability_stance(proposals[0].name)
            if proposals
            else None
        )
        return {
            "reply": reply,
            "speak": False,
            "capabilities": [
                {"name": c.name, "status": c.status.value} for c in candidates
            ],
            "recommendation": (
                recommendation.value if recommendation is not None else None
            ),
        }

    if action == "recommend":
        if not name:
            return {"reply": "Name a capability to recommend on.", "speak": False}
        recommendation = jarvis.recommend_capability(name)
        return {
            "reply": recommendation.rationale,
            "speak": False,
            "stance": recommendation.stance.value,
            "confidence": recommendation.confidence.value,
        }

    if action == "acquire":
        if not name:
            return {"reply": "Name a capability to acquire.", "speak": False}
        acquired = jarvis.acquire_capability(name)
        if acquired is None:
            return {
                "reply": f"I haven't proposed '{name}' — scout it first.",
                "speak": False,
            }
        return {
            "reply": (
                f"Understood — I now consider '{name}' acquired as a capability."
            ),
            "speak": False,
            "capability": {"name": acquired.name, "status": acquired.status.value},
        }

    if action == "reject":
        if not name:
            return {"reply": "Name a capability to reject.", "speak": False}
        rejected = jarvis.reject_capability(name)
        if rejected is None:
            return {
                "reply": f"I haven't proposed '{name}' — scout it first.",
                "speak": False,
            }
        return {
            "reply": f"Declined — I won't re-propose '{name}'.",
            "speak": False,
            "capability": {"name": rejected.name, "status": rejected.status.value},
        }

    if action == "notice":
        # Auto-initiated growth (Odysseus, Vision §34): detect recurringly
        # unanswered subjects and turn each gap into an evidence-grounded need,
        # scouting what could help. Delegating to the same core path the
        # reflective cycle uses keeps the surface and the autonomous loop aligned.
        proposals = jarvis.auto_scout_gaps()
        if not proposals:
            return {
                "reply": (
                    "I haven't noticed any new subject I keep failing to answer about — "
                    "ask me something and I'll tell you if it becomes a recurring gap."
                ),
                "speak": False,
            }
        lines = [f"- {c.name}" for c in proposals]
        return {
            "reply": (
                "I noticed subjects I keep failing to answer about, and scouted "
                "abilities that could help:\n" + "\n".join(lines)
            ),
            "speak": False,
            "gaps": [
                {"subject": c.name, "candidates": [c.name]} for c in proposals
            ],
        }

    return {"reply": "Unknown capability action.", "speak": False}


def _tool(jarvis: Jarvis, payload: Reply) -> Reply:
    """Exercise Jarvis's acting tools — list or run one (Vision §34, 06_TOOLS_AGENCY).

    ``list`` reports the registered tools (what Jarvis *can* act through); ``run``
    executes one behind the permission gate, so external/destructive tools need an
    explicit ``approved: true`` before anything happens. Nothing here decides
    *whether* to act: the core keeps that deliberate choice; this surface only
    makes an approved act possible and observable.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {"reply": "Use tool with action 'list' or 'run'.", "speak": False}
    if action == "list":
        specs = jarvis.tool_channels()
        if not specs:
            return {"reply": "No tools are registered yet.", "speak": False}
        lines = [_tool_line(spec) for spec in specs]
        return {
            "reply": "Tools I have:\n" + "\n".join(lines),
            "speak": False,
            "count": len(specs),
        }
    if action == "run":
        name = str(payload.get("name", "")).strip()
        if not name:
            return {"reply": "Name a tool to run.", "speak": False}
        raw = payload.get("arguments")
        arguments: dict[str, str] | None = None
        if isinstance(raw, dict):
            items = cast("dict[object, object]", raw)
            arguments = {str(k): str(v) for k, v in items.items()}
        approved = payload.get("approved", False)
        if isinstance(approved, str):
            approved = approved.strip().lower() in ("true", "1", "yes")
        result = jarvis.run_tool(name, arguments, approved=bool(approved))
        return {
            "reply": _tool_run_reply(name, result),
            "speak": False,
            "ok": result.ok,
        }
    return {"reply": "Unknown tool action.", "speak": False}


def _tool_line(spec: ToolSpec) -> str:
    """A readable declaration of one tool, flagging when it needs approval."""
    mark = " (needs approval)" if spec.requires_approval else ""
    return f"- {spec.name}: {spec.description}{mark}"


def _tool_run_reply(name: str, result: ToolCallResult) -> str:
    """What a tool run produced -- its outcome, not a verdict on it (D6)."""
    if result.ok:
        return f"Tool '{name}' ran successfully:\n{result.value or '(no output)'}"
    return f"Tool '{name}' could not run: {result.error}"


def _format_calendar_event(event: object) -> str:
    """A readable summary of one calendar event."""
    from jarvis.domain.value_objects.calendar_event import CalendarEvent

    if not isinstance(event, CalendarEvent):
        return str(event)
    lines = [f"Title: {event.title}", f"When: {event.start} \u2192 {event.end}"]
    if event.location:
        lines.append(f"Location: {event.location}")
    if event.description:
        lines.append(f"Description: {event.description}")
    lines.append(f"ID: {event.id}")
    return "\n".join(lines)


def _format_scheduled_task(task: object) -> str:
    """A readable summary of one scheduled task."""
    from jarvis.domain.value_objects.scheduled_task import ScheduledTask

    if not isinstance(task, ScheduledTask):
        return str(task)
    lines = [
        f"Name: {task.name}",
        f"Command: {task.command}",
    ]
    if task.cron:
        lines.append(f"Schedule: {task.cron}")
    lines.append(f"Enabled: {'yes' if task.enabled else 'no'}")
    if task.next_run is not None:
        lines.append(f"Next run: {task.next_run}")
    if task.last_run is not None:
        lines.append(f"Last run: {task.last_run} ({task.last_status or 'unknown'})")
        if task.last_output:
            lines.append(f"Last output: {task.last_output[:500]}")
    if task.description:
        lines.append(f"Description: {task.description}")
    lines.append(f"ID: {task.id}")
    return "\n".join(lines)


_GOOGLE_REDIRECT_URI = "http://127.0.0.1:8765/api/auth/google/callback"


def _gain_calendar_capability(jarvis: Jarvis) -> None:
    """Propose and acquire the "manage calendar" capability, if not held yet.

    Used after wiring a live Google store so ``can_do`` reflects the new backing; this
    is the deliberate, earned acquisition (Odysseus, Vision §28). Matches the capability
    the CalendarCapability provider reports, so `can_do` and `calendar list` agree.
    """
    known = [c.name for c in jarvis.capabilities()]
    if "manage calendar" in known:
        return
    jarvis.remember_capability(
        Capability(
            name="manage calendar",
            description="see and schedule events on a live Google Calendar",
            requirement="a connected calendar store at the edge (CalendarStore)",
            provenance="google calendar",
            status=CapabilityStatus.ACQUIRED,
        )
    )


def _google_calendar(jarvis: Jarvis, payload: Reply) -> Reply:
    """Connect Jarvis to a real Google Calendar (Odysseus #6, live edge).

    Actions: ``status`` (is Google wired + connected), ``auth`` (returns the consent
    URL to open in a browser), ``complete`` (hands back the authorisation code to
    exchange for a refresh token and wire the store), and ``disconnect`` (clear the
    saved token and go offline to Google).

    ``auth`` also accepts ``client_id``/``client_secret``: when given they are
    applied to the live process and saved to ``.env`` (write-only, never echoed
    back), so the panel itself asks for the credentials instead of sending the
    companion to edit a file.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use google_calendar with action 'status', 'auth', 'complete', "
            "or 'disconnect'.",
            "speak": False,
        }
    if action == "status":
        store = google_calendar.build_google_calendar_store()
        if store is None:
            return {
                "reply": "Google Calendar is not connected. Run `google_calendar "
                "auth` to link it.",
                "speak": False,
                "connected": False,
            }
        return {
            "reply": "Google Calendar is configured; it serves the calendar capability "
            "when that capability is also earned.",
            "speak": False,
            "connected": True,
        }
    if action == "auth":
        # Credentials from the panel are write-only: staged into the live
        # process and persisted to .env, never echoed back anywhere.
        given_id = str(payload.get("client_id", "")).strip()
        given_secret = str(payload.get("client_secret", "")).strip()
        saved = False
        if given_id or given_secret:
            updates: dict[str, str] = {}
            if given_id:
                os.environ[google_calendar.ENV_CLIENT_ID] = given_id
                updates[google_calendar.ENV_CLIENT_ID] = given_id
            if given_secret:
                os.environ[google_calendar.ENV_CLIENT_SECRET] = given_secret
                updates[google_calendar.ENV_CLIENT_SECRET] = given_secret
            llm_config_store.persist(updates)
            saved = True
        client_id = given_id or google_calendar.client_id_from_environ()
        if not client_id:
            return {
                "reply": "Google Calendar needs its OAuth credentials first: paste the "
                "client ID and secret (Google Cloud Console → OAuth client ID), then "
                "connect again. They are saved to the server's .env and never shown back.",
                "speak": False,
                "redirect_uri": _GOOGLE_REDIRECT_URI,
            }
        url = google_calendar.authorize_url(
            client_id, redirect_uri=_GOOGLE_REDIRECT_URI
        )
        return {
            "reply": ("Credentials saved to .env. " if saved else "")
            + "Open this URL in your browser to authorise: " + url,
            "speak": False,
            "authorize_url": url,
            "redirect_uri": _GOOGLE_REDIRECT_URI,
            "saved": saved,
        }
    if action == "complete":
        code = str(payload.get("code", "")).strip()
        if not code:
            return {
                "reply": "Provide the authorisation code from the redirect.",
                "speak": False,
            }
        client_id = google_calendar.client_id_from_environ()
        client_secret = os.environ.get(google_calendar.ENV_CLIENT_SECRET, "")
        if not client_id or not client_secret:
            return {
                "reply": "Google Calendar needs its OAuth credentials first: run "
                "`google_calendar auth` with the client ID and secret.",
                "speak": False,
            }
        try:
            refresh, access = google_calendar.exchange_code(
                client_id, client_secret, code, redirect_uri=_GOOGLE_REDIRECT_URI
            )
        except google_calendar.GoogleCalendarAuthError as error:
            return {"reply": f"Couldn't connect Google Calendar: {error}", "speak": False}
        if refresh:
            llm_config_store.persist({google_calendar.ENV_REFRESH_TOKEN: refresh})
        # Wire the store directly from the freshly exchanged token — env may not yet hold
        # the refresh token in this process, so a factory read of the environment would
        # (correctly) conclude Google is unconfigured for this run.
        jarvis.set_calendar_store(
            google_calendar.GoogleCalendarStore(
                client_id,
                client_secret,
                refresh,
                access_token=access,
            )
        )
        _gain_calendar_capability(jarvis)
        return {
            "reply": "Google Calendar is now wired as the live calendar store. "
            "Use `calendar list` to see your events.",
            "speak": False,
        }
    if action == "disconnect":
        llm_config_store.persist({google_calendar.ENV_REFRESH_TOKEN: ""})
        jarvis.set_calendar_store(None)
        return {"reply": "Google Calendar disconnected.", "speak": False}
    return {"reply": "Unknown google_calendar action.", "speak": False}


def _calendar(jarvis: Jarvis, payload: Reply) -> Reply:
    """Manage calendar events through the calendar capability (Odysseus #6).

    Actions: ``list``, ``get``, ``create``, ``update``, ``delete``, ``range``.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use calendar with action 'list', 'get', 'create', "
            "'update', 'delete', or 'range'.",
            "speak": False,
        }
    if jarvis.calendar_store is None:
        return {
            "reply": "No calendar capability is wired up right now.",
            "speak": False,
        }
    if not jarvis.can_do("manage calendar"):
        return _capability_not_ready(jarvis, "manage calendar")
    try:
        if action == "list":
            limit_raw = payload.get("limit", 20)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 20
            events = jarvis.list_calendar_events(limit=limit)
            if not events:
                return {"reply": "No calendar events found.", "speak": False}
            lines = [_format_calendar_event(e) for e in events]
            return {
                "reply": "Calendar events:\n\n" + "\n\n".join(lines),
                "speak": False,
                "count": len(events),
            }
        if action == "get":
            event_id = str(payload.get("id", "")).strip()
            if not event_id:
                return {"reply": "Provide an event id.", "speak": False}
            event = jarvis.get_calendar_event(event_id)
            return {"reply": _format_calendar_event(event), "speak": False}
        if action == "create":
            title = str(payload.get("title", "")).strip()
            if not title:
                return {"reply": "Provide a title for the event.", "speak": False}
            start_raw = str(payload.get("start", "")).strip()
            end_raw = str(payload.get("end", "")).strip()
            if not start_raw or not end_raw:
                return {"reply": "Provide start and end datetimes (ISO format).", "speak": False}
            start = datetime.fromisoformat(start_raw)
            end = datetime.fromisoformat(end_raw)
            description = str(payload.get("description", "")).strip()
            location = str(payload.get("location", "")).strip()
            all_day_raw = payload.get("all_day", False)
            all_day = bool(all_day_raw)
            event = jarvis.create_calendar_event(
                title=title, start=start, end=end,
                description=description, location=location, all_day=all_day,
            )
            return {
                "reply": f"Created event: {event.title} (ID: {event.id})",
                "speak": False,
            }
        if action == "update":
            event_id = str(payload.get("id", "")).strip()
            if not event_id:
                return {"reply": "Provide the event id to update.", "speak": False}
            title = str(payload.get("title", "")).strip()
            if not title:
                return {"reply": "Provide a title.", "speak": False}
            start_raw = str(payload.get("start", "")).strip()
            end_raw = str(payload.get("end", "")).strip()
            if not start_raw or not end_raw:
                return {"reply": "Provide start and end datetimes (ISO format).", "speak": False}
            start = datetime.fromisoformat(start_raw)
            end = datetime.fromisoformat(end_raw)
            description = str(payload.get("description", "")).strip()
            location = str(payload.get("location", "")).strip()
            all_day_raw = payload.get("all_day", False)
            all_day = bool(all_day_raw)
            event = jarvis.update_calendar_event(
                event_id, title=title, start=start, end=end,
                description=description, location=location, all_day=all_day,
            )
            return {
                "reply": f"Updated event: {event.title} (ID: {event.id})",
                "speak": False,
            }
        if action == "delete":
            event_id = str(payload.get("id", "")).strip()
            if not event_id:
                return {"reply": "Provide the event id to delete.", "speak": False}
            jarvis.delete_calendar_event(event_id)
            return {"reply": f"Deleted event {event_id}.", "speak": False}
        if action == "range":
            start_raw = str(payload.get("start", "")).strip()
            end_raw = str(payload.get("end", "")).strip()
            if not start_raw or not end_raw:
                return {"reply": "Provide start and end datetimes (ISO format).", "speak": False}
            start = datetime.fromisoformat(start_raw)
            end = datetime.fromisoformat(end_raw)
            limit_raw = payload.get("limit", 20)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 20
            events = jarvis.calendar_events_in_range(start, end, limit=limit)
            if not events:
                return {"reply": "No events in that range.", "speak": False}
            lines = [_format_calendar_event(e) for e in events]
            return {
                "reply": "Events in range:\n\n" + "\n\n".join(lines),
                "speak": False,
                "count": len(events),
            }
    except Exception as error:  # noqa: BLE001 - the store boundary
        return {"reply": f"I couldn't do that ({type(error).__name__}).", "speak": False}
    return {"reply": "Unknown calendar action.", "speak": False}


def _tasks(jarvis: Jarvis, payload: Reply) -> Reply:
    """Manage scheduled tasks through the task-scheduler capability (Odysseus #7).

    Actions: ``list``, ``get``, ``create``, ``update``, ``delete``,
    ``enable``, ``disable``, ``due``, ``run``. ``run`` executes the task's
    command right now through the earned-agency executor and records the
    outcome on the task (last run, status, output); it needs an enabled task
    and a wired executor, else it declines honestly and records nothing.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use tasks with action 'list', 'get', 'create', 'update', "
            "'delete', 'enable', 'disable', 'due', or 'run'.",
            "speak": False,
        }
    if jarvis.task_scheduler is None:
        return {
            "reply": "No task-scheduler capability is wired up right now.",
            "speak": False,
        }
    if not jarvis.can_do("manage tasks"):
        return _capability_not_ready(jarvis, "manage tasks")
    try:
        if action == "list":
            limit_raw = payload.get("limit", 20)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 20
            tasks = jarvis.list_scheduled_tasks(limit=limit)
            if not tasks:
                return {"reply": "No scheduled tasks found.", "speak": False}
            lines = [_format_scheduled_task(t) for t in tasks]
            return {
                "reply": "Scheduled tasks:\n\n" + "\n\n".join(lines),
                "speak": False,
                "count": len(tasks),
            }
        if action == "get":
            task_id = str(payload.get("id", "")).strip()
            if not task_id:
                return {"reply": "Provide a task id.", "speak": False}
            task = jarvis.get_scheduled_task(task_id)
            return {"reply": _format_scheduled_task(task), "speak": False}
        if action == "create":
            name = str(payload.get("name", "")).strip()
            if not name:
                return {"reply": "Provide a name for the task.", "speak": False}
            command = str(payload.get("command", "")).strip()
            if not command:
                return {"reply": "Provide a command for the task.", "speak": False}
            cron = str(payload.get("cron", "")).strip()
            description = str(payload.get("description", "")).strip()
            enabled_raw = payload.get("enabled", True)
            enabled = bool(enabled_raw)
            task = jarvis.create_scheduled_task(
                name=name, command=command, cron=cron,
                description=description, enabled=enabled,
            )
            return {
                "reply": f"Created task: {task.name} (ID: {task.id})",
                "speak": False,
            }
        if action == "update":
            task_id = str(payload.get("id", "")).strip()
            if not task_id:
                return {"reply": "Provide the task id to update.", "speak": False}
            name = str(payload.get("name", "")).strip()
            if not name:
                return {"reply": "Provide a name.", "speak": False}
            command = str(payload.get("command", "")).strip()
            if not command:
                return {"reply": "Provide a command.", "speak": False}
            cron = str(payload.get("cron", "")).strip()
            description = str(payload.get("description", "")).strip()
            enabled_raw = payload.get("enabled", True)
            enabled = bool(enabled_raw)
            task = jarvis.update_scheduled_task(
                task_id, name=name, command=command, cron=cron,
                description=description, enabled=enabled,
            )
            return {
                "reply": f"Updated task: {task.name} (ID: {task.id})",
                "speak": False,
            }
        if action == "delete":
            task_id = str(payload.get("id", "")).strip()
            if not task_id:
                return {"reply": "Provide the task id to delete.", "speak": False}
            jarvis.delete_scheduled_task(task_id)
            return {"reply": f"Deleted task {task_id}.", "speak": False}
        if action == "enable":
            task_id = str(payload.get("id", "")).strip()
            if not task_id:
                return {"reply": "Provide the task id to enable.", "speak": False}
            task = jarvis.enable_scheduled_task(task_id)
            return {
                "reply": f"Enabled task: {task.name} (ID: {task.id})",
                "speak": False,
            }
        if action == "disable":
            task_id = str(payload.get("id", "")).strip()
            if not task_id:
                return {"reply": "Provide the task id to disable.", "speak": False}
            task = jarvis.disable_scheduled_task(task_id)
            return {
                "reply": f"Disabled task: {task.name} (ID: {task.id})",
                "speak": False,
            }
        if action == "due":
            tasks = jarvis.due_scheduled_tasks()
            if not tasks:
                return {"reply": "No tasks are currently due.", "speak": False}
            lines = [_format_scheduled_task(t) for t in tasks]
            return {
                "reply": "Due tasks:\n\n" + "\n\n".join(lines),
                "speak": False,
                "count": len(tasks),
            }
        if action == "run":
            task_id = str(payload.get("id", "")).strip()
            if not task_id:
                return {"reply": "Provide the task id to run.", "speak": False}
            try:
                outcome = jarvis.run_scheduled_task(task_id)
            except RuntimeError as error:
                return {"reply": f"I couldn't run it: {error}", "speak": False}
            if outcome.success:
                return {
                    "reply": f"Ran it — {outcome.summary} (recorded on the task).",
                    "speak": False,
                    "ok": True,
                }
            return {
                "reply": f"It ran but failed honestly: {outcome.summary} (recorded on the task).",
                "speak": False,
                "ok": False,
            }
    except ValueError as error:  # noqa: BLE001 - a bad cron/schedule is guidance, not a crash
        return {"reply": f"No pude hacerlo: {error}", "speak": False}
    except Exception as error:  # noqa: BLE001 - the store boundary
        return {"reply": f"I couldn't do that ({type(error).__name__}).", "speak": False}
    return {"reply": "Unknown tasks action.", "speak": False}


def _format_note(note: object) -> str:
    """A readable summary of one stored note."""
    from jarvis.domain.value_objects.note import Note

    if not isinstance(note, Note):
        return str(note)
    lines = [f"Title: {note.title}"]
    if note.tags:
        lines.append(f"Tags: {', '.join(note.tags)}")
    if note.body:
        body = note.body if len(note.body) <= 500 else note.body[:500].rstrip() + "…"
        lines.append(body)
    lines.append(f"ID: {note.id}")
    return "\n".join(lines)


def _note_tags(raw: object) -> tuple[str, ...]:
    """Tags from a comma string or a list, cleaned and de-duplicated."""
    if isinstance(raw, list):
        items = [str(v).strip() for v in cast("list[object]", raw)]
    else:
        items = [item.strip() for item in str(raw or "").split(",")]
    seen: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.append(item)
    return tuple(seen)


def _notes(jarvis: Jarvis, payload: Reply) -> Reply:
    """Keep plain-text notes through the notes capability (Odysseus #8).

    Actions: ``list``, ``get``, ``create``, ``update``, ``delete``, ``search``.
    Notes are unvetted material the companion asked to keep -- reading one is
    retrieval, never a verdict; writing one is reversible and gated in the
    caller, never a decision Jarvis makes on its own.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use notes with action 'list', 'get', 'create', "
            "'update', 'delete', or 'search'.",
            "speak": False,
        }
    if jarvis.notes_store is None:
        return {
            "reply": "No notes capability is wired up right now.",
            "speak": False,
        }
    if not jarvis.can_do("manage notes"):
        return _capability_not_ready(jarvis, "manage notes")
    try:
        if action == "list":
            limit_raw = payload.get("limit", 20)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 20
            found = jarvis.list_notes(limit=limit)
            if not found:
                return {"reply": "No notes yet — jot one down.", "speak": False}
            lines = [_format_note(n) for n in found]
            return {
                "reply": "Notes:\n\n" + "\n\n".join(lines),
                "speak": False,
                "count": len(found),
                "notes": [
                    {"id": n.id, "title": n.title, "tags": list(n.tags)}
                    for n in found
                ],
            }
        if action == "get":
            note_id = str(payload.get("id", "")).strip()
            if not note_id:
                return {"reply": "Provide a note id.", "speak": False}
            note = jarvis.get_note(note_id)
            return {
                "reply": _format_note(note),
                "speak": False,
                "note": {
                    "id": note.id,
                    "title": note.title,
                    "body": note.body,
                    "tags": list(note.tags),
                },
            }
        if action == "create":
            title = str(payload.get("title", "")).strip()
            body = str(payload.get("body", "")).strip()
            if not title and not body:
                return {"reply": "Provide a title and/or a body.", "speak": False}
            note = jarvis.create_note(
                title=title, body=body, tags=_note_tags(payload.get("tags"))
            )
            return {
                "reply": f"Kept note: {note.title} (ID: {note.id})",
                "speak": False,
            }
        if action == "update":
            note_id = str(payload.get("id", "")).strip()
            if not note_id:
                return {"reply": "Provide the note id to update.", "speak": False}
            current = jarvis.get_note(note_id)
            title = str(payload.get("title", "")).strip() or current.title
            body = str(payload.get("body", "")).strip() or current.body
            tags = (
                _note_tags(payload.get("tags"))
                if "tags" in payload
                else current.tags
            )
            note = jarvis.update_note(note_id, title=title, body=body, tags=tags)
            return {
                "reply": f"Updated note: {note.title} (ID: {note.id})",
                "speak": False,
            }
        if action == "delete":
            note_id = str(payload.get("id", "")).strip()
            if not note_id:
                return {"reply": "Provide the note id to delete.", "speak": False}
            jarvis.delete_note(note_id)
            return {"reply": f"Deleted note {note_id}.", "speak": False}
        if action == "search":
            query = str(payload.get("query", "")).strip()
            if not query:
                return {"reply": "Provide a query to search notes.", "speak": False}
            limit_raw = payload.get("limit", 10)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 10
            found = jarvis.search_notes(query, limit=limit)
            if not found:
                return {
                    "reply": f"Nothing in notes matches {query!r}.",
                    "speak": False,
                    "count": 0,
                }
            lines = [_format_note(n) for n in found]
            return {
                "reply": f"Notes matching {query!r}:\n\n" + "\n\n".join(lines),
                "speak": False,
                "count": len(found),
                "notes": [
                    {"id": n.id, "title": n.title, "tags": list(n.tags)}
                    for n in found
                ],
            }
    except Exception as error:  # noqa: BLE001 - the store boundary
        return {"reply": f"I couldn't do that ({type(error).__name__}).", "speak": False}
    return {"reply": "Unknown notes action.", "speak": False}


def _format_email(message: object) -> str:
    """A readable summary of one email, body truncated for the surface."""
    from jarvis.domain.value_objects.email_message import EmailMessage

    if not isinstance(message, EmailMessage):
        return str(message)
    lines = [
        f"From: {message.sender or '(unknown)'}",
        f"Subject: {message.subject or '(no subject)'}",
    ]
    if message.recipients:
        lines.append(f"To: {', '.join(message.recipients)}")
    body = message.body if len(message.body) <= 800 else message.body[:800].rstrip() + "…"
    lines.append(body)
    lines.append(f"ID: {message.message_id or '(none)'}")
    return "\n".join(lines)


def _mail(jarvis: Jarvis, payload: Reply) -> Reply:
    """Read and send email through the mailbox capability (Odysseus email).

    Actions: ``list`` (``folder``, ``limit``), ``read`` (``message_id``,
    ``folder``), ``send`` (``to``, ``subject``, ``body``). Reading is
    retrieval -- candidate context, never adopted fact. Sending is an external
    material act: it needs the earned capability *and* an explicit
    ``approved: true`` per send, so nothing ever leaves the outbox by
    accident; without it the reply asks for approval and sends nothing.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use mail with action 'list', 'read', or 'send'.",
            "speak": False,
        }
    if jarvis.mail_source is None:
        return {
            "reply": "No mail capability is wired up right now.",
            "speak": False,
        }
    if not jarvis.can_do("send and read email"):
        return _capability_not_ready(jarvis, "send and read email")
    try:
        if action == "list":
            folder = str(payload.get("folder", "inbox")).strip() or "inbox"
            limit_raw = payload.get("limit", 10)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 10
            messages = jarvis.list_emails(folder=folder, limit=limit)
            if not messages:
                return {"reply": f"No messages in {folder}.", "speak": False}
            lines = [_format_email(m) for m in messages]
            return {
                "reply": f"Messages in {folder}:\n\n" + "\n\n".join(lines),
                "speak": False,
                "count": len(messages),
            }
        if action == "read":
            message_id = str(payload.get("message_id", "")).strip()
            if not message_id:
                return {"reply": "Provide a message id.", "speak": False}
            folder = str(payload.get("folder", "inbox")).strip() or "inbox"
            return {
                "reply": _format_email(jarvis.read_email(message_id, folder=folder)),
                "speak": False,
            }
        if action == "send":
            raw_to = payload.get("to", "")
            recipients = _note_tags(raw_to)
            if not recipients:
                return {"reply": "Provide at least one recipient.", "speak": False}
            subject = str(payload.get("subject", "")).strip()
            body = str(payload.get("body", "")).strip()
            if not subject and not body:
                return {"reply": "Provide a subject and/or a body.", "speak": False}
            approved = payload.get("approved", False)
            if isinstance(approved, str):
                approved = approved.strip().lower() in ("true", "1", "yes")
            if not approved:
                return {
                    "reply": (
                        "Sending email is an external act — confirm it explicitly "
                        "by sending again with approved: true. Nothing was sent."
                    ),
                    "speak": False,
                }
            sent = jarvis.send_email(to=recipients, subject=subject, body=body)
            return {
                "reply": f"Sent to {', '.join(sent.recipients)}: {sent.subject or '(no subject)'}",
                "speak": False,
            }
    except Exception as error:  # noqa: BLE001 - the mailbox boundary
        return {"reply": f"I couldn't do that ({type(error).__name__}).", "speak": False}
    return {"reply": "Unknown mail action.", "speak": False}


def _documents(jarvis: Jarvis, payload: Reply) -> Reply:
    """Manage the files the companion shares (work-with-files capability).

    Actions: ``list``, ``read``, ``info``, ``save``, ``edit``, ``search``, ``remove``.
    ``list`` names each document with its owner (companion-shared vs generated).
    ``info`` answers "whose is that, and when did I get it?" from the recorded
    provenance (Vision §26). ``save`` takes ``name`` and ``content`` with
    ``encoding`` ``"text"`` (default) or ``"b64"`` (binary kept intact), an
    optional ``path`` folder to file the document under (``"docs/api.md"``,
    relative and sandbox-safe), and an optional ``owner`` ``"companion"``
    (default) or ``"jarvis"``. ``edit`` rewrites an existing document from a
    free-form ``instruction``: the live model *proposes* the revised text (Vision
    §38) and Jarvis applies it, keeping the recorded attribution and reporting
    what actually changed; offline there is no grounded proposal to apply. ``read``
    returns the content as text (truncated for the surface) or base64. ``search``
    takes ``query`` and returns the documents whose name or text match, each with a
    snippet and match strength -- candidates, never a verdict.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use documents with action 'list', 'read', 'info', 'save', "
            "'edit', 'search', or 'remove'.",
            "speak": False,
        }
    if jarvis.documents_store is None:
        return {
            "reply": "No documents capability is wired up right now.",
            "speak": False,
        }
    if not jarvis.can_do("work with files"):
        return _capability_not_ready(jarvis, "work with files")
    try:
        if action == "list":
            names = jarvis.list_documents()
            if not names:
                return {"reply": "No documents yet — share a file.", "speak": False}
            lines = "".join(f"  - {_ownership_tag(jarvis, name)}{name}\n" for name in names)
            return {
                "reply": f"Documents I'm keeping ({len(names)}):\n\n{lines}",
                "speak": False,
                "count": len(names),
            }
        if action == "read":
            name = _document_name(payload.get("name"))
            if not name:
                return {"reply": "Provide a document name to read.", "speak": False}
            raw = jarvis.read_document(name)
            return _document_read_reply(name, raw)
        if action == "info":
            name = _document_name(payload.get("name"))
            if not name:
                return {"reply": "Provide a document name to inspect.", "speak": False}
            return _document_info_reply(name, jarvis)
        if action == "save":
            name = _document_name(payload.get("name"))
            if not name:
                return {"reply": "Provide a document name.", "speak": False}
            try:
                folder = _document_folder(payload.get("path"))
            except ValueError:
                return {
                    "reply": "That document path escapes my sandbox.",
                    "speak": False,
                }
            if folder:
                name = f"{folder}/{name}"
            content = payload.get("content")
            if content is None:
                return {"reply": "Provide the document content.", "speak": False}
            encoding = str(payload.get("encoding", "text")).strip().lower()
            if encoding == "b64":
                try:
                    raw = base64.b64decode(str(content), validate=True)
                except (ValueError, TypeError):
                    return {"reply": "content was not valid base64.", "speak": False}
            else:
                raw = str(content).encode("utf-8")
            owner = _document_owner(payload.get("owner"))
            if owner is None:
                return {"reply": "Owner must be 'companion' or 'jarvis'.", "speak": False}
            jarvis.write_document(name, raw, owner=owner)
            nbytes = len(raw)
            note = " " if _looks_text(raw) else " (binary)"
            return {
                "reply": f"Kept {name} ({nbytes} bytes{note}).",
                "speak": False,
                "name": name,
            }
        if action == "edit":
            name = _document_name(payload.get("name"))
            if not name:
                return {"reply": "Provide a document name to edit.", "speak": False}
            instruction = str(payload.get("instruction", "")).strip()
            if not instruction:
                return {
                    "reply": "Tell me what to change (instruction).",
                    "speak": False,
                }
            if jarvis.document_editor is None:
                return {
                    "reply": "Editing needs a live model to propose the rewrite — "
                    "share the corrected content via save instead.",
                    "speak": False,
                }
            try:
                edit = jarvis.edit_document(name, instruction)
            except ValueError:
                return {
                    "reply": "That document isn't text, so I can't rewrite it.",
                    "speak": False,
                }
            if edit is None:
                return {
                    "reply": "I couldn't come up with a concrete rewrite for that — "
                    "share the corrected content via save instead.",
                    "speak": False,
                }
            return {
                "reply": f"Rewrote {name}: {edit.note} "
                f"({len(edit.content.encode('utf-8'))} bytes).",
                "speak": False,
                "name": name,
                "note": edit.note,
            }
        if action == "search":
            query = str(payload.get("query", "")).strip()
            if not query:
                return {"reply": "Provide a query to search my documents.", "speak": False}
            limit_raw = payload.get("limit", 5)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 5
            hits = jarvis.search_documents(query, limit=limit)
            if not hits:
                return {
                    "reply": "Nothing in my documents matches that.",
                    "speak": False,
                    "count": 0,
                }
            lines = "".join(
                f"  - {hit.name} ({hit.relevance:.2f}): {hit.snippet}\n"
                for hit in hits
            )
            return {
                "reply": f"Documents matching \"{query}\" ({len(hits)}):\n\n{lines}",
                "speak": False,
                "count": len(hits),
                "hits": [
                    {"name": hit.name, "snippet": hit.snippet}
                    for hit in hits
                ],
            }
        if action == "remove":
            name = _document_name(payload.get("name"))
            if not name:
                return {"reply": "Provide a document name to remove.", "speak": False}
            jarvis.remove_document(name)
            return {"reply": f"Removed {name}.", "speak": False}
    except Exception as error:  # noqa: BLE001 - the store boundary
        return {"reply": f"I couldn't do that ({type(error).__name__}).", "speak": False}
    return {"reply": "Unknown documents action.", "speak": False}


def _document_name(raw: object) -> str:
    """A safe document name from arbitrary input (its basename only).

    Browser upload paths (``C:/Users/me/file.txt``, ``../file.txt``) collapse to
    the bare file name; a folder is filed separately through ``path`` so the
    sandbox boundary is never near a traversal.
    """
    text = str(raw or "").strip()
    if not text:
        return ""
    return Path(text.replace("\\", "/")).name


def _document_folder(raw: object) -> str:
    """A safe, relative folder to file documents under, or ``""`` when omitted.

    Raises :class:`ValueError` when the folder would escape the sandbox
    (absolute, or containing ``..``/``.`` or empty segments), mirroring the
    store's own name gate.
    """
    text = str(raw or "").strip().replace("\\", "/")
    if not text:
        return ""
    parts = text.split("/")
    if (
        text.startswith("/")
        or any(part in ("", ".", "..") for part in parts)
        or any(":" in part for part in parts)
    ):
        raise ValueError("document path escapes the sandbox")
    return text


def _looks_text(content: bytes) -> bool:
    """Best-effort guess of whether ``content`` is text (utf-8-decodable)."""
    try:
        content.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _ownership_tag(jarvis: Jarvis, name: str) -> str:
    """A short attribution prefix for a document in a listing (Vision §26).

    Companion-shared files are the norm; only a Jarvis-materialised artifact is
    tagged explicitly, so the common case stays quiet.
    """
    meta = jarvis.document_meta(name)
    if meta is not None and meta.owner is DocumentOwner.JARVIS:
        return "[jarvis] "
    return ""


def _document_owner(raw: object) -> DocumentOwner | None:
    """The attribution for a save, or None when the value is not a known owner."""
    if raw is None:
        return DocumentOwner.COMPANION
    text = str(raw).strip().lower()
    if text == "jarvis":
        return DocumentOwner.JARVIS
    if text == "companion":
        return DocumentOwner.COMPANION
    return None


def _document_info_reply(name: str, jarvis: Jarvis) -> Reply:
    """Render the recorded provenance of one document (Vision §26).

    ``requested_at``/``updated_at``/``owner`` are the store's honest record of
    attribution and timing; ``None`` means the file predates provenance tracking.
    """
    meta = jarvis.document_meta(name)
    if meta is None:
        return {
            "reply": f"I keep {name} but no provenance was recorded for it — it "
            "predates my ownership tracking.",
            "speak": False,
            "name": name,
        }
    owner = (
        "companion — I'm keeping a file you shared"
        if meta.owner is DocumentOwner.COMPANION
        else "jarvis — a document I generated"
    )
    return {
        "reply": (
            f"{name}\n"
            f"  Owner:   {owner}\n"
            f"  Size:    {meta.size_bytes} bytes\n"
            f"  Stored:  {meta.stored_at:%Y-%m-%d %H:%M} UTC\n"
            f"  Updated: {meta.updated_at:%Y-%m-%d %H:%M} UTC"
        ),
        "speak": False,
        "name": name,
        "meta": {
            "name": meta.name,
            "owner": meta.owner.value,
            "size_bytes": meta.size_bytes,
            "stored_at": meta.stored_at.isoformat(),
            "updated_at": meta.updated_at.isoformat(),
        },
    }


def _document_read_reply(name: str, raw: bytes) -> Reply:
    """Render a document read: text when readably textual, base64 when binary.

    Long text is truncated for the surface (the reasoner reads in slices); the full
    byte length is always reported so the companion knows what was skipped.
    """
    if _looks_text(raw):
        text = raw.decode("utf-8", errors="replace")
        shown = text[:3000]
        if len(text) > len(shown):
            shown = f"{shown}\n\n... ({len(text)} chars total; say 'documents read " \
                    f"{name}' at the seam for the full stream)"
        return {"reply": f"{name}:\n\n{shown}", "speak": False, "name": name}
    return {
        "reply": f"{name} is binary ({len(raw)} bytes) — I keep it intact but can't "
        "read its contents yet. Say 'read <name>' at the seam for raw bytes.",
        "speak": False,
        "name": name,
        "encoding": "b64",
        "content": base64.b64encode(raw).decode("ascii"),
    }


def _ready_marker(jarvis: Jarvis, capability: str) -> str:
    """A concise "(ready)" taste when an acquired capability is live-backed."""
    return " (ready)" if jarvis.can_do(capability) else ""


def _belief(jarvis: Jarvis, payload: Reply) -> Reply:
    """Explore what Jarvis holds as grounded beliefs, with their evidence (F5).

    Actions: ``list`` (every belief with its derived confidence and how many
    pieces of evidence bear for/against it) and ``get`` (``statement`` -- the
    full provenance of one belief, the same grounds the reasoning panel shows).
    Read-only: beliefs are never edited here, only inspected.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use belief with action 'list' or 'get'.",
            "speak": False,
        }
    if action == "list":
        beliefs = sorted(
            jarvis.beliefs.all_beliefs(),
            key=lambda b: b.confidence.value,
            reverse=True,
        )
        if not beliefs:
            return {
                "reply": "I hold no grounded beliefs yet — talk to me and confirm what I reason.",
                "speak": False,
                "beliefs": [],
            }
        entries: list[Reply] = []
        for belief in beliefs:
            explanation = belief.explain()
            entries.append(
                {
                    "statement": explanation.statement,
                    "subject": subject_of(explanation.statement),
                    "confidence": explanation.confidence.value,
                    "supporting": len(explanation.supporting),
                    "contradicting": len(explanation.contradicting),
                }
            )
        lines = [
            f"- {e['subject']} ({e['confidence']:.2f}, "
            f"{e['supporting']}+{e['contradicting']}-)"
            for e in entries
        ]
        return {
            "reply": "What I hold:\n" + "\n".join(lines),
            "speak": False,
            "beliefs": entries,
        }
    if action == "get":
        statement = str(payload.get("statement", "")).strip()
        if not statement:
            return {"reply": "Name a belief statement to inspect.", "speak": False}
        belief = jarvis.beliefs.get_by_statement(statement)
        if belief is None:
            return {
                "reply": f"I hold no belief recorded as {statement!r}.",
                "speak": False,
            }
        grounds = _provenance(belief)
        grounds["statement"] = belief.explain().statement
        return {
            "reply": belief.explain().narrate(subject_of(belief.explain().statement)),
            "speak": False,
            "provenance": grounds,
        }
    return {"reply": "Unknown belief action.", "speak": False}


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


# Predefined multi-step chains over the real edge commands (F4). Each step names
# a command from _COMMANDS plus its static payload; ``from_inputs`` copies named
# caller inputs into that payload. A step with ``collect`` builds its payload
# from the previous steps' replies instead (a genuine chain, not parallel calls).
_WORKFLOWS: dict[str, Reply] = {
    "brief": {
        "title": "El día de un vistazo",
        "description": "Próximos eventos del calendario + tareas pendientes, en un digest.",
        "inputs": [],
        "steps": [
            {"command": "calendar", "payload": {"action": "list", "limit": 5}},
            {"command": "tasks", "payload": {"action": "due"}},
        ],
    },
    "investigate": {
        "title": "Investigar un tema",
        "description": "Búsqueda web y después investigación en profundidad sobre el tema.",
        "inputs": [
            {"name": "query", "label": "tema", "required": True},
            {"name": "depth", "label": "profundidad", "required": False, "default": "1"},
        ],
        "steps": [
            {
                "command": "external",
                "payload": {"action": "search", "limit": 5},
                "from_inputs": ["query"],
            },
            {
                "command": "research",
                "payload": {"depth": 1},
                "from_inputs": ["query", "depth"],
            },
        ],
    },
    "dossier": {
        "title": "Armar un dossier",
        "description": "Busca, investiga y guarda el combinado como documento generado.",
        "inputs": [
            {"name": "query", "label": "tema", "required": True},
        ],
        "steps": [
            {
                "command": "external",
                "payload": {"action": "search", "limit": 5},
                "from_inputs": ["query"],
            },
            {
                "command": "research",
                "payload": {"depth": 1},
                "from_inputs": ["query"],
            },
            {"command": "documents", "collect": True},
        ],
    },
}


def _workflow_step_capability(command: str, payload: Reply) -> str | None:
    """The earned capability a workflow step needs, or None when it needs none."""
    if command == "external":
        action = str(payload.get("action", "")).strip().lower()
        if action == "search":
            return "search the web"
        if action == "read":
            return "read external documents"
        return None
    if command == "research":
        return "deep research"
    if command == "compare":
        return "compare language models"
    if command == "calendar":
        return "manage calendar"
    if command == "tasks":
        return "manage tasks"
    if command == "documents":
        return "work with files"
    return None


def _workflow_missing(jarvis: Jarvis, name: str) -> list[Reply]:
    """The inactive edges a workflow needs, each with its honest derived reason."""
    definition = _WORKFLOWS[name]
    reasons = {edge.get("capability"): edge.get("reason") for edge in _agents_block(jarvis)}
    missing: list[Reply] = []
    seen: set[str] = set()
    for step in cast("list[Reply]", definition["steps"]):
        command = str(step.get("command", ""))
        if bool(step.get("collect")):
            capability: str | None = "work with files"
        else:
            capability = _workflow_step_capability(command, cast("Reply", step.get("payload", {})))
        if capability is None or capability in seen:
            continue
        seen.add(capability)
        if not jarvis.can_do(capability):
            missing.append({"capability": capability, "reason": reasons.get(capability)})
    return missing


def _workflows_block(jarvis: Jarvis) -> list[Reply]:
    """Every predefined workflow with its inputs and whether its edges are live."""
    block: list[Reply] = []
    for name, definition in _WORKFLOWS.items():
        missing = _workflow_missing(jarvis, name)
        block.append(
            {
                "name": name,
                "title": definition["title"],
                "description": definition["description"],
                "inputs": definition["inputs"],
                "steps": [
                    {
                        "command": step.get("command", ""),
                        "action": cast("Reply", step.get("payload", {})).get("action", ""),
                    }
                    for step in cast("list[Reply]", definition["steps"])
                ],
                "ready": not missing,
                "missing": missing,
            }
        )
    return block


def _slug(text: str, limit: int = 40) -> str:
    """A filesystem-safe slug for a generated dossier name."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit] or "dossier"


def _workflow(jarvis: Jarvis, payload: Reply) -> Reply:
    """Run a predefined multi-step chain over the real edge commands (F4).

    Actions: ``list`` (definitions with inputs and which edges are live) and
    ``run`` (``name`` plus ``inputs``). A workflow runs only when every edge
    it needs is active (acquired + live-backed); otherwise it refuses honestly
    with each step marked blocked and the derived reason -- nothing half-runs.
    Steps run in order and stop on the first error (later steps read as
    omitted); the final reply joins every step's real outcome under headers.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use workflow with action 'list' or 'run'.",
            "speak": False,
        }
    if action == "list":
        block = _workflows_block(jarvis)
        lines = [
            f"- {entry['name']}: {entry['title']}"
            + (" (ready)" if entry["ready"] else " (blocked)")
            for entry in block
        ]
        return {
            "reply": "Workflows:\n" + "\n".join(lines),
            "speak": False,
            "workflows": block,
        }
    if action == "run":
        name = str(payload.get("name", "")).strip()
        if name not in _WORKFLOWS:
            return {"error": f"unknown workflow: {name or '(none)'}", "speak": False}
        definition = _WORKFLOWS[name]
        raw_inputs = payload.get("inputs", {})
        inputs: dict[str, str] = {}
        if isinstance(raw_inputs, dict):
            items = cast("dict[object, object]", raw_inputs)
            inputs = {str(k): str(v) for k, v in items.items()}
        for schema in cast("list[Reply]", definition["inputs"]):
            key = str(schema.get("name", ""))
            if bool(schema.get("required")) and not inputs.get(key, "").strip():
                return {
                    "error": f"workflow '{name}' needs input '{key}'.",
                    "speak": False,
                }
            if key not in inputs and schema.get("default") is not None:
                inputs[key] = str(schema["default"])
        missing = _workflow_missing(jarvis, name)
        steps = cast("list[Reply]", definition["steps"])
        if missing:
            wanted = ", ".join(str(m.get("capability")) for m in missing)
            return {
                "ok": False,
                "reply": (
                    f"No puedo ejecutar '{name}': faltan bordes activos ({wanted}). "
                    "Mira la pestaña Agentes para el porqué de cada uno."
                ),
                "speak": False,
                "steps": [
                    {
                        "command": step.get("command", ""),
                        "action": cast("Reply", step.get("payload", {})).get("action", ""),
                        "state": "bloqueado",
                        "reason": next(
                            (
                                str(m.get("reason"))
                                for m in missing
                                if m.get("capability")
                                == (
                                    "work with files"
                                    if step.get("collect")
                                    else _workflow_step_capability(
                                        str(step.get("command", "")),
                                        cast("Reply", step.get("payload", {})),
                                    )
                                )
                            ),
                            None,
                        ),
                    }
                    for step in steps
                ],
            }
        ran: list[Reply] = []
        collected: list[tuple[str, str]] = []
        halted = False
        for step in steps:
            command = str(step.get("command", ""))
            if halted:
                ran.append({"command": command, "state": "omitido"})
                continue
            if bool(step.get("collect")):
                query = inputs.get("query", "tema")
                body = "\n\n".join(
                    f"# {title}\n\n{text}" for title, text in collected
                ) or "(sin resultados previos)"
                step_payload: Reply = {
                    "action": "save",
                    "name": f"dossier-{_slug(query)}.md",
                    "content": f"# Dossier: {query}\n\n{body}\n",
                    "owner": "jarvis",
                }
            else:
                step_payload = dict(cast("Reply", step.get("payload", {})))
                for key in cast("list[str]", step.get("from_inputs", [])):
                    if key in inputs:
                        step_payload[key] = inputs[key]
            run = _COMMANDS.get(command)
            if run is None:
                ran.append(
                    {"command": command, "state": "error", "reply": "unknown step command."}
                )
                halted = True
                continue
            outcome = run(jarvis, step_payload)
            outcome.pop("state", None)
            text = str(outcome.get("reply") or outcome.get("error") or "(sin salida)")
            if "error" in outcome:
                ran.append({"command": command, "state": "error", "reply": text})
                halted = True
                continue
            label = (
                f"{command} {step_payload.get('action', '')}".strip()
                if not step.get("collect")
                else "documents save"
            )
            collected.append((label, text))
            ran.append({"command": command, "state": "ok", "reply": text})
        digest = "\n\n---\n\n".join(
            f"## {title}\n\n{text}" for title, text in collected
        ) or "(sin resultados)"
        all_ok = all(entry.get("state") == "ok" for entry in ran)
        title = str(definition.get("title", name))
        done = sum(1 for entry in ran if entry.get("state") == "ok")
        return {
            "ok": all_ok,
            "reply": f"Workflow '{title}' ({done}/{len(ran)} pasos ok):\n\n{digest}",
            "speak": False,
            "steps": ran,
        }
    return {"reply": "Unknown workflow action.", "speak": False}


_COMMANDS: dict[str, Command] = {
    "say": _say,
    "explain": _explain,
    "reflect": _reflect,
    "introspect": _introspect,
    "wonder": _wonder,
    "rest": _rest,
    "energy_budget": _energy_budget,
    "deliberation": _deliberation,
    "tunables": _tunables,
    "perceiver": _perceiver,
    "provider_health": _provider_health,
    "reasoner": _reasoner,
    "provider_reset": _provider_reset,
    "embeddings": _embeddings,
    "speech": _speech,
    "learn": _learn,
    "greeting": _greeting,
    "state": _state,
    "external": _external,
    "research": _research,
    "compare": _compare,
    "capability": _capability,
    "tool": _tool,
    "calendar": _calendar,
    "google_calendar": _google_calendar,
    "tasks": _tasks,
    "notes": _notes,
    "mail": _mail,
    "documents": _documents,
    "workflow": _workflow,
    "belief": _belief,
    "recall": _recall,
    "conversations": _conversations,
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
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Malformed or non-UTF-8 body -> empty payload, never a 500.
        return {}
    return cast("Reply", loaded) if isinstance(loaded, dict) else {}


def parse_body(body: bytes) -> Reply:
    """Public wrapper over the request-body parser, for the streaming server path."""
    return _parse(body)


def _json(payload: Reply) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _google_oauth_callback(jarvis: Jarvis, path: str) -> Response:
    """Complete the Google OAuth handshake from the browser callback and send Jarvis home.

    A browser GET (Google redirects here with ``?code=...``), so the response is a small
    HTML page that bounces the user to ``/``. The ``code`` is single-use: it feeds the
    ``google_calendar complete`` command which exchanges it, persists the refresh token,
    wires the store, and acquires the capability. Any failure is a clear message, not a
    crash.
    """
    query = urllib.parse.parse_qs(path.split("?", 1)[1] if "?" in path else "")
    codes = query.get("code", [])
    error = query.get("error", [None])[0]
    if error:
        message = f"Google refused authorisation: {error}"
    elif not codes:
        message = "Google Calendar callback received no authorisation code."
    else:
        result = handle(
            jarvis, "google_calendar", {"action": "complete", "code": codes[0]}
        )
        message = "OK — you can close this tab and return to the command center."
        if "error" in result:
            message = f"Couldn't connect Google Calendar: {result['error']}"
        elif result.get("reply"):
            message = str(result["reply"])
    body = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>Jarvis — Google Calendar</title></head>"
        f"<body style='font-family:system-ui;background:#05070d;color:#dfe9ff;"
        f"font-size:16px;line-height:1.6;padding:2em'>"
        f"<p>{message}</p>"
        "<p><a href='/' style='color:#38e6d0'>Return to the command center</a></p>"
        "</body></html>"
    ).encode()
    return Response(200, "text/html; charset=utf-8", body)


def _transcribe(jarvis: Jarvis, audio: bytes) -> Response:
    """Transcribe raw audio with the wired ear and answer as JSON.

    A missing ear is a clean 400 (configuration, not a crash); a provider/network
    failure is a structured 502 so the server survives and the client sees what
    happened. Success returns ``{"text": …}``.
    """
    if jarvis.speech_perception is None:
        return Response(
            400,
            "application/json; charset=utf-8",
            _json({"error": "no speech capability configured; set_speech_perception"}),
        )
    try:
        text = jarvis.transcribe(audio)
    except Exception as error:  # noqa: BLE001 -- a loud, structured provider error
        message = f"transcription failed: {error}"
        return Response(502, "application/json; charset=utf-8", _json({"error": message}))
    return Response(200, "application/json; charset=utf-8", _json({"text": text}))


def route(jarvis: Jarvis, method: str, path: str, body: bytes) -> Response:
    """Decide the response for one HTTP request — pure, no socket (Vision §30).

    Serves the console page at ``/``, the live snapshot at ``GET /api/state``, and a
    command at ``POST /api/<command>``. ``POST /api/speech/transcribe`` takes raw
    audio bytes (not JSON) and returns the transcription. This is the whole HTTP
    contract, testable without binding a port; :mod:`jarvis.interface.server` only
    moves the bytes.
    """
    clean = path.split("?", 1)[0]
    if method == "GET" and clean in ("/", "/index.html"):
        return Response(200, "text/html; charset=utf-8", _CONSOLE_HTML.read_bytes())
    # Google OAuth redirects the browser back here with ?code=...&state=.... We swallow
    # it into the `google_calendar complete` command and bounce the user back to the
    # console with a small page (this is a browser GET, not a JSON API call).
    if method == "GET" and clean == "/api/auth/google/callback":
        return _google_oauth_callback(jarvis, path)
    if clean == "/api/speech/transcribe":
        return _transcribe(jarvis, body)  # raw audio in, JSON out (live STT ear)
    if clean.startswith("/api/"):
        command = clean[len("/api/") :].strip("/") or "state"
        payload = _parse(body) if method == "POST" else {}
        result = handle(jarvis, command, payload)
        status = 400 if "error" in result else 200
        return Response(status, "application/json; charset=utf-8", _json(result))
    return Response(404, "application/json; charset=utf-8", _json({"error": f"not found: {clean}"}))
