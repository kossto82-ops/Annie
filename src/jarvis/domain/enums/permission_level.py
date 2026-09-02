"""PermissionLevel: how risky a tool call is, and when it needs approval.

Permission levels gate *acts*, not thoughts (Vision §34, §28): they classify what a
tool may do so that destructiveness or external side-effects are never an accident.
Derived from the tool's declared ``ToolSpec``; a policy decides whether a given
level requires confirmation before execution.

Levels are ordered from least to most sensitive so a policy can compare them:
READ < WRITE < EXECUTE < EXTERNAL_ACTION < DESTRUCTIVE.
"""

from __future__ import annotations

from enum import IntEnum


class PermissionLevel(IntEnum):
    """Sensitivity of a tool call, ordered from least to most risky."""

    READ = 0
    WRITE = 1
    EXECUTE = 2
    EXTERNAL_ACTION = 3
    DESTRUCTIVE = 4