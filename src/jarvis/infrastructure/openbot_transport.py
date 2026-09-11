"""OpenBot transport: the sync seam over one AG-UI session (D7, D8).

OpenBot communicates through the AG-UI (Agent-User Interaction) protocol over
HTTP/SSE.  This module defines the *domain-safe* shapes the adapter works with
and a sync transport seam that is offline-testable without any network or the
``ag-ui-protocol`` package.

* :class:`OpenBotTransport` -- the sync seam.  ``run_task`` sends a task to an
  AG-UI endpoint and returns the collected events.  Predictable and fakeable.
* :class:`HttpOpenBotTransport` -- a live HTTP/SSE implementation using only
  ``urllib`` (stdlib).  Imported lazily by the composition root; never forces a
  dependency.
* :class:`FakeOpenBotTransport` -- a canned transport for offline tests.

The domain stays clean: this module never decides *whether* to act; it only
makes an AG-UI call possible and observable.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, cast, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Domain-safe value objects (no AG-UI SDK types leak here)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenBotToolDef:
    """A tool the adapter declares to the AG-UI endpoint.

    Mirrors ``ag_ui.core.Tool`` shape (name, description, parameters JSON
    schema) but uses only stdlib types so the domain stays clean.
    """

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenBotToolCall:
    """A tool call requested by the AG-UI endpoint (model-driven)."""

    tool_call_id: str
    name: str
    arguments: dict[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenBotRunResult:
    """The collected outcome of one AG-UI run over an endpoint.

    Events are classified so the adapter can build a ``TaskResult`` without
    parsing raw JSON.
    """

    text: str = ""
    tool_calls: tuple[OpenBotToolCall, ...] = ()
    error: str = ""
    finished: bool = False
    run_id: str = ""
    thread_id: str = ""


class OpenBotError(RuntimeError):
    """The transport hit a connection, protocol or timeout error."""


# ---------------------------------------------------------------------------
# Transport seam (sync, offline-testable)
# ---------------------------------------------------------------------------


@runtime_checkable
class OpenBotTransport(Protocol):
    """The sync seam over one live AG-UI session (D8).

    ``run_task`` sends a bounded task to an AG-UI endpoint and returns the
    collected events.  Raises ``OpenBotError`` on connection, protocol or
    timeout failure so the adapter can surface an honest failure.
    """

    @property
    def endpoint(self) -> str: ...

    def is_reachable(self) -> bool: ...

    def run_task(
        self,
        task: str,
        *,
        tools: tuple[OpenBotToolDef, ...] = (),
        timeout: float = 120.0,
    ) -> OpenBotRunResult: ...


# ---------------------------------------------------------------------------
# HTTP implementation (stdlib only -- no AG-UI SDK needed)
# ---------------------------------------------------------------------------


def _encode_sse_request(
    task: str,
    *,
    run_id: str,
    thread_id: str,
    tools: tuple[OpenBotToolDef, ...],
    agent_token: str | None = None,
) -> bytes:
    """Build the JSON body for a ``POST /ag-ui`` request."""
    messages = [
        {
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": task,
        }
    ]
    tool_defs = [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters or None,
        }
        for t in tools
    ]
    body: dict[str, Any] = {
        "threadId": thread_id,
        "runId": run_id,
        "messages": messages,
        "tools": tool_defs,
        "context": [],
        "forwardedProps": None,
    }
    return json.dumps(body).encode("utf-8")


def _parse_sse_events(raw: str) -> list[dict[str, Any]]:
    """Parse an SSE text stream into a list of AG-UI event dicts.

    SSE format: lines starting with ``data: `` contain JSON; blank lines
    separate events.  Other lines (``:``, ``event:``, ``id:``) are ignored.
    """
    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if line.startswith("data: "):
            payload = line[6:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
    return events


class HttpOpenBotTransport:
    """An :class:`OpenBotTransport` backed by a live AG-UI HTTP/SSE endpoint.

    Uses only ``urllib`` (stdlib) so no SDK or third-party HTTP client is
    required.  The ``agent_token`` (``MANAGED_AGENT_TOKEN``) is sent as the
    ``x-openbot-agent-token`` header when the server requires it.

    ``pydantic-ai`` is not imported here; this is pure stdlib.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        agent_token: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._agent_token = agent_token
        self._timeout = timeout

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def is_reachable(self) -> bool:
        """Ping ``GET /health`` to check liveness."""
        try:
            req = Request(
                f"{self._endpoint}/health",
                method="GET",
            )
            with urlopen(req, timeout=5) as resp:  # noqa: S310
                return resp.status == 200
        except (HTTPError, URLError, OSError, TimeoutError):
            return False

    def run_task(
        self,
        task: str,
        *,
        tools: tuple[OpenBotToolDef, ...] = (),
        timeout: float | None = None,
    ) -> OpenBotRunResult:
        """Send a task to the AG-UI endpoint and collect SSE events."""
        run_id = str(uuid.uuid4())
        thread_id = str(uuid.uuid4())
        body = _encode_sse_request(
            task, run_id=run_id, thread_id=thread_id, tools=tools
        )
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if self._agent_token:
            headers["x-openbot-agent-token"] = self._agent_token
        req = Request(
            f"{self._endpoint}/ag-ui",
            data=body,
            headers=headers,
            method="POST",
        )
        effective_timeout = timeout if timeout is not None else self._timeout
        try:
            with urlopen(req, timeout=effective_timeout) as resp:  # noqa: S310
                raw = resp.read().decode("utf-8")
        except HTTPError as exc:
            raise OpenBotError(
                f"OpenBot returned HTTP {exc.code}: {exc.reason}"
            ) from exc
        except URLError as exc:
            raise OpenBotError(
                f"OpenBot unreachable: {exc.reason}"
            ) from exc
        except (TimeoutError, OSError) as exc:
            raise OpenBotError(
                f"OpenBot timeout or connection error: {exc}"
            ) from exc
        return _collect_result(
            _parse_sse_events(raw),
            run_id=run_id,
            thread_id=thread_id,
        )


