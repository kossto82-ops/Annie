"""ToolSpec: what a tool is and how risky it is (Vision §34).

A tool is an extension of Jarvis's ability to *act* in the world. The spec declares
what the tool does, what arguments it accepts, and its :class:`PermissionLevel` --
the classification that lets policy decide whether the call needs approval before it
runs. The spec carries no cognition: it only describes; executing is up to a Tool
implementation, and *deciding whether to run* is up to the core (Vision §34, §6).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jarvis.domain.enums.permission_level import PermissionLevel


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolSpec:
    """Declaration of a tool: its name, purpose, arguments and permission level."""

    name: str
    description: str
    args: dict[str, str] = field(default_factory=lambda: {})
    permission: PermissionLevel = PermissionLevel.READ

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("A tool requires a non-empty name")
        if not self.description or not self.description.strip():
            raise ValueError("A tool requires a description")

    @property
    def requires_approval(self) -> bool:
        """True when executing this tool needs explicit approval (policy hook).

        By default only external and destructive actions require approval -- the
        READ/WRITE/EXECUTE levels are locally reversible and do not need it.
        Overridable by an injected policy.
        """
        return self.permission >= PermissionLevel.EXTERNAL_ACTION