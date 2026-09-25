"""Charitable instruction compiler — free text to decided-script, deterministically.

A material instruction *executes* through the earned-agency executor (Vision
§27-28). With a live provider, a model turns free text into a multi-step act; the
*offline* charitable executor can only run **decided scripts** (no free-text LLM
needed, roadmap F6c). This service is the deterministic hinge: it compiles the
small, unambiguous instruction envelopes the core already understands into the
decided-script format — ``tool key="value"`` per line — without guessing.

It never reasons about ambiguous requests: unmatched text compiles to ``None`` and
honestly declines downstream. It only ever emits locally reversible sandbox acts
(filesystem read/write, echo); a destructive or external step is **never
compiled** here — an explicit user script containing one still hits the registry
policy gate and refuses.
"""

from __future__ import annotations

import re

# A filename-like path: word chars, dashes, dots and slashes, no spaces. Keeping
# the path space-free makes the envelope unambiguous ("con" can only be the
# content separator, never part of a name).
_PATH = r"[\w\-.]+"

# ES: "escribe un archivo notas.txt con Hola mundo"
_ES_WRITE = re.compile(
    r"^(?:escribe|crea|guarda)\s+un\s+archivo\s+(?P<path>"
    + _PATH
    + r")(?:\s+(?:con\s+el\s+contenido|con\s+el\s+texto|"
    r"que\s+contenga|que\s+diga|con)\s+(?P<content>.+?))?\s*$"
)
# EN: "write a file notes.txt with Hello world"
_EN_WRITE = re.compile(
    r"^(?:write|create|save)\s+(?:a\s+)?file\s+(?P<path>"
    + _PATH
    + r")(?:\s+(?:with\s+the\s+content|with\s+the\s+text|with\s+content|"
    r"that\s+(?:says|contains)|containing|with)\s+(?P<content>.+?))?\s*$"
)
_ES_READ = re.compile(r"^(?:lee|abre)\s+(?:el\s+)?archivo\s+(?P<path>" + _PATH + r")\s*$")
_EN_READ = re.compile(r"^(?:read|open)\s+(?:the\s+)?file\s+(?P<path>" + _PATH + r")\s*$")
_ES_ECHO = re.compile(r"^(?:dime|di|repite)\s+(?P<text>.+)$")
_EN_ECHO = re.compile(r"^(?:say|echo)\s+(?P<text>.+)$")


def _quote(value: str) -> str:
    """Quote a value for the decided-script grammar (double quotes in the value)."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def compile_charitable_instruction(text: str) -> str | None:
    """Compile an unambiguous instruction envelope into a decided-script text.

    Returns a one-line decided-script in the ``tool key=value`` grammar, or
    ``None`` when the request needs real freedom (a live provider) or deserves an
    honest decline. Order: write, read, echo — a request that matches several
    shapes compiles to the most specific enclosure first.
    """
    stripped = text.strip()
    if not stripped:
        return None

    match = _ES_WRITE.match(stripped) or _EN_WRITE.match(stripped)
    if match is not None:
        path = match.group("path")
        content = match.group("content") or ""
        return (
            "filesystem operation=write "
            f'path={_quote(path)} content={_quote(content.rstrip())}'
        )

    match = _ES_READ.match(stripped) or _EN_READ.match(stripped)
    if match is not None:
        return f"filesystem operation=read path={_quote(match.group('path'))}"

    match = _ES_ECHO.match(stripped) or _EN_ECHO.match(stripped)
    if match is not None:
        return f"echo text={_quote(match.group('text').strip())}"

    return None