"""EchoTool: the simplest Tool, for verifying the registry loop end-to-end.

Echoes back the ``text`` argument verbatim. It is a demonstration edge
implementation: harmless (EXECUTE level, locally reversible) and deterministic, so
the full ``selection -> permission -> execution -> observation`` path can be tested
offline without touching files, shells, or the network (D8, 06_TOOLS_AGENCY).
"""

from __future__ import annotations

from jarvis.domain.enums.permission_level import PermissionLevel
from jarvis.domain.value_objects.tool_call_result import ToolCallResult
from jarvis.domain.value_objects.tool_spec import ToolSpec


class EchoTool:
    """A tool that echoes back its ``text`` argument."""

    spec = ToolSpec(
        name="echo",
        description="echo the given text back verbatim",
        args={"text": "the text to echo back"},
        permission=PermissionLevel.EXECUTE,
    )

    def run(self, arguments: dict[str, str]) -> ToolCallResult:
        text = arguments.get("text", "")
        return ToolCallResult(value=text, ok=True)