def _collect_result(
    events: list[dict[str, Any]],
    *,
    run_id: str,
    thread_id: str,
) -> OpenBotRunResult:
    """Classify a list of parsed AG-UI events into an ``OpenBotRunResult``."""
    text_parts: list[str] = []
    tool_calls: list[OpenBotToolCall] = []
    error = ""
    finished = False
    current_tool_id = ""
    current_tool_name = ""
    current_tool_args = ""

    for event in events:
        etype = event.get("type", "")
        if etype == "TEXT_MESSAGE_CONTENT":
            delta = event.get("delta", "")
            if isinstance(delta, str):
                text_parts.append(delta)
        elif etype == "TOOL_CALL_START":
            current_tool_id = event.get("toolCallId", "")
            current_tool_name = event.get("toolCallName", "")
            current_tool_args = ""
        elif etype == "TOOL_CALL_ARGS":
            delta = event.get("delta", "")
            if isinstance(delta, str):
                current_tool_args += delta
        elif etype == "TOOL_CALL_END":
            if current_tool_id and current_tool_name:
                args = _parse_tool_args(current_tool_args)
                tool_calls.append(
                    OpenBotToolCall(
                        tool_call_id=current_tool_id,
                        name=current_tool_name,
                        arguments=args,
                    )
                )
            current_tool_id = ""
            current_tool_name = ""
            current_tool_args = ""
        elif etype == "RUN_FINISHED":
            finished = True
        elif etype == "RUN_ERROR":
            error = event.get("message", "OpenBot run error")

    return OpenBotRunResult(
        text="".join(text_parts),
        tool_calls=tuple(tool_calls),
        error=error,
        finished=finished,
        run_id=run_id,
        thread_id=thread_id,
    )


def _parse_tool_args(raw: str) -> dict[str, str]:
    """Best-effort JSON parse of accumulated tool-call arguments."""
    if not raw.strip():
        return {}
    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
    if not isinstance(parsed, dict):
        return {"_raw": raw}
    items = cast(dict[str, object], parsed)
    return {key: str(value) for key, value in items.items()}


# ---------------------------------------------------------------------------
# Fake transport for offline tests
# ---------------------------------------------------------------------------


class FakeOpenBotTransport:
    """A canned :class:`OpenBotTransport` for offline tests (D8).

    Configure canned results per task prefix or let the default succeed.
    """

    def __init__(
        self,
        *,
        default_result: OpenBotRunResult | None = None,
        reachable: bool = True,
    ) -> None:
        self._default_result = default_result or OpenBotRunResult(
            text="Done.",
            finished=True,
        )
        self._reachable = reachable
        self._calls: list[str] = []

    @property
    def endpoint(self) -> str:
        return "fake://openbot"

    @property
    def calls(self) -> list[str]:
        return list(self._calls)

    def is_reachable(self) -> bool:
        return self._reachable

    def run_task(
        self,
        task: str,
        *,
        tools: tuple[OpenBotToolDef, ...] = (),
        timeout: float = 120.0,
    ) -> OpenBotRunResult:
        self._calls.append(task)
        return self._default_result
