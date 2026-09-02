"""ToolCallResult: the outcome of one tool invocation.

A result carries the produced value and, for the observability trace, whether the
call succeeded and any error. The result feeds the *evaluation* step: Jarvis reasons
over what a tool returned rather than trusting it blindly (Vision §34). The result
itself contains no cognition -- it is data plus outcome.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallResult:
    """Outcome of a tool call: a value, success flag and optional error."""

    value: str = ""
    ok: bool = True
    error: str = ""