"""capability_orchestration: the decision layer between cognition and providers.

This service answers the orchestration question of the capability gate: "does
this need external information, which capability, who provides it, and what
came back?" -- while keeping the five stages distinct (Vision §38):

    NEED -> CAPABILITY -> RETRIEVAL -> EVIDENCE -> BELIEF

* :func:`decide_capability` is the NEED + CAPABILITY stages: it deterministically
  decides whether a subject requires external information and, if so, which
  read/research capability satisfies it. It is deliberately *not* an LLM/embedding
  choice -- the decision is rule-based and reproducible, mirroring the shallow
  matching the capability scout already uses for candidate proposals (D11).
* :func:`execute_capability` is the CAPABILITY -> RETRIEVAL stage: it routes a
  decided capability to an :class:`ExternalSource`, calls the provider exactly
  once, and returns an inspectable :class:`CapabilityOutcome` carrying the
  provenance-bearing :class:`RetrievedDocument` results.

The service never turns a result into evidence and never writes to cognition:
no belief, episode, semantic memory, topic, attention or curiosity mutation is
even reachable from here. Converting a *successful* retrieval into candidate
evidence happens only through the existing sanctioned pipeline -- e.g. the
``ExternalCapabilityKnowledgeSource`` adapter feeding the executive's
deliberate-consult seam -- and empty/unavailable/failed retrievals stay honest
"nothing", never negative evidence.

Read/research only: no action/write capability is orchestrated in v1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from jarvis.domain.retrieval.external_source import ExternalSource
from jarvis.domain.value_objects.capability_outcome import (
    CapabilityOutcome,
    CapabilityOutcomeStatus,
)
from jarvis.domain.value_objects.capability_request import CapabilityRequest
from jarvis.domain.value_objects.capability_requirement import CapabilityRequirement

_URL_RE = re.compile(r"https?://[^\s]+")
_NORM_RE = re.compile(r"[^a-z0-9]+")

# Bilingual, deterministic cues that say "outside information is needed now".
_TIMELY_CUES = frozenset(
    {
        "current",
        "latest",
        "today",
        "now",
        "news",
        "weather",
        "web",
        "internet",
        "search",
        "update",
        "recent",
        "online",
        "fresh",
        "price",
        "precio",
        "hoy",
        "actual",
        "noticia",
        "noticias",
        "clima",
        "hora",
    }
)
_GITHUB_CUES = frozenset({"github", "repo", "repository", "repos"})
_YOUTUBE_CUES = frozenset({"youtube", "video"})

_NOT_NEEDED_REASON = (
    "answerable from internal knowledge; no external capability needed"
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityDecision:
    """What cognition decided: whether to look outside, and with which capability.

    ``target`` is the URL for a read requirement, or ``None`` for searches (the
    subject itself is the query). ``reason`` is the why-trace -- see
    :class:`CapabilityRequest`; it is inspectable and never a belief.
    """

    needed: bool
    capability: CapabilityRequirement | None
    subject: str
    target: str | None = None
    reason: str = ""
    source_hint: str | None = None

    def __post_init__(self) -> None:
        if not self.subject or not self.subject.strip():
            raise ValueError("a capability decision requires a subject")
        if self.needed and self.capability is None:
            raise ValueError("a needed capability decision requires a capability")


def _norm(text: str) -> str:
    return _NORM_RE.sub(" ", text.lower()).strip()


def _extract_url(text: str) -> str | None:
    match = _URL_RE.search(text)
    if match is None:
        return None
    return match.group(0).rstrip(".,);]}'\"`")


def decide_capability(
    subject: str,
    *,
    reason: str = "",
    source_hint: str | None = None,
    known_internally: bool = False,
) -> CapabilityDecision:
    """Decide whether ``subject`` needs external information, and how.

    Deterministic, offline, and bilingual (the same shallow cue matching the
    capability scout uses for proposals). Rules, in order:

    1. ``known_internally`` -- cognition already has the answer; no call.
    2. A URL is present (in ``source_hint`` or ``subject``) -- READ_URL.
    3. An explicit ``source_hint`` names a platform (github/youtube) -- a
       source-constrained research requirement; the preference is preserved and
       never swapped for another source.
    4. Subject cues: GitHub words, YouTube words, then timely-current words.
    5. Otherwise NO_NEED -- the subject looks answerable from within.

    ``reason`` is the why-trace the caller wants to record; when empty a
    derived reason is recorded so every decision stays inspectable.
    """
    subject_s = subject.strip()
    if known_internally:
        return CapabilityDecision(
            needed=False,
            capability=None,
            subject=subject_s,
            reason=reason or _NOT_NEEDED_REASON,
            source_hint=source_hint,
        )

    url = _extract_url(source_hint or subject_s)
    if url is not None:
        return CapabilityDecision(
            needed=True,
            capability=CapabilityRequirement.READ_URL,
            subject=subject_s,
            target=url,
            reason=reason or f"deliberate read of {url} about: {subject_s}",
            source_hint=source_hint,
        )

    hint_words: set[str] = (
        set(_norm(source_hint).split())
        if source_hint and source_hint.strip()
        else set()
    )
    if "github" in hint_words or _GITHUB_CUES & hint_words:
        return CapabilityDecision(
            needed=True,
            capability=CapabilityRequirement.RESEARCH_GITHUB,
            subject=subject_s,
            reason=reason or f"deliberate GitHub research about: {subject_s}",
            source_hint=source_hint,
        )
    if "youtube" in hint_words or "yt" in hint_words or _YOUTUBE_CUES & hint_words:
        return CapabilityDecision(
            needed=True,
            capability=CapabilityRequirement.RESEARCH_YOUTUBE,
            subject=subject_s,
            reason=reason or f"deliberate YouTube research about: {subject_s}",
            source_hint=source_hint,
        )

    words = set(_norm(subject_s).split())
    if _GITHUB_CUES & words:
        return CapabilityDecision(
            needed=True,
            capability=CapabilityRequirement.RESEARCH_GITHUB,
            subject=subject_s,
            reason=reason or f"deliberate GitHub research about: {subject_s}",
            source_hint=source_hint,
        )
    if _YOUTUBE_CUES & words:
        return CapabilityDecision(
            needed=True,
            capability=CapabilityRequirement.RESEARCH_YOUTUBE,
            subject=subject_s,
            reason=reason or f"deliberate YouTube research about: {subject_s}",
            source_hint=source_hint,
        )
    if _TIMELY_CUES & words:
        return CapabilityDecision(
            needed=True,
            capability=CapabilityRequirement.SEARCH_WEB,
            subject=subject_s,
            reason=reason or f"deliberate web research about: {subject_s}",
            source_hint=source_hint,
        )

    return CapabilityDecision(
        needed=False,
        capability=None,
        subject=subject_s,
        reason=reason or _NOT_NEEDED_REASON,
        source_hint=source_hint,
    )


def _build_request(
    decision: CapabilityDecision, *, target: str
) -> CapabilityRequest:
    return CapabilityRequest(
        capability=decision.capability,
        target=target,
        subject=decision.subject,
        reason=decision.reason,
        source_preference=decision.source_hint,
    )


def execute_capability(
    decision: CapabilityDecision,
    source: ExternalSource | None,
    *,
    search_limit: int = 5,
) -> CapabilityOutcome:
    """Execute a decided capability against a provider, exactly once.

    Returns an honest :class:`CapabilityOutcome` for every input -- including
    "no need" and "no provider wired" -- and never raises. Bounded execution is
    structural: a single attempted call per decision (``attempts`` is 0 when no
    call was made, 1 when one was), no retry loop and no auto "search again" on
    uncertainty. A failed/empty request returns its status to cognition, which
    decides whether another retrieval is ever justified.
    """
    if not decision.needed:
        request = _build_request(decision, target=decision.subject)
        return CapabilityOutcome(
            status=CapabilityOutcomeStatus.NO_NEED,
            request=request,
            documents=(),
            message=_NOT_NEEDED_REASON,
            attempts=0,
        )

    capability = decision.capability
    if capability is None or source is None:
        request = _build_request(decision, target=decision.subject)
        return CapabilityOutcome(
            status=CapabilityOutcomeStatus.UNAVAILABLE,
            request=request,
            documents=(),
            message="the requested capability is not wired (no external provider)",
            attempts=0,
        )

    if capability.is_read and not decision.target:
        request = _build_request(decision, target=decision.subject)
        return CapabilityOutcome(
            status=CapabilityOutcomeStatus.FAILED,
            request=request,
            documents=(),
            message="a URL-read capability request carries no URL",
            attempts=0,
        )

    if capability.is_search and _search_channel_off(source):
        request = _build_request(decision, target=decision.subject)
        return CapabilityOutcome(
            status=CapabilityOutcomeStatus.UNAVAILABLE,
            request=request,
            documents=(),
            message="no web-search backend is configured right now",
            attempts=0,
        )

    target = decision.target or decision.subject
    request = _build_request(decision, target=target)
    try:
        if capability.is_read:
            docs = (source.read(target),)
        else:
            docs = source.search(target, limit=search_limit)
    except Exception as exc:  # noqa: BLE001 - the provider boundary
        return CapabilityOutcome(
            status=CapabilityOutcomeStatus.FAILED,
            request=request,
            documents=(),
            message=f"capability request failed ({type(exc).__name__})",
            attempts=1,
        )

    if not docs:
        return CapabilityOutcome(
            status=CapabilityOutcomeStatus.EMPTY,
            request=request,
            documents=(),
            message="the request returned nothing",
            attempts=1,
        )

    return CapabilityOutcome(
        status=CapabilityOutcomeStatus.SUCCESS,
        request=request,
        documents=tuple(docs),
        message="retrieved",
        attempts=1,
    )


def _search_channel_off(source: ExternalSource) -> bool:
    """True when the provider itself reports its search channel as ``off``.

    Consulted before a search attempt so "capability unavailable" is told apart
    from "request failed" and never confused with "nothing was found". A stub
    that says nothing about a search channel is left to the provider -- a real
    search call decides.
    """
    try:
        channels = source.available_channels()
    except Exception:  # noqa: BLE001 - report-only path; a search call decides
        return False
    return any(c.name == "search" and c.status == "off" for c in channels)