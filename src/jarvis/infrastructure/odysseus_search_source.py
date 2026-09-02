"""SearXNGResearchSource: a ResearchSource backed by a SearXNG instance.

Deep research needs a place to actually *look*. This adapter routes one depth-scale
question to a self-hosted SearXNG JSON API and returns a structured
:class:`ResearchReport` -- a plain-language summary plus the cited documents behind
it (Vision §38).

The SearXNG request format (`GET /search?q=...&format=json&language=...&
categories=...&safesearch=...` -> ``{results: [{title, url, content}]}``) and result
mapping mirror Odysseus's ``services/search/providers.py::searxng_search_api``
(AGPL-3.0, odysseus-dev/odysseus), reimplemented here as a *self-contained
adapter*: this source does not import Odysseus's app, so it brings no httpx/bs4/
settings coupling into Jarvis and stays fully offline-testable (D7, D8).

The edge never decides anything (D6): this source only *gathers* search results and
describes what it found. The summary is an honest mechanical account of the
retrieval ("searched for X, N results"), never a verdict or a synthesis; turning
the report into standing evidence and weighing it is the cognitive core's job.

Network is injectable through a `transport` callable so offline tests run
deterministically and never touch the wire, mirroring :class:`AgentReachSource`.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, cast

from jarvis.domain.value_objects.research_report import ResearchReport
from jarvis.domain.value_objects.retrieved_document import RetrievedDocument

# -- Transport (mirrors AgentReachSource) -------------------------------------

Transport = Callable[[str, Mapping[str, str], bytes, float], bytes]

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_DEFAULT_INSTANCE = "https://searx.be"
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _urllib_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> bytes:
    request = urllib.request.Request(url, data=body or None, headers=dict(headers))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


# How many results one research round of a given depth asks for.
def _limit_for(depth: int, base: int = 5) -> int:
    if depth < 1:
        return base
    return base * depth


class SearXNGResearchSource:
    """Investigate a question in depth through a SearXNG instance.

    ``deep_research(query, depth=depth)`` runs ``depth`` rounds of search against
    the instance and returns a :class:`ResearchReport`: a mechanical summary of the
    retrieval plus the cited documents (each carrying SearXNG provenance), so the
    core can reason over *what was found* -- never a verdict.
    """

    def __init__(
        self,
        *,
        instance: str = _DEFAULT_INSTANCE,
        timeout: float = 15.0,
        transport: Transport | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._instance = (instance or _DEFAULT_INSTANCE).rstrip("/")
        self._timeout = timeout
        self._transport: Transport = transport or _urllib_transport
        self._safesearch = (environ or os.environ).get("SEARXNG_SAFESEARCH", "2")

    # -- ResearchSource -------------------------------------------------------

    def deep_research(self, query: str, *, depth: int = 1) -> ResearchReport:
        """Search the instance for ``query`` and return a report with cited documents.

        ``depth`` scales how many results one round gathers. Raises only on a real
        failure of the instance; an empty result returns an honest sparse report.
        """
        limit = _limit_for(depth)
        raw_results = self._search(query, limit)
        documents = tuple(
            RetrievedDocument(
                content=result.get("snippet") or result.get("title") or "",
                source="searxng",
                url=result.get("url"),
                title=result.get("title"),
                retrieved_at=datetime.now(UTC),
                metadata={"engine": "searxng", "instance": self._instance},
            )
            for result in raw_results
            if result.get("url")
        )
        summary = self._summarize(query, depth, documents)
        return ResearchReport(query=query, summary=summary, documents=documents)

    # -- Search plumbing ------------------------------------------------------

    def _search(self, query: str, limit: int) -> list[dict[str, str]]:
        """Run one SearXNG JSON API round for ``query``; return raw result dicts."""
        params = {
            "q": query,
            "format": "json",
            "language": "en",
            "categories": "general",
            "safesearch": self._safesearch,
        }
        url = f"{self._instance}/search?" + urllib.parse.urlencode(params)
        headers = {"User-Agent": _UA, "Accept": "application/json"}
        try:
            body = self._transport(url, headers, b"", self._timeout)
        except Exception as exc:
            raise RuntimeError(f"searxng search failed for {query!r}: {exc}") from exc
        if len(body) > _MAX_RESPONSE_BYTES:
            raise RuntimeError(
                f"searxng response exceeds {_MAX_RESPONSE_BYTES} bytes for {query!r}"
            )
        try:
            data: dict[str, Any] = json.loads(body.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(
                f"searxng returned unparseable JSON for {query!r}: {exc}"
            ) from exc
        results = cast("list[Mapping[str, object]]", data.get("results") or [])
        return [
            {
                "title": str(item.get("title", "")),
                "url": str(item.get("url", "")),
                "snippet": str(item.get("content", "")) or str(item.get("snippet", "")),
            }
            for item in results[:limit]
            if item.get("url")
        ]

    def _summarize(
        self, query: str, depth: int, documents: tuple[RetrievedDocument, ...]
    ) -> str:
        """An honest mechanical description of the retrieval (never a verdict)."""
        if not documents:
            return f"Searched for {query!r} (depth {depth}) and found nothing."
        titles = "; ".join(doc.title for doc in documents[:5] if doc.title)
        return (
            f"Searched for {query!r} (depth {depth}). "
            f"Found {len(documents)} result(s): {titles}"
        )


def build_odysseus_search_source(
    environ: Mapping[str, str] | None = None,
    *,
    instance: str | None = None,
    timeout: float = 15.0,
    transport: Transport | None = None,
) -> SearXNGResearchSource | None:
    """Build a :class:`SearXNGResearchSource` when a SearXNG instance is configured.

    ``None`` means "no research capability configured" (e.g. no ``SEARXNG_INSTANCE``
    env var), so a Jarvis built from this keeps working offline. Passing
    ``instance`` explicitly opts in and overrides the environment, keeping the
    composition root trivial.
    """
    resolved = instance or (environ or os.environ).get("SEARXNG_INSTANCE") or None
    if resolved is None:
        return None
    return SearXNGResearchSource(
        instance=resolved, timeout=timeout, transport=transport, environ=environ
    )