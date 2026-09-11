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
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from jarvis.jarvis import Jarvis

from jarvis.interface._state import snapshot
from jarvis.interface._conversation import _say, stream_say, StreamEvent
from jarvis.interface._cognition import (
    _explain,
    _reflect,
    _introspect,
    _wonder,
    _rest,
    _energy_budget,
    _deliberation,
    _tunables,
    _learn,
    _greeting,
    _belief,
    _state,
)
from jarvis.interface._providers import (
    _perceiver,
    _provider_health,
    _reasoner,
    _provider_reset,
    _embeddings,
    _speech,
)
from jarvis.interface._external import _external, _research, _compare
from jarvis.interface._crud import (
    _calendar,
    _google_calendar,
    _tasks,
    _notes,
    _mail,
    _documents,
)
from jarvis.interface._recall import _recall, _conversations
from jarvis.interface._workflow import _workflow
from jarvis.interface._capabilities import _capability, _tool

# Re-export for backward compatibility with tests that patch llm_config_store.
from jarvis.infrastructure import llm_config_store  # noqa: F401

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
