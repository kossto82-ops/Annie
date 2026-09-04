"""The command center's socket: a thin stdlib HTTP wrapper (Vision §30, §40).

All the decisions live in :mod:`jarvis.interface.command_center` as pure functions;
this module only binds a port, reads a request, calls :func:`route`, and writes the
bytes back. No framework, no dependency — just :mod:`http.server`. Building the app
picks the perceiver from the environment (a real language model when ``JARVIS_LLM_*``
is configured, the keyword perceiver otherwise), and optionally gives Jarvis a
persistent memory under a home directory so the companion remembers across restarts.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from jarvis.domain.perception.perception_source import PerceptionSource
from jarvis.domain.retrieval.external_source import ExternalSource
from jarvis.domain.retrieval.mail_source import MailBox
from jarvis.domain.retrieval.notes_store import NotesStore
from jarvis.domain.retrieval.research_source import ResearchSource
from jarvis.domain.retrieval.task_agent_source import TaskAgent
from jarvis.domain.services.model_compare import ModelComparator
from jarvis.infrastructure.agent_reach_source import build_web_source, llm_search_from_model
from jarvis.infrastructure.calendar_store import build_calendar_store
from jarvis.infrastructure.env_settings import settings_from_env
from jarvis.infrastructure.google_calendar import build_google_calendar_store
from jarvis.infrastructure.json_belief_store import JsonBeliefStore
from jarvis.infrastructure.json_episode_store import JsonEpisodeStore
from jarvis.infrastructure.json_refutation_store import JsonRefutationStore
from jarvis.infrastructure.language_model import LanguageModel
from jarvis.infrastructure.language_model_registry import build_language_model
from jarvis.infrastructure.llm_config_store import load_env_file
from jarvis.infrastructure.mail_source import build_mail_source
from jarvis.infrastructure.model_compare_source import build_model_compare_source
from jarvis.infrastructure.notes_store import build_notes_store
from jarvis.infrastructure.odysseus_search_source import build_odysseus_search_source
from jarvis.infrastructure.perceiver_factory import (
    build_embedder,
    companion_perceiver_from_settings,
    perceiver_from_settings,
    reasoner_from_settings,
    renderer_from_settings,
)
from jarvis.infrastructure.provider_settings import ProviderSettings
from jarvis.infrastructure.speech_perception import EchoSpeechPerception
from jarvis.infrastructure.task_agent_source import build_default_task_agent
from jarvis.infrastructure.task_scheduler import build_task_scheduler
from jarvis.interface.command_center import Response, parse_body, route, stream_say
from jarvis.jarvis import Jarvis

EdgeSources = tuple[
    ExternalSource | None,
    ResearchSource | None,
    ModelComparator | None,
    MailBox | None,
    TaskAgent | None,
    NotesStore | None,
]


def _build_edge(settings: ProviderSettings) -> EdgeSources:
    """Build the live edge sources (Odysseus, D7) from the environment.

    Each builder returns ``None`` when its prerequisite is missing, so a Jarvis with
    none of them wired keeps working fully offline (D8). Web *read* uses the free Jina
    Reader; web *search* runs through the configured chat model (e.g. the local
    OmniRoute gateway, so no JINA_API_KEY is needed) when a real provider is set.
    """
    import os
    from dataclasses import replace

    search_model = (
        build_language_model(settings)
        if settings.model and settings.provider not in _OFFLINE_PROVIDERS
        else None
    )
    web_source = build_web_source(
        llm_search_from_model(search_model) if search_model is not None else None
    )
    research_source = build_odysseus_search_source()
    # Blind model comparison uses the same gateway with a comma-separated model list,
    # so the connected providers (via OmniRoute's auto/* routing) can be compared.
    compare_models: dict[str, LanguageModel] = {}
    for raw in (os.environ.get("JARVIS_COMPARE_MODELS") or "").split(","):
        name = raw.strip()
        if name:
            compare_models[name] = build_language_model(replace(settings, model=name))
    model_compare = build_model_compare_source(compare_models or None)
    mail_source = build_mail_source()
    task_agent = build_default_task_agent()
    notes_store = build_notes_store()
    return (
        web_source,
        research_source,
        model_compare,
        mail_source,
        task_agent,
        notes_store,
    )


_OFFLINE_PROVIDERS = frozenset({"", "scripted", "stub", "keyword"})


def create_jarvis(home: str | Path | None = None) -> Jarvis:
    """Build the Jarvis the command center drives (Vision §3, §5, §32).

    With ``home`` set, every store is wired to JSON files under that directory so the
    companion remembers across restarts; otherwise memory is in-process. Both perceivers
    — the world one and the relational one — come from ``JARVIS_LLM_*`` (an LLM pair for
    a real provider, the keyword rule + silent companion otherwise). Either can still be
    switched at runtime from the command center.

    The edge capabilities (web, deep research, model comparison, email, delegation,
    notes) are wired from the environment when configured and stay ``None`` otherwise,
    so the same Jarvis works fully offline. ``can_do`` reflects which are live.
    """
    settings = settings_from_env()
    perception: PerceptionSource = perceiver_from_settings(settings)
    companion_perception = companion_perceiver_from_settings(settings)
    reasoner = reasoner_from_settings(settings)
    external_source, research_source, model_compare, mail_source, task_agent, notes_store = (
        _build_edge(settings)
    )
    if home is None:
        jarvis = Jarvis(
            perception=perception,
            companion_perception=companion_perception,
            enable_recall=True,
            reasoner=reasoner,
            external_source=external_source,
            research_source=research_source,
            model_compare=model_compare,
            mail_source=mail_source,
            task_agent=task_agent,
            notes_store=notes_store,
        )
    else:
        base = Path(home)
        base.mkdir(parents=True, exist_ok=True)
        jarvis = Jarvis(
            beliefs=JsonBeliefStore(base / "beliefs.json"),
            episodes=JsonEpisodeStore(base / "episodes.json"),
            companion_store=JsonBeliefStore(base / "companion.json"),
            actions_store=JsonBeliefStore(base / "actions.json"),
            reversibility_store=JsonBeliefStore(base / "reversibility.json"),
            goals_store=JsonBeliefStore(base / "goals.json"),
            subgoals_store=JsonBeliefStore(base / "subgoals.json"),
            refutations_store=JsonRefutationStore(base / "refutations.json"),
            perception=perception,
            companion_perception=companion_perception,
            enable_recall=True,
            reasoner=reasoner,
            external_source=external_source,
            research_source=research_source,
            model_compare=model_compare,
            mail_source=mail_source,
            task_agent=task_agent,
            notes_store=notes_store,
        )
    jarvis.set_voice(renderer_from_settings(settings))  # reply in the user's language
    # The ear (the input mirror of the mouth): the command center's browser does
    # speech-to-text with the Web Speech API, so Jarvis's default ear passes the
    # already-transcribed text straight through. This is what makes the "perceive
    # speech" capability live and earned.
    jarvis.set_speech_perception(EchoSpeechPerception())
    # Upgrade recall to meaning-based when an embedder is configured (e.g. bge-m3 on a
    # local ollama), independent of the chat provider; otherwise recall stays lexical.
    embedder = build_embedder()
    if embedder is not None:
        jarvis.enable_embedding_recall(embedder)
    # A connected Google Calendar becomes the live calendar store (Odysseus #6, live
    # edge). Opt-in: only when a refresh token is saved does it replace the local store.
    google_store = build_google_calendar_store()
    if google_store is not None:
        jarvis.set_calendar_store(google_store)
    else:
        # Otherwise the local file-backed calendar supports `manage calendar` when its
        # root is configured (Odysseus #6). This is what makes the console buttons work.
        local_calendar = build_calendar_store()
        if local_calendar is not None:
            jarvis.set_calendar_store(local_calendar)
    # And the local task scheduler backs `manage tasks` when its root is configured
    # (Odysseus #7). Google Tasks is intentionally not mapped (contract mismatch).
    local_tasks = build_task_scheduler()
    if local_tasks is not None:
        jarvis.set_task_scheduler(local_tasks)
    return jarvis


class _Handler(BaseHTTPRequestHandler):
    """Moves bytes only; every decision is delegated to :func:`route`."""

    jarvis: ClassVar[Jarvis]

    def do_GET(self) -> None:  # noqa: N802 (stdlib dispatch name)
        self._respond(route(self.jarvis, "GET", self.path, b""))

    def do_POST(self) -> None:  # noqa: N802 (stdlib dispatch name)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length > 0 else b""
        if self.path.split("?", 1)[0].rstrip("/") == "/api/stream/say":
            self._stream_say(body)
        else:
            self._respond(route(self.jarvis, "POST", self.path, body))

    def _stream_say(self, body: bytes) -> None:
        """Stream a `say` turn as newline-delimited JSON events, flushed as they arrive.

        The reply appears token by token instead of all at once. No Content-Length: the
        body streams until the handler returns and the connection closes.
        """
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            for event, data in stream_say(self.jarvis, parse_body(body)):
                line = json.dumps({"event": event, "data": data}).encode("utf-8") + b"\n"
                self.wfile.write(line)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the client navigated away mid-stream; nothing to do

    def _respond(self, response: Response) -> None:
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        self.wfile.write(response.body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silent by default; the control center is the surface, not the console."""


