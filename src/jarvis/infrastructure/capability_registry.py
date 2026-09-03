"""capability_registry: the edge that backs acquired capabilities (Odysseus, D7).

The registry answers one question for the surfaces: *given a capability name,
which provider serves it, and is it ready?* It is the live side of Odysseus --
an acquired ``Capability`` is bookkeeping, a registered provider is what makes
that acquisition real. Registration and availability live entirely at the edge;
the cognitive core never depends on them (a store with providers is still a
store). Providers stay provider-agnostic and offline-testable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from jarvis.domain.retrieval.external_source import ExternalSource
from jarvis.domain.retrieval.mail_source import MailBox
from jarvis.domain.retrieval.notes_store import NotesStore
from jarvis.domain.retrieval.research_source import ResearchSource
from jarvis.domain.retrieval.task_agent_source import TaskAgent
from jarvis.domain.services.capability_provider import CapabilityProvider
from jarvis.domain.services.model_compare import ModelComparator


class CapabilityRegistry(Protocol):
    """A registry that resolves capability names to their edge providers."""

    def provider_for(self, capability: str) -> CapabilityProvider | None:
        """The provider serving ``capability``, or None when none is wired."""
        ...


@dataclass(frozen=True, slots=True)
class StaticCapabilityRegistry:
    """A frozen registry holding providers as registered (offline, injectable).

    Deterministic and immutable: a surface can read it freely, and a test can
    build one from stubs without any provider or network.
    """

    _by_name: Mapping[str, CapabilityProvider] = field(
        default_factory=dict[str, CapabilityProvider]
    )

    def provider_for(self, capability: str) -> CapabilityProvider | None:
        return self._by_name.get(capability)


def build_default_registry(
    external_source: ExternalSource | None,
    *,
    research_source: ResearchSource | None = None,
    model_compare: ModelComparator | None = None,
    reasoner: CapabilityProvider | None = None,
    recall: CapabilityProvider | None = None,
    mail_source: MailBox | None = None,
    task_agent: TaskAgent | None = None,
    notes_store: NotesStore | None = None,
) -> CapabilityRegistry:
    """The built-in edge: the ExternalSource backs the Internet capabilities.

    When no ExternalSource is wired, an empty registry means no capability is
    live-backed -- Jarvis is simply offline. With one, agent-reach serves both
    web capabilities (read and search) as real, usable acquisitions. An optional
    ``reasoner``/``recall`` provider backs the reasoning and meaning-recall
    capabilities (kept separate so they can reflect runtime seams). The deep-
    research and blind model-comparison sources back their capabilities too, when
    wired, so ``can_do`` is uniform across every edge (Odysseus, §28). A wired
    mailbox backs the email capability, and a wired task agent backs delegation
    (D1-revised: material edge action).
    """
    by_name: dict[str, CapabilityProvider] = {}
    if external_source is not None:
        by_name.update(
            {
                name: ExternalSourceCapability(external_source, name)
                for name in ("search the web", "read external documents")
            }
        )
    if research_source is not None:
        by_name["deep research"] = ResearchCapability(research_source)
    if model_compare is not None:
        by_name["compare language models"] = ModelCompareCapability(model_compare)
    if reasoner is not None:
        by_name["reason with a language model"] = reasoner
    if recall is not None:
        by_name["recall by meaning"] = recall
    if mail_source is not None:
        by_name["send and read email"] = MailCapability(mail_source)
    if task_agent is not None:
        by_name["delegate to an agent"] = AgentCapability(task_agent)
    if notes_store is not None:
        by_name["manage notes"] = NotesCapability(notes_store)
    return StaticCapabilityRegistry(_by_name=by_name)


class ReasonerCapability:
    """'reason with a language model' backed by the live reasoner (Vision §37).

    A capability is bookkeeping; this reports whether Jarvis's *actual* reasoner is
    a live one right now. Silent (offline, never proposes) is not a usable reasoning
    capability, so it reads as unavailable; a real LLM reasoner makes it live. The
    provider is mutable so the runtime seam (`set_reasoner`) can flip availability.
    """

    def __init__(self, capability: str = "reason with a language model") -> None:
        self._capability = capability
        self._live = False

    @property
    def capability(self) -> str:
        return self._capability

    def is_available(self) -> bool:
        return self._live

    def set_live(self, live: bool) -> None:
        """Mark whether a live provider backs reasoning right now."""
        self._live = live


class SemanticRecallCapability:
    """'recall by meaning' backed by the embedding retriever (Vision §3, D11).

    Reports whether Jarvis's long-term recall is meaning-based (an embedding
    retriever) right now. Lexical-only recall is plain keyword memory, not this
    capability, so it reads as unavailable until embedding recall is enabled. Mutable
    so the runtime seam (`enable_embedding_recall`) can flip availability.
    """

    def __init__(self, capability: str = "recall by meaning") -> None:
        self._capability = capability
        self._live = False

    @property
    def capability(self) -> str:
        return self._capability

    def is_available(self) -> bool:
        return self._live

    def set_live(self, live: bool) -> None:
        """Mark whether meaning-based recall is live right now."""
        self._live = live


class ExternalSourceCapability:
    """An :class:`ExternalSource` presented as a capability provider.

    The agent-reach ExternalSource (Vision §38) is itself the web capability --
    read and search -- so it backs those two capability names directly. It is
    available whenever it is wired; channel health is reported separately.
    """

    def __init__(self, source: ExternalSource, capability: str) -> None:
        self._source = source
        self._capability = capability

    @property
    def capability(self) -> str:
        return self._capability

    def is_available(self) -> bool:
        return True


class ResearchCapability:
    """The 'deep research' capability backed by the research source (Odysseus).

    A research source is itself the in-depth-investigation capability, so it
    backs that capability name directly. It is available whenever it is wired;
    whether Jarvis *uses* it stays a deliberate, earned decision in the core.
    """

    def __init__(self, source: ResearchSource, capability: str = "deep research") -> None:
        self._source = source
        self._capability = capability

    @property
    def capability(self) -> str:
        return self._capability

    def is_available(self) -> bool:
        return True


class ModelCompareCapability:
    """The 'compare language models' capability backed by the model comparator.

    The comparator is itself the blind-evaluation capability, so it backs that
    capability name directly. It is available whenever it is wired; interpreting
    the replies stays Jarvis's (D6) and using it stays a deliberate decision.
    """

    def __init__(
        self,
        comparator: ModelComparator,
        capability: str = "compare language models",
    ) -> None:
        self._comparator = comparator
        self._capability = capability

    @property
    def capability(self) -> str:
        return self._capability

    def is_available(self) -> bool:
        return True


class MailCapability:
    """The 'send and read email' capability backed by the mailbox edge (Odysseus).

    A wired mailbox is itself the email capability, so it backs that capability
    name directly. It is available whenever it is wired; whether Jarvis *uses* it
    -- and especially whether it *sends* -- stays a deliberate, earned decision
    gated by the controlled-autonomy policy (D1-revised: material edge action).
    """

    def __init__(self, mailbox: MailBox, capability: str = "send and read email") -> None:
        self._mailbox = mailbox
        self._capability = capability

    @property
    def capability(self) -> str:
        return self._capability

    def is_available(self) -> bool:
        return True


class AgentCapability:
    """The 'delegate to an agent' capability backed by the edge agent (D1-revised).

    A wired task agent is itself the delegation capability, so it backs that
    capability name directly. It is available whenever it is wired; whether Jarvis
    *chooses* to delegate -- and to what task -- stays a deliberate decision gated
    by the controlled-autonomy policy (ask-first for real-world effects).
    """

    def __init__(self, agent: TaskAgent, capability: str = "delegate to an agent") -> None:
        self._agent = agent
        self._capability = capability

    @property
    def capability(self) -> str:
        return self._capability

    def is_available(self) -> bool:
        return True


class NotesCapability:
    """The 'manage notes' capability backed by the notes store edge (Odysseus #8).

    A wired notes store is itself the notes capability, so it backs that
    capability name directly. It is available whenever it is wired; whether Jarvis
    *chooses* to create/edit/delete a note -- reversible, low-risk material
    actions -- stays a deliberate request gated by the surface.
    """

    def __init__(self, store: NotesStore, capability: str = "manage notes") -> None:
        self._store = store
        self._capability = capability

    @property
    def capability(self) -> str:
        return self._capability

    def is_available(self) -> bool:
        return True