"""The command center's socket: a thin stdlib HTTP wrapper (Vision §30, §40).

All the decisions live in :mod:`jarvis.interface.command_center` as pure functions;
this module only binds a port, reads a request, calls :func:`route`, and writes the
bytes back. No framework, no dependency — just :mod:`http.server`. Building the app
picks the perceiver from the environment (a real language model when ``JARVIS_LLM_*``
is configured, the keyword perceiver otherwise), and optionally gives Jarvis a
persistent memory under a home directory so the companion remembers across restarts.
"""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from jarvis.domain.perception.perception_source import PerceptionSource
from jarvis.infrastructure.env_settings import language_model_from_env
from jarvis.infrastructure.json_belief_store import JsonBeliefStore
from jarvis.infrastructure.json_episode_store import JsonEpisodeStore
from jarvis.infrastructure.json_refutation_store import JsonRefutationStore
from jarvis.infrastructure.llm_perception import LlmPerception
from jarvis.interface.command_center import Response, route
from jarvis.jarvis import Jarvis

_OFFLINE_PROVIDERS = frozenset({"", "scripted", "stub"})


def _perception_from_env() -> PerceptionSource | None:
    """An LLM-backed perceiver when ``JARVIS_LLM_*`` names a real provider, else None
    (so Jarvis uses its default keyword perceiver — no LLM in the judgment, §38).
    """
    provider = os.environ.get("JARVIS_LLM_PROVIDER", "").strip().lower()
    if provider in _OFFLINE_PROVIDERS:
        return None
    return LlmPerception(language_model_from_env())


def create_jarvis(home: str | Path | None = None) -> Jarvis:
    """Build the Jarvis the command center drives (Vision §3, §32).

    With ``home`` set, every store is wired to JSON files under that directory so the
    companion remembers across restarts; otherwise memory is in-process. The
    perceiver comes from the environment either way.
    """
    perception = _perception_from_env()
    if home is None:
        return Jarvis(perception=perception)
    base = Path(home)
    base.mkdir(parents=True, exist_ok=True)
    return Jarvis(
        beliefs=JsonBeliefStore(base / "beliefs.json"),
        episodes=JsonEpisodeStore(base / "episodes.json"),
        companion_store=JsonBeliefStore(base / "companion.json"),
        actions_store=JsonBeliefStore(base / "actions.json"),
        reversibility_store=JsonBeliefStore(base / "reversibility.json"),
        goals_store=JsonBeliefStore(base / "goals.json"),
        subgoals_store=JsonBeliefStore(base / "subgoals.json"),
        refutations_store=JsonRefutationStore(base / "refutations.json"),
        perception=perception,
    )


class _Handler(BaseHTTPRequestHandler):
    """Moves bytes only; every decision is delegated to :func:`route`."""

    jarvis: ClassVar[Jarvis]

    def do_GET(self) -> None:  # noqa: N802 (stdlib dispatch name)
        self._respond(route(self.jarvis, "GET", self.path, b""))

    def do_POST(self) -> None:  # noqa: N802 (stdlib dispatch name)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length > 0 else b""
        self._respond(route(self.jarvis, "POST", self.path, body))

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


def run(host: str = "127.0.0.1", port: int = 8765, home: str | Path | None = None) -> None:
    """Serve the command center until interrupted (Ctrl-C)."""
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
