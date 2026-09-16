"""CapabilityOutcome: what one capability request produced (v1).

The orchestrator returns one of these for every request. It is the *retrieval*
answer -- it says what the capability layer did, never what it means. The five
statuses keep the distinctions the epistemic core depends on:

* ``SUCCESS``     -- documents came back, with provenance intact.
* ``EMPTY``       -- the request worked but found nothing. Honest "nothing",
  never negative evidence (an empty result does not support the opposite).
* ``UNAVAILABLE`` -- the capability or its provider is not wired/reachable.
  This is *not* "the information does not exist", and it is never converted
  into negative evidence.
* ``FAILED``      -- the request ran and errored (network, provider, ...).
* ``NO_NEED``     -- cognition decided no external capability was called for;
  the outcome records that decision as a trace, with zero attempts.

``documents`` are the existing provenance-bearing :class:`RetrievedDocument`
objects, untouched from the provider -- orchestration never strips provenance.
``attempts`` is the bounded-execution proof: at most one provider attempt per
request, and no hidden retry/research loop (a fresh decision is a fresh
request; uncertainty returns to cognition, and cognition decides whether
another retrieval is justified).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from jarvis.domain.value_objects.capability_request import CapabilityRequest
from jarvis.domain.value_objects.retrieved_document import RetrievedDocument


class CapabilityOutcomeStatus(Enum):
    """The honest result of one capability request."""

    NO_NEED = "no_need"
    SUCCESS = "success"
    EMPTY = "empty"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityOutcome:
    """What one capability request produced, with its request preserved."""

    status: CapabilityOutcomeStatus
    request: CapabilityRequest
    documents: tuple[RetrievedDocument, ...] = ()
    message: str = ""
    attempts: int = 0

    @property
    def obtained(self) -> bool:
        """True when usable documents came back (the only evidence source)."""
        return self.status is CapabilityOutcomeStatus.SUCCESS and bool(self.documents)

    @property
    def provider_backends(self) -> tuple[tuple[str, str], ...]:
        """The (provider, backend) pairs actually reported by the documents.

        Derived from the documents' own metadata so provenance is never
        duplicated or invented by the orchestration layer (Vision §8).
        """
        seen: list[tuple[str, str]] = []
        for doc in self.documents:
            provider = doc.metadata.get("provider", "unknown")
            backend = doc.metadata.get("backend", "unknown")
            pair = (provider, backend)
            if pair not in seen:
                seen.append(pair)
        return tuple(seen)