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
from jarvis.domain.services.capability_provider import CapabilityProvider


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
) -> CapabilityRegistry:
    """The built-in edge: the ExternalSource backs the Internet capabilities.

    When no ExternalSource is wired, an empty registry means no capability is
    live-backed -- Jarvis is simply offline. With one, agent-reach serves both
    web capabilities (read and search) as real, usable acquisitions.
    """
    if external_source is None:
        return StaticCapabilityRegistry()
    return StaticCapabilityRegistry(
        _by_name={
            name: ExternalSourceCapability(external_source, name)
            for name in ("search the web", "read external documents")
        }
    )


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