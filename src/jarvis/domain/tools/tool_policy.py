"""ToolPolicy: decides whether a tool call needs approval before it runs.

Policy is a *gate*, not a judge: it classifies a call by its :class:`PermissionLevel`
and returns an approval verdict, but it never decides whether Jarvis *should* act --
that reasoning stays in the cognitive core (Vision §28, §34). The default sees
external and destructive actions as requiring explicit confirmation, matching the
06_TOOLS_AGENCY principle that destructive/external operations begin gated.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.enums.permission_level import PermissionLevel


@dataclass(frozen=True, slots=True, kw_only=True)
class ApprovalDecision:
    """Whether a tool call may proceed and, if not, why."""

    allowed: bool
    reason: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolPolicy:
    """The approval policy over tool permission levels."""

    approval_required_from: PermissionLevel = PermissionLevel.EXTERNAL_ACTION

    def approve(self, level: PermissionLevel) -> ApprovalDecision:
        """Return whether a call at ``level`` may run without further approval.

        ``READ``, ``WRITE`` and ``EXECUTE`` are locally reversible and allowed;
        ``EXTERNAL_ACTION`` and ``DESTRUCTIVE`` require explicit confirmation so
        side-effects on the world are never an accident.
        """
        if level >= self.approval_required_from:
            return ApprovalDecision(
                allowed=False,
                reason=(
                    f"tool call at permission level {level.name} requires "
                    "explicit approval before it may run"
                ),
            )
        return ApprovalDecision(allowed=True)