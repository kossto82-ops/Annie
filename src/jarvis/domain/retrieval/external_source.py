"""ExternalSource: the seam between Jarvis and the outside information (capability).

This is a domain-level Protocol, mirroring :class:`MemoryRetriever` and
:class:`PerceptionSource` (Vision §32, §38): it is the *capability* that gives
Jarvis access to the Internet -- search, read, and health of the underlying
channels. It deliberately does not decide anything:

* It fetches and returns :class:`RetrievedDocument` candidates.
* It does not weigh beliefs, assert facts, or derive confidence.
* Turning a result into standing evidence, and reasoning over it, stays in the
  cognitive core.

An `ExternalSource` *retrieves*; it is not memory. It must never write to Jarvis's
beliefs, memory, or knowledge stores directly. Its results carry provenance
(source, url, title, metadata) so the core can later tell external information
apart from internal knowledge (Vision §8).

Separating the seam from any concrete provider keeps Jarvis working offline --
an implementation may fail off when no provider is configured or reachable, and a
regular conversation never needs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from jarvis.domain.value_objects.retrieved_document import RetrievedDocument


@dataclass(frozen=True, slots=True)
class ChannelStatus:
    """A snapshot of one external channel's health, as reported by an ExternalSource.

    ``status`` is one of ``"ok"`` / ``"warn"`` / ``"off"`` / ``"error"`` (the
    vocabulary Agent-Reach's doctor uses); ``active_backend`` names the backend
    actually serving now, or is ``None`` when unavailable. This is report-only and
    never a decision.
    """

    name: str
    status: str
    message: str = ""
    active_backend: str | None = None


@runtime_checkable
class ExternalSource(Protocol):
    """Gives Jarvis read/search access to external (Internet) information."""

    def read(self, url: str) -> RetrievedDocument:
        """Fetch the content of ``url`` and return it as a document.

        Raises when ``url`` cannot be read (unreachable, unrecognized, blocked).
        """
        ...

    def search(
        self, query: str, *, limit: int = 5
    ) -> tuple[RetrievedDocument, ...]:
        """Return up to ``limit`` external results bearing on ``query``.

        Ordered most-relevant first; empty when nothing is found. Raises only on a
        real failure of the underlying search, so an empty result stays an honest
        "nothing found".
        """
        ...

    def available_channels(self) -> tuple[ChannelStatus, ...]:
        """Report the health of the configured external channels (doctor).

        Allows Jarvis to decide which sources it *can* reach before choosing to use
        one -- it is information, not a decision.
        """
        ...
