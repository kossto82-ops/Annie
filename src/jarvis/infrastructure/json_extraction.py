"""Extract a JSON array from a language model's reply, tolerantly (Vision §37).

Models are asked for "ONLY a JSON array", but they don't always comply: some wrap it in
a ```json fence, some add a sentence before or after. Rather than reject all of that as
unreadable, pull out the first ``[`` … last ``]`` span and parse it. Anything that still
isn't a JSON array yields ``None`` — honest silence, never a fabricated reading.
"""

from __future__ import annotations

import json
from typing import Any, cast


def extract_json_array(raw: object) -> list[Any] | None:
    """Return the JSON array embedded in ``raw`` (fenced or bare), or None.

    ``raw`` is typed ``object`` because it is untrusted model output: a
    non-string reply is tolerated as unreadable (``None``) rather than trusted.
    """
    if not isinstance(raw, str):
        return None
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed: Any = json.loads(raw[start : end + 1])
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(parsed, list):
        return cast("list[Any]", parsed)
    return None
