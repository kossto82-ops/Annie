"""DelegationScope: the set of tools a delegated task may touch (D1-revised).

Delegation hands a *material* task to the edge agent behind the `TaskAgent` seam.
A scope narrows that hand-off to an explicit toolset: the executor refuses any
tool whose name is outside the scope, truthfully, so a scoped delegation can
never wander into tools the caller did not sanction -- exactly the decided-script
grammar's ``name key="value"`` tool identity, plus the model-driven toolset.

The scope itself is a plain set of tool names. It makes no decision about
*whether* the task should run (that stays upstream, gated by the
controlled-autonomy policy and the registry's permission gate); it only bounds
*which* tools one delegated task may use. An empty scope allows nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from jarvis.domain.enums.permission_level import PermissionLevel


@dataclass(frozen=True, slots=True, kw_only=True)
class DelegationScope:
    """The exact tool names one delegated task may call."""

    allowed_tools: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for name in self.allowed_tools:
            if not name.strip():
                raise ValueError("a delegation scope tool name must not be empty")

    @classmethod
    def none(cls) -> DelegationScope:
        """The most restrictive scope: no tool may be called."""
        return cls(allowed_tools=frozenset())

    @classmethod
    def all(cls, *names: str) -> DelegationScope:
        """A scope over exactly ``names`` (de-duplicated, order-free)."""
        return cls(allowed_tools=frozenset(names))

    def allows(self, name: str) -> bool:
        """Whether tool ``name`` may be called under this scope."""
        return name in self.allowed_tools


def scope_at_most(
    tools: Mapping[str, PermissionLevel], level: PermissionLevel
) -> DelegationScope:
    """A scope of every tool whose permission sits at or below ``level``.

    The caller supplies the tool -> permission map (e.g. derived from a
    :class:`~jarvis.domain.tools.tool_registry.ToolRegistry`'s specs), so the
    factory stays pure and offline-testable. ``at_most`` is the convenient floor:
    a delegation "no MCP / no destructive" is ``scope_at_most(registry_map,
    PermissionLevel.WRITE)``, keeping only locally reversible acts.
    """
    return DelegationScope(
        allowed_tools=frozenset(
            name for name, permission in tools.items() if permission <= level
        )
    )