"""Tools: Jarvis's ability to act in the world (Vision §34).

Tools are extensions of Jarvis's ability to *act*, never of its ability to *think*
(Vision §34, §6): a Tool only executes; deciding *whether* to run it, and *what to
make of its outcome*, stays in the cognitive core. This package hosts the domain
Protocols and services that make a tool call travel the loop of 06_TOOLS_AGENCY:

    selection -> permission -> execution -> observation -> evaluation

Concrete tools live behind domain Protocols in :mod:`jarvis.infrastructure` (D7),
so the core never depends on a particular filesystem, shell, or HTTP client.
"""

from __future__ import annotations

from jarvis.domain.tools.tool_policy import ToolPolicy
from jarvis.domain.tools.tool_registry import ToolRegistry

__all__ = ["ToolPolicy", "ToolRegistry"]