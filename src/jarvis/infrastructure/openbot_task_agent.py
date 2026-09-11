"""OpenBotTaskAgent: a TaskAgent backed by OpenBot's AG-UI execution seam (D7, D8).

The adapter translates a bounded Jarvis task into an AG-UI run request,
collects the streamed events, and maps them onto a ``TaskResult`` (D6: the
truth comes from the observed execution, not the model's closing words).

Boundaries held here:

* The transport is injectable and offline-testable (D8).
* The adapter does NOT decide whether to act; the task and any upstream
  approval arrive already determined (revised D1).
* The adapter does NOT mutate Jarvis memory, beliefs, or capabilities.
  It produces a ``TaskResult`` whose ``provenance`` records the delegation.
* Tool calls returned by the AG-UI endpoint are noted but NOT executed by
  the adapter itself -- execution through OpenBot's governed gateway is
  OpenBot's responsibility.  The ``TaskResult`` records them as evidence.
* Failures (connection, timeout, protocol, refusal) are surfaced honestly
  as ``success=False`` with a clear error string -- never converted into
  a fabricated success (Vision §37).
"""

from __future__ import annotations

from jarvis.domain.value_objects.task_result import TaskResult
from jarvis.infrastructure.openbot_transport import (
    HttpOpenBotTransport,
    OpenBotError,
    OpenBotRunResult,
    OpenBotToolDef,
    OpenBotTransport,
)
from jarvis.infrastructure.provider_settings import OpenBotSettings

_PROVIDER = "openbot"


class OpenBotTaskAgent:
    """A :class:`TaskAgent` that delegates bounded tasks to OpenBot via AG-UI.

    The adapter is thin: it translates the task, invokes the transport, and
    maps the result.  It carries no planner, no memory, no belief system, and
    no policy engine -- those stay in the Jarvis core (D1, D6, §37).
    """

    def __init__(
        self,
        transport: OpenBotTransport,
        *,
        tools: tuple[OpenBotToolDef, ...] = (),
        timeout: float = 120.0,
    ) -> None:
        self._transport = transport
        self._tools = tools
        self._timeout = timeout
        self._last_result: OpenBotRunResult | None = None

    @property
    def transport(self) -> OpenBotTransport:
        return self._transport

    @property
    def last_result(self) -> OpenBotRunResult | None:
        """The raw AG-UI result of the most recent run (for observability)."""
        return self._last_result

    def run_task(self, task: str) -> TaskResult:
        """Send ``task`` to OpenBot and return its material outcome (D6)."""
        text = task.strip()
        if not text:
            return TaskResult(
                task=task,
                summary="no task provided",
                success=False,
            )
        if not self._transport.is_reachable():
            return TaskResult(
                task=task,
                summary=f"{_PROVIDER}: endpoint unreachable",
                success=False,
            )
        try:
            result = self._transport.run_task(
                text,
                tools=self._tools,
                timeout=self._timeout,
            )
        except OpenBotError as exc:
            return TaskResult(
                task=task,
                summary=f"{_PROVIDER}: {exc}",
                success=False,
            )
        self._last_result = result
        return _map_result(task, result)


def _map_result(task: str, result: OpenBotRunResult) -> TaskResult:
    """Map an AG-UI ``OpenBotRunResult`` onto a Jarvis ``TaskResult`` (D6).

    The truth comes from the observed execution events, not from whatever
    the model's closing words said.  A run that returned text but never
    finished is reported as partial.
    """
    if result.error:
        return TaskResult(
            task=task,
            summary=f"{_PROVIDER} error: {result.error}",
            success=False,
        )
    if not result.finished:
        return TaskResult(
            task=task,
            summary=f"{_PROVIDER} partial: {result.text or 'no output'}",
            success=False,
        )
    parts: list[str] = []
    if result.text:
        parts.append(result.text.strip())
    if result.tool_calls:
        tc_summary = "; ".join(
            f"{tc.name}({', '.join(f'{k}={v}' for k, v in tc.arguments.items())})"
            for tc in result.tool_calls
        )
        parts.append(f"tool calls: {tc_summary}")
    summary = " ".join(parts) if parts else f"{_PROVIDER}: no output"
    return TaskResult(
        task=task,
        summary=summary,
        success=True,
    )


def build_openbot_task_agent(
    settings: OpenBotSettings | None = None,
    *,
    endpoint: str | None = None,
    agent_token: str | None = None,
    timeout: float | None = None,
    tools: tuple[OpenBotToolDef, ...] = (),
) -> OpenBotTaskAgent | None:
    """Build the OpenBot adapter from settings (or explicit args), or ``None``.

    Returns ``None`` when no endpoint is configured so an offline Jarvis stays
    fully functional (D8).  The transport is constructed but lazy: reaching the
    endpoint happens only when a task actually runs.
    """
    if settings is None:
        settings = _from_env()
    if settings is None:
        return None
    ep = endpoint or settings.endpoint
    token = agent_token or settings.agent_token
    eff_timeout = timeout if timeout is not None else settings.timeout
    if not ep:
        return None
    return OpenBotTaskAgent(
        _HttpTransport(ep, agent_token=token, default_timeout=eff_timeout),
        tools=tools,
        timeout=eff_timeout,
    )


def _from_env() -> OpenBotSettings | None:
    """Read OpenBot settings from the environment, or ``None`` when unconfigured."""
    import os

    from jarvis.infrastructure.env_settings import openbot_settings_from_env

    return openbot_settings_from_env(os.environ)


class _HttpTransport:
    """Lazy stdlib HTTP transport that avoids importing at module level."""

    def __init__(
        self,
        endpoint: str,
        *,
        agent_token: str | None = None,
        default_timeout: float = 120.0,
    ) -> None:
        self._endpoint = endpoint
        self._agent_token = agent_token
        self._default_timeout = default_timeout
        self._inner: HttpOpenBotTransport | None = None

    def _resolve(self) -> HttpOpenBotTransport:
        if self._inner is None:
            from jarvis.infrastructure.openbot_transport import (
                HttpOpenBotTransport,
            )

            self._inner = HttpOpenBotTransport(
                self._endpoint,
                agent_token=self._agent_token,
                timeout=self._default_timeout,
            )
        return self._inner

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def is_reachable(self) -> bool:
        return self._resolve().is_reachable()

    def run_task(
        self,
        task: str,
        *,
        tools: tuple[OpenBotToolDef, ...] = (),
        timeout: float = 120.0,
    ) -> OpenBotRunResult:
        return self._resolve().run_task(task, tools=tools, timeout=timeout)
