"""CapabilityRequirement: what Jarvis needs from an external capability (v1).

The capability layer keeps ``NEED`` / ``CAPABILITY`` / ``RETRIEVAL`` /
``EVIDENCE`` distinct. This enum names the *capability* side of that chain --
the read/research requirement Jarvis decides it has -- without ever naming a
provider or a backend. A requirement is routed to a provider by the
:mod:`capability_orchestration` service, and the provider picks its own backend.

v1 is deliberately small: exactly the representative read/research set the
orchestration boundary is verified against (Vision §38):

* ``READ_URL``       -- fetch one URL and bring its text back.
* ``SEARCH_WEB``     -- search the open web for timely outside information.
* ``RESEARCH_GITHUB`` -- search with a GitHub source preference (never a
  silent substitution -- the preference rides the request and the trace).
* ``RESEARCH_YOUTUBE`` -- search with a YouTube source preference.

No action/write capability exists in v1: this layer is read/research only.
Other agent-reach channels stay behind the provider until a later gate
justifies them (D7).
"""

from __future__ import annotations

from enum import Enum


class CapabilityRequirement(Enum):
    """A read/research requirement Jarvis can decide it needs (read-only v1)."""

    READ_URL = "read_url"
    SEARCH_WEB = "search_web"
    RESEARCH_GITHUB = "research_github"
    RESEARCH_YOUTUBE = "research_youtube"

    @property
    def is_search(self) -> bool:
        """True when this requirement is satisfied by a provider *search*."""
        return self in (
            CapabilityRequirement.SEARCH_WEB,
            CapabilityRequirement.RESEARCH_GITHUB,
            CapabilityRequirement.RESEARCH_YOUTUBE,
        )

    @property
    def is_read(self) -> bool:
        """True when this requirement is satisfied by fetching one URL."""
        return self is CapabilityRequirement.READ_URL

    @property
    def source_preference(self) -> str | None:
        """The platform this requirement is constrained to, if any.

        A source preference is honored: the orchestrator never silently swaps a
        preferred platform for a different one. It exists so the request is
        inspectable ("why did Jarvis call the web provider with a github
        preference?"); whether the provider can ground that platform is a
        provider-availability question, never a silent assumption.
        """
        return {
            CapabilityRequirement.RESEARCH_GITHUB: "github",
            CapabilityRequirement.RESEARCH_YOUTUBE: "youtube",
        }.get(self)