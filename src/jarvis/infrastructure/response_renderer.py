"""ResponseRenderer: how Jarvis's reply is phrased for the companion (Vision §40).

The cognitive core reasons and produces a reply in its own canonical form. *How* that
reply is voiced — in particular, in which language and register — is a presentation
concern that lives at the edge, not in the core. A `ResponseRenderer` takes a reply
Jarvis has already decided and rephrases it for the companion.

This is strictly presentation (§38): a renderer may re-word Jarvis's own conclusion,
it must NOT add, remove, or change any fact — the epistemic content is fixed before it
gets here. The default renderer changes nothing at all.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ResponseRenderer(Protocol):
    """Rephrases a reply Jarvis has decided, without changing its meaning."""

    def phrase(self, reply: str, like: str) -> str:
        """Return ``reply`` reworded to match ``like`` (e.g. its language)."""
        ...


class IdentityRenderer:
    """The default voice: it returns the reply exactly as the core phrased it.

    Offline, or with the keyword perceiver, there is no model to rephrase with — so the
    reply is left untouched (English canonical form). No network, no change.
    """

    def phrase(self, reply: str, like: str) -> str:
        return reply
