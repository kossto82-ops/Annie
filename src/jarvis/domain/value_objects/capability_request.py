"""CapabilityRequest: one inspectable ask to the capability layer (v1).

This is the request contract the capability orchestrator executes. It carries
what Jarvis wants -- the *capability*, the *target* it applies to, and the
*reason* it is wanted -- but never collapses retrieval into evidence: a request
only asks to go get; what the result *means* stays in the epistemic pipeline.

The ``reason`` is an execution trace, not a belief: it answers a future
self-review's "why did I invoke an external capability?" and is never written
to semantic memory automatically (the orchestrator writes nothing).

Fields are kept to what the current architecture genuinely consumes (D7):

* ``capability``    -- the read/research requirement decided by cognition.
* ``target``        -- the URL (for reads) or the query text (for searches).
* ``subject``       -- the original trigger the request serves (inspectable).
* ``reason``        -- why Jarvis decided to look outside (the trace).
* ``source_preference`` -- an explicit source constraint, preserved verbatim.

A network timeout is deliberately *not* duplicated here: bounded execution is
structural (one attempt, see ``CapabilityOutcome.attempts``) and the concrete
adapter owns its network timeout (e.g. ``AgentReachSource(timeout=...)``).
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.value_objects.capability_requirement import CapabilityRequirement


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityRequest:
    """A bounded, inspectable ask for one read/research capability."""

    capability: CapabilityRequirement | None
    target: str
    subject: str
    reason: str = ""
    source_preference: str | None = None

    def __post_init__(self) -> None:
        if not self.target or not self.target.strip():
            raise ValueError("A capability request requires a target")
        if not self.subject or not self.subject.strip():
            raise ValueError("A capability request requires a subject")
        if self.capability is None and not self.reason.strip():
            raise ValueError(
                "a request without a capability still needs an explicit reason"
            )