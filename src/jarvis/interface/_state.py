"""Snapshot/state assembly — builds the live model the UI renders after every turn."""

from __future__ import annotations

import os
import shutil
import time

from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.services.capability_scout import catalog
from jarvis.infrastructure import google_calendar
from jarvis.infrastructure.perceiver_factory import (
    available_providers,
    describe,
    saved_models,
)
from jarvis.interface._shared import (
    _OFFLINE_PERCEIVERS,
    _companion_name,
    _recall_block,
)
from jarvis.jarvis import Jarvis

# A reply the UI can render and (optionally) speak; some commands add extra fields.
Reply = dict[str, object]


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


def _workflows_block_lazy(jarvis: Jarvis) -> list[Reply]:
    """Lazy wrapper to avoid circular import with _workflow at module level."""
    from jarvis.interface._workflow import _workflows_block

    return _workflows_block(jarvis)


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
        "workflows": _workflows_block_lazy(jarvis),
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



