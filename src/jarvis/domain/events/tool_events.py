"""Events about tool runs (Vision §34, 06_TOOLS_AGENCY observability)."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.value_objects.tool_call import ToolCall


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallRecorded(CognitiveEvent):
    """A tool call was executed and its outcome recorded for later evaluation.

    Carries the immutable :class:`ToolCall` so a future model can reason over what
    Jarvis did, how it went, and what to learn from it (the ``evaluation`` step of
    the tool loop) without the raw exception crossing the cognitive boundary.
    """

    call: ToolCall