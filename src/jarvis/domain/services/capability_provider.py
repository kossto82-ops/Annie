"""capability_provider: the live edge that backs an acquired capability (Odysseus).

A ``Capability`` in the store is *bookkeeping* -- what Jarvis declares it can do.
This Protocol is the live side of the same coin: a provider that actually serves
that capability. Keeping the two apart is the whole boundary (D7): the cognitive
core recognises, evaluates and acquires capabilities; the edge owns *how* they
work, as an injectable, provider-agnostic adapter.

A provider only reports *which capability name it serves* and *whether it is
ready right now*. It never decides whether Jarvis should use it -- that stays a
deliberate, earned decision in the core (Vision §28). Being a Protocol keeps the
edge offline-testable (a stub provider behaves deterministically).
"""

from __future__ import annotations

from typing import Protocol


class CapabilityProvider(Protocol):
    """A concrete adapter that serves one named capability at the edge."""

    @property
    def capability(self) -> str:
        """The capability name this provider serves (e.g. "search the web")."""
        ...

    def is_available(self) -> bool:
        """Whether the provider can serve the capability right now.

        Report-only: a surface uses it to say "I can actually do this now"; it
        is not a decision to use the capability.
        """
        ...