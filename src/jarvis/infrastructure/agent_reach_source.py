"""AgentReachSource: an ExternalSource backed by the Agent-Reach capability.

Agent-Reach is a *capability layer* in front of the Internet: it installs, health-
checks, and routes to real CLIs/APIs (Jina Reader for web reads, Exa for semantic
search, yt-dlp, gh, ...). Jarvis treats it as an :class:`ExternalSource` -- fetched
documents come back with provenance, and Jarvis (not Agent-Reach) decides and
reasons over them (Vision §38).

Network stays at the edge (Vision §38, D8): the actual HTTP fetch is a `transport`
callable, injectable so offline tests never touch the network and run
deterministically.

The package itself is not required: web *reads* use the free Jina Reader endpoint and
web *search* can run through an ``llm_search`` backend (e.g. the configured chat model
on a local OmniRoute gateway, so no JINA_API_KEY is needed). When the optional
``agent_reach`` package is installed, its doctor report augments
:meth:`AgentReachSource.available_channels`.
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
from jarvis.infrastructure.language_model import LanguageModel


class AgentReachUnavailable(RuntimeError):
    """The agent-reach package is not installed (kept for backward compatibility).

    The package is no longer required for read/search; this exception is retained so
    callers that handled it keep working, but the source now reports its own channels
    instead of raising.
    """


Transport = Callable[[str, Mapping[str, str], bytes, float], bytes]

# A web *search* adapter: given a query, returns a compact Markdown/plain summary
# of what was found. The concrete backend is injectable so the network stays at the
# edge and offline tests hand it a stub (D7, D8). The default backend asks an
# OpenAI-compatible chat endpoint (e.g. the local OmniRoute gateway) -- a configured
# model acts as the search producer -- so search needs no dedicated web-search API
# key (no JINA_API_KEY). It is honest about what it is: a model-produced finding
# summary with source "web_search", not a claim of live page retrieval.
SearchFn = Callable[[str], str]


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
    channel); ``search`` uses a configured web-search backend. By default that backend
    is ``llm_search`` -- an injectable callable (e.g. a chat model on the local
    OmniRoute gateway) that answers "what's on the web about X" — so search needs no
    dedicated web-search API key (no JINA_API_KEY). When ``llm_search`` is absent but
    a ``JINA_API_KEY`` is set, it falls back to Jina's search endpoint; with neither,
    search raises a clear error. ``available_channels`` mirrors Agent-Reach's doctor
    report.
    """

    def __init__(
        self,
        *,
        config: Any | None = None,
        timeout: float = 30.0,
        transport: Transport | None = None,
        environ: Mapping[str, str] | None = None,
        llm_search: SearchFn | None = None,
    ) -> None:
        self._config = config
        self._timeout = timeout
        self._transport: Transport = transport or self._default_transport
        self._llm_search: SearchFn | None = llm_search
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

        The preferred backend is ``llm_search`` (an injectable chat model on the local
        OmniRoute gateway), which needs no dedicated web-search API key. When that is
        absent, Jina's search endpoint is used if ``JINA_API_KEY`` is set (``read``, via
        Jina Reader, is free). With neither, this raises a clear error rather than
        silently returning nothing -- so Jarvis can tell "I cannot search yet" apart
        from "nothing was found". The returned content is Markdown/plain text.
        """
        if self._llm_search is not None:
            try:
                text = self._llm_search(query)
            except Exception as exc:
                raise RuntimeError(f"web search failed for {query!r}: {exc}") from exc
            if not text.strip():
                return ()
            return (
                self._document(text, source="web_search", url=None, title=query[:80]),
            )
        if self._jina_search_key is None:
            raise RuntimeError(
                "no web-search backend configured; set JARVIS_LLM_* to point at an "
                "OmniRoute gateway (or set JINA_API_KEY) to enable Jarvis's Internet "
                "search capability"
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
        """Report the fetch/search channels this source can actually use.

        The web *read* channel (Jina Reader, zero-config) is reported as ``ok`` whenever
        the source is built; the *search* channel is ``ok`` when a search backend is
        configured (an ``llm_search`` -- e.g. the OmniRoute gateway -- or a
        ``JINA_API_KEY``) and ``off`` otherwise. When the optional ``agent_reach``
        package is importable, its doctor report is appended for the richer channels,
        but it is never required -- a Jarvis without the package still reports its own
        channels (D7/D8).
        """
        statuses: list[ChannelStatus] = [
            ChannelStatus(
                name="web",
                status="ok",
                message="Jina Reader (zero-config web reads)",
                active_backend="jina-reader",
            )
        ]
        search_backend: str | None = None
        if self._llm_search is not None:
            search_backend = "llm-search"
        elif self._jina_search_key is not None:
            search_backend = "jina-search"
        statuses.append(
            ChannelStatus(
                name="search",
                status="ok" if search_backend is not None else "off",
                message=(
                    "web search via configured backend"
                    if search_backend is not None
                    else "no web-search backend configured"
                ),
                active_backend=search_backend,
            )
        )
        try:
            doctor_mod: Any = importlib.import_module("agent_reach.doctor")
            config_mod: Any = importlib.import_module("agent_reach.config")
        except Exception:  # pragma: no cover - agent-reach package is optional
            return tuple(statuses)
        config_cls: Any = config_mod.Config
        config = self._config or config_cls()
        check_all = cast(
            "Callable[[Any], dict[str, Any]]", doctor_mod.check_all
        )
        results = check_all(config)
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


def build_web_source(
    llm_search: SearchFn | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport: Transport | None = None,
) -> AgentReachSource | None:
    """Build the Internet source without requiring the optional ``agent_reach`` package.

    The web *read* path uses Jina Reader (zero config, free) and the *search* path uses
    ``llm_search`` (e.g. a chat model on the local OmniRoute gateway), so neither needs
    the agent-reach package or a dedicated web-search API key. ``None`` only when there
    is no search backend at all *and* no JINA_API_KEY -- i.e. Jarvis is genuinely
    confined to reads and cannot search, in which case the composition root keeps it
    offline rather than advertising a half-capability.
    """
    env = environ if environ is not None else os.environ
    jina_key = (env.get("JINA_API_KEY") or "").strip() or None
    if llm_search is None and jina_key is None:
        return None
    # Pass the environment as-is: the source reads JINA_API_KEY itself when present,
    # and uses llm_search first when wired -- either supports the web capability live.
    return AgentReachSource(transport=transport, environ=env, llm_search=llm_search)


# Prompt that turns a chat model into a web-search *adapter*. It asks the model to
# return a compact, factual summary of what a web search for the query would surface —
# the model is the search producer (its web-connected routes, when OmniRoute fronts
# one), never a decision-maker. Kept as a constant so it is easy to see and tune.
_SEARCH_SYSTEM_PROMPT = (
    "You are a web-search adapter. Answer with a short, factual summary of what a "
    "live web search for the user's query would return. Prefer concrete, checkable "
    "points (who, what, when, where) over opinion. If you have no reliable outside "
    "information for the query, say so plainly rather than inventing it. Return only "
    "the summary text, no preamble."
)


def llm_search_from_model(
    model: LanguageModel, *, prompt: str = _SEARCH_SYSTEM_PROMPT
) -> SearchFn:
    """Wrap a :class:`LanguageModel` as an ``llm_search`` backend for the web source.

    This is the wiring that lets search run through an existing chat endpoint (e.g. the
    local OmniRoute gateway) with no dedicated web-search key: ``search(query)`` asks
    the configured model to report what a web search would find, and returns that text
    as the search result. The model is only a search *adapter* (a producer of text to
    weigh later), never the decision-maker (Vision §38, D6).
    """

    def search(query: str) -> str:
        return model.complete(f"{prompt}\n\nSearch query: {query}")

    return search