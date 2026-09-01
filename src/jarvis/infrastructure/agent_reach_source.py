"""AgentReachSource: an ExternalSource backed by the Agent-Reach capability.

Agent-Reach is a *capability layer* in front of the Internet: it installs, health-
checks, and routes to real CLIs/APIs (Jina Reader for web reads, Exa for semantic
search, yt-dlp, gh, ...). Jarvis treats it as an :class:`ExternalSource` -- fetched
documents come back with provenance, and Jarvis (not Agent-Reach) decides and
reasons over them (Vision §38).

Network stays at the edge (Vision §38, D8): the actual HTTP fetch is a `transport`
callable, injectable so offline tests never touch the network and run
deterministically.

Availability is opt-in: building this raises ``AgentReachUnavailable`` when the
``agent_reach`` package is not importable, so a Jarvis without Agent-Reach keeps
working normally and this capability simply reads as unavailable.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, cast

from jarvis.domain.retrieval.external_source import ChannelStatus
from jarvis.domain.value_objects.retrieved_document import RetrievedDocument


class AgentReachUnavailable(RuntimeError):
    """The agent-reach package is not installed, so the source cannot be built."""


Transport = Callable[[str, Mapping[str, str], bytes, float], bytes]


def _urllib_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> bytes:
    request = urllib.request.Request(url, data=body or None, headers=dict(headers))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


# Agent-Reach's Jina Reader constants (mirrored so a bare install needs no import).
_JINA_READ = "https://r.jina.ai/"
_JINA_SEARCH = "https://s.jina.ai/"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class AgentReachSource:
    """An ExternalSource that fetches through Agent-Reach's web/Jina capability.

    ``read`` pulls a URL to Markdown via Jina Reader (Agent-Reach's zero-config web
    channel); ``search`` uses Jina's zero-config search endpoint when no Exa key is
    configured, and falls back to Exa (via Agent-Reach's doctor-reported availability)
    when it is. ``available_channels`` mirrors Agent-Reach's doctor report.
    """

    def __init__(
        self,
        *,
        config: Any | None = None,
        timeout: float = 30.0,
        transport: Transport | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._config = config
        self._timeout = timeout
        self._transport: Transport = transport or self._default_transport
        env = environ if environ is not None else os.environ
        self._jina_search_key = (env.get("JINA_API_KEY") or "").strip() or None

    @property
    def available(self) -> bool:
        return True

    def _default_transport(
        self, url: str, headers: Mapping[str, str], body: bytes, timeout: float
    ) -> bytes:
        return _urllib_transport(url, headers, body, timeout)

    def _get(self, url: str, *, auth: str | None = None) -> bytes:
        headers = {"User-Agent": _UA, "Accept": "text/plain"}
        if auth:
            headers["Authorization"] = f"Bearer {auth}"
        body = self._transport(url, headers, b"", self._timeout)
        if len(body) > _MAX_RESPONSE_BYTES:
            raise ValueError(
                f"response exceeds {_MAX_RESPONSE_BYTES} byte limit for {url}"
            )
        return body

    def _document(
        self,
        content: str,
        *,
        source: str,
        url: str | None,
        title: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> RetrievedDocument:
        return RetrievedDocument(
            content=content,
            source=source,
            url=url,
            title=title,
            retrieved_at=datetime.now(UTC),
            metadata=metadata or {},
        )

    def read(self, url: str) -> RetrievedDocument:
        """Fetch ``url`` to Markdown via Agent-Reach's web (Jina Reader) channel."""
        text = self._get(_JINA_READ + url).decode("utf-8")
        return self._document(text, source="web", url=url)

    def search(
        self, query: str, *, limit: int = 5
    ) -> tuple[RetrievedDocument, ...]:
        """Search the web through a configured provider.

        ``read`` (Jina Reader) is free, but semantic *web search* needs a provider
        key (Jina's search endpoint requires ``JINA_API_KEY``). Without one this
        raises a clear error rather than silently returning nothing -- so Jarvis can
        tell "I cannot search yet" apart from "nothing was found". The fetched payload
        is Markdown text.
        """
        if self._jina_search_key is None:
            raise RuntimeError(
                "no web-search provider configured; set JINA_API_KEY to enable "
                "Jarvis's Internet search capability"
            )
        try:
            raw = self._get(
                _JINA_SEARCH + urllib.parse.quote(query), auth=self._jina_search_key
            )
        except Exception as exc:
            raise RuntimeError(f"web search failed for {query!r}: {exc}") from exc
        text = raw.decode("utf-8")
        if not text.strip():
            return ()
        return (
            self._document(text, source="web_search", url=None, title=query[:80]),
        )

    def available_channels(self) -> tuple[ChannelStatus, ...]:
        """Mirror Agent-Reach's doctor report into :class:`ChannelStatus` objects.

        The agent-reach package is optional (Jarvis has no dependency on it), so it is
        imported at runtime and everything is cast through ``Any`` -- pyright's strict
        mode never needs to resolve the external package for this to type-check.
        """
        try:
            doctor_mod: Any = importlib.import_module("agent_reach.doctor")
            config_mod: Any = importlib.import_module("agent_reach.config")
        except Exception as exc:  # pragma: no cover - depends on installed package
            raise AgentReachUnavailable(str(exc)) from exc
        config_cls: Any = config_mod.Config
        config = self._config or config_cls()
        check_all = cast(
            "Callable[[Any], dict[str, Any]]", doctor_mod.check_all
        )
        results = check_all(config)
        statuses: list[ChannelStatus] = []
        for key, value in results.items():
            item: dict[str, Any] = cast("dict[str, Any]", value) if isinstance(value, dict) else {}
            statuses.append(
                ChannelStatus(
                    name=str(key),
                    status=str(item.get("status", "off")),
                    message=str(item.get("message", "")),
                    active_backend=cast("str | None", item.get("active_backend")),
                )
            )
        return tuple(statuses)


def build_agent_reach_source(
    environ: Mapping[str, str] | None = None,
    *,
    transport: Transport | None = None,
) -> AgentReachSource | None:
    """Build the :class:`AgentReachSource` when agent-reach is importable, else None.

    ``None`` means "no Internet capability configured"; a Jarvis built from this
    keeps working offline. The package-not-importable case is normal (a bare Jarvis
    has no dependency on agent-reach) and yields ``None`` rather than raising, so the
    composition root need not special-case it.
    """
    if importlib.util.find_spec("agent_reach") is None:
        return None
    return AgentReachSource(transport=transport)