def make_handler(jarvis: Jarvis) -> type[BaseHTTPRequestHandler]:
    """A request-handler class bound to one Jarvis (each server has its own)."""

    class JarvisHandler(_Handler):
        pass

    JarvisHandler.jarvis = jarvis
    return JarvisHandler


def create_server(
    jarvis: Jarvis, host: str = "127.0.0.1", port: int = 8765
) -> ThreadingHTTPServer:
    """A threading HTTP server bound to ``host:port`` serving the command center.

    Port ``0`` binds an ephemeral port (read it back from ``server.server_address``);
    the caller owns the lifecycle (``serve_forever`` / ``shutdown``).
    """
    return ThreadingHTTPServer((host, port), make_handler(jarvis))


def run(host: str = "127.0.0.1", port: int = 8765, home: str | Path | None = "./.jarvis") -> None:
    """Serve the command center until interrupted (Ctrl-C).

    Persistence is on by default: memory lives under ``./.jarvis`` so the companion
    remembers across restarts. Pass ``home=None`` (or an empty ``JARVIS_HOME``) for an
    in-memory session that forgets on exit.
    """
    # Resume a saved provider/model/key so a restart keeps whatever was configured in
    # the panel (the read-back half of the .env persistence). Real env vars still win.
    load_env_file()
    jarvis = create_jarvis(home)
    server = create_server(jarvis, host, port)
    bound_host, bound_port = server.server_address[0], server.server_address[1]
    print(f"Jarvis command center on http://{bound_host}:{bound_port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping the command center.")
    finally:
        server.shutdown()
        server.server_close()
