"""External/research/compare handlers — the Internet and model-comparison surface."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from jarvis.domain.services.model_compare import ModelRun
from jarvis.domain.value_objects.capability_outcome import (
    CapabilityOutcome,
    CapabilityOutcomeStatus,
)
from jarvis.domain.value_objects.research_report import ResearchReport
from jarvis.domain.value_objects.retrieved_document import RetrievedDocument
from jarvis.interface._shared import capability_not_ready
from jarvis.jarvis import Jarvis

if TYPE_CHECKING:
    pass

# A reply the UI can render and (optionally) speak; some commands add extra fields.
Reply = dict[str, object]

# The Internet command (read/search) requires the matching Odysseus capability to
# be *acquired and backed by a provider* -- using it is earned, not automatic.
EXTERNAL_CAPABILITIES = {
    "read": "read external documents",
    "search": "search the web",
}

_RESEARCH_CAPABILITY = "deep research"
_COMPARE_CAPABILITY = "compare language models"


def external_not_ready(jarvis: Jarvis, capability: str) -> Reply:
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
    return capability_not_ready(jarvis, capability)


def _external(jarvis: Jarvis, payload: Reply) -> Reply:
    """Use the Internet capability: read, search, investigate, or report channels.

    ``read``/``search`` are the *deliberate* gates a surface (or an explicit outer
    decision layer) uses when updated/outside information is actually needed.
    ``investigate`` is the orchestrated path: Jarvis *decides* which capability
    (read vs search, source-preferred) fits the subject, executes it once, and
    reports the honest outcome. Results carry provenance back to Jarvis; Jarvis
    does not write them to memory here. Offline/absent capability or a fetch
    failure is a clear message, never a crash and never negative evidence.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": (
                "Use external with action 'read', 'search', 'investigate' "
                "or 'channels'."
            ),
            "speak": False,
        }
    if action in ("read", "search") and not jarvis.can_do(EXTERNAL_CAPABILITIES[action]):
        return external_not_ready(jarvis, EXTERNAL_CAPABILITIES[action])
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
        if action == "investigate":
            return _investigate(jarvis, payload)
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


def _investigate(jarvis: Jarvis, payload: Reply) -> Reply:
    """The orchestrated external path: decide, execute once, report honestly.

    ``investigate`` is where the capability decision lives behind a deliberate
    surface gate: Jarvis (not the caller) decides whether outside information is
    needed and which read/research capability fits, honors an explicit source
    preference, and executes exactly one bounded request. The reply narrates the
    honest outcome -- retrieved documents with provenance, an explicit
    unavailable state, an honest empty, or a failure -- and never a belief.

    With ``ingest=true`` the retrieved documents are *also* perceived into
    provenance-bearing claims (through the ordinary perceiver) and fed through
    one sanctioned cognitive episode: the working belief evolves only through
    the existing evidence machinery, never by direct assignment. Off by default:
    plain ``investigate`` stays read-only, as the capability gate defined it.
    """
    subject = str(payload.get("subject", "") or payload.get("query", "")).strip()
    if not subject:
        return {"reply": "Provide a subject to investigate.", "speak": False}
    reason = str(payload.get("reason", "")).strip()
    raw_hint = str(payload.get("source", "")).strip()
    source_hint = raw_hint or None
    decision = jarvis.decide_capability(
        subject, reason=reason, source_hint=source_hint
    )
    if decision.needed and decision.capability is not None:
        gate = (
            EXTERNAL_CAPABILITIES["read"]
            if decision.capability.is_read
            else EXTERNAL_CAPABILITIES["search"]
        )
        if not jarvis.can_do(gate):
            return external_not_ready(jarvis, gate)
    outcome = jarvis.execute_capability_decision(decision)
    reply = _capability_outcome_reply(outcome)
    if _is_ingest(payload) and outcome.status is CapabilityOutcomeStatus.SUCCESS:
        episode = jarvis.learn_from_external(subject, outcome.documents)
        if episode is not None:
            reply["reply"] = (
                f"{reply['reply']}\n\n"
                "I also perceived these documents as claims and weighed them "
                "through a cognitive episode — where the evidence pointed, I "
                "updated accordingly. Nothing is believed more strongly than the "
                "evidence allows."
            )
        else:
            reply["reply"] = (
                f"{reply['reply']}\n\n"
                "I read them for claims, but the perceiver extracted no evidence "
                "to weigh."
            )
    return reply


def _is_ingest(payload: Reply) -> bool:
    return str(payload.get("ingest", "")).strip().lower() in (
        "true",
        "1",
        "yes",
        "on",
    )


def _capability_outcome_reply(outcome: CapabilityOutcome) -> Reply:
    """Render an honest capability outcome, provenance kept and verdicts avoided."""
    if outcome.status is CapabilityOutcomeStatus.NO_NEED:
        return {
            "reply": (
                "I don't need outside information for that — it comes from what "
                "I already know, so no external capability was called."
            ),
            "speak": False,
        }
    if outcome.status is CapabilityOutcomeStatus.UNAVAILABLE:
        return {
            "reply": (
                f"I couldn't use that external capability right now: {outcome.message}. "
                "That says the capability is unavailable, not that the information "
                "doesn't exist."
            ),
            "speak": False,
        }
    if outcome.status is CapabilityOutcomeStatus.FAILED:
        return {
            "reply": (
                f"I tried, but that external request failed ({outcome.message}). "
                "My reasoning and memory are unaffected."
            ),
            "speak": False,
        }
    if outcome.status is CapabilityOutcomeStatus.EMPTY:
        return {
            "reply": (
                "Nothing external came back for that — an honest 'nothing found', "
                "not a claim either way."
            ),
            "speak": False,
        }
    docs = outcome.documents
    parts: list[str] = []
    for i, doc in enumerate(docs, 1):
        head = doc.content.strip().replace("\n", " ")
        if len(head) > 200:
            head = head[:200].rstrip() + "…"
        title = f" — {doc.title}" if doc.title else ""
        parts.append(f"{i}. [{doc.source}]{title}\n   {doc.url or '(no url)'}\n   {head}")
    return {
        "reply": "I looked outside and found:\n" + "\n".join(parts),
        "speak": False,
        "count": len(docs),
        "research_reason": outcome.request.reason,
    }


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
        return capability_not_ready(jarvis, _RESEARCH_CAPABILITY)
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
        return capability_not_ready(jarvis, _COMPARE_CAPABILITY)
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


Command = Callable[[Jarvis, Reply], Reply]

# The commands this module serves, composed by the command-center router.
COMMANDS: dict[str, Command] = {
    "compare": _compare,
    "external": _external,
    "research": _research,
}
