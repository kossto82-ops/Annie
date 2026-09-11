"""External/research/compare handlers — the Internet and model-comparison surface."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from jarvis.domain.services.model_compare import ModelRun
from jarvis.domain.value_objects.research_report import ResearchReport
from jarvis.domain.value_objects.retrieved_document import RetrievedDocument
from jarvis.jarvis import Jarvis

from jarvis.interface._shared import _capability_not_ready

if TYPE_CHECKING:
    pass

# A reply the UI can render and (optionally) speak; some commands add extra fields.
Reply = dict[str, object]

# The Internet command (read/search) requires the matching Odysseus capability to
# be *acquired and backed by a provider* -- using it is earned, not automatic.
_EXTERNAL_CAPABILITIES = {
    "read": "read external documents",
    "search": "search the web",
}

_RESEARCH_CAPABILITY = "deep research"
_COMPARE_CAPABILITY = "compare language models"


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
