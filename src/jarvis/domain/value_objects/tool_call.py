"""ToolCall: a concrete, immutable record of one tool invocation.

A call names the tool, the arguments (relevant ones; never secrets), the permission
level it ran under, and (for observability) how long it took and whether it
succeeded. It is written to the trace so Jarvis can later reason about *what it did*
and *how it went* -- the evaluation step of the tool loop (06_TOOLS_AGENCY).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from jarvis.domain.enums.permission_level import PermissionLevel


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCall:
    """One immutable record of a tool invocation, for the observability trace."""

    tool: str
    arguments: dict[str, str] = field(default_factory=lambda: {})
    permission: PermissionLevel = PermissionLevel.READ
    duration_seconds: float = 0.0
    ok: bool = True
    error: str = ""
    started_at: datetime = field(default_factory=_now)