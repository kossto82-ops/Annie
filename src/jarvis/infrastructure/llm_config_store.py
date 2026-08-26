"""Apply and persist the LLM provider config, incl. the API key (Vision §32, §40).

The command center lets the developer switch provider *and hand over the API key* to
start testing against a live model. Two effects, kept separate so each is testable:

* :func:`stage` puts the chosen ``JARVIS_LLM_*`` values into the process environment so
  they take effect immediately (the very next :func:`build_perceiver` reads the key).
* :func:`persist` upserts those same values into a ``.env`` file so the choice — and the
  key — survive a restart, without clobbering unrelated lines.

The secret is write-only from the surface's point of view: it flows page -> local
server -> ``.env`` and process env, and is *never* read back into any reply or snapshot.
The ``.env`` file is git-ignored. This module never logs a value.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path

_PREFIX = "JARVIS_LLM_"
_ENV_FILE_VAR = "JARVIS_ENV_FILE"
_DEFAULT_ENV_FILE = ".env"

# The config keys the surface may set, mapped from the perceiver command's fields.
_FIELDS: dict[str, str] = {
    "provider": f"{_PREFIX}PROVIDER",
    "model": f"{_PREFIX}MODEL",
    "base_url": f"{_PREFIX}BASE_URL",
    "api_key": f"{_PREFIX}API_KEY",
}


def _updates(
    provider: str, model: str, base_url: str | None, api_key: str
) -> dict[str, str]:
    """The non-empty ``JARVIS_LLM_*`` values to set. Empty fields are left untouched."""
    values = {"provider": provider, "model": model, "base_url": base_url or "", "api_key": api_key}
    return {_FIELDS[name]: value for name, value in values.items() if value}


def stage(
    provider: str,
    model: str,
    base_url: str | None,
    api_key: str,
    *,
    environ: MutableMapping[str, str] | None = None,
) -> dict[str, str]:
    """Apply the chosen config to the live process environment; return what was set.

    Called before building the perceiver so the just-entered key is available to the
    generic adapter. Only non-empty values are set, so passing just a key updates only
    the key.
    """
    env = environ if environ is not None else os.environ
    updates = _updates(provider, model, base_url, api_key)
    env.update(updates)
    return updates


def persist(
    updates: dict[str, str],
    *,
    env_path: str | Path | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> Path:
    """Upsert ``updates`` into the ``.env`` file, atomically, keeping other lines intact.

    The path is ``env_path``, else ``JARVIS_ENV_FILE``, else ``.env`` in the working
    directory. Returns the file written. Writing nothing is a no-op that still returns
    the path.
    """
    env = environ if environ is not None else os.environ
    path = Path(env_path or env.get(_ENV_FILE_VAR) or _DEFAULT_ENV_FILE)
    if updates:
        _upsert(path, updates)
    return path


def _upsert(path: Path, updates: dict[str, str]) -> None:
    """Rewrite ``path`` with ``updates`` applied: replace matching keys in place, append
    the rest, and leave every other line (comments, unrelated vars) exactly as it was.
    """
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    lines: list[str] = []
    for line in existing:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in remaining:
            lines.append(f"{key}={remaining.pop(key)}")
        else:
            lines.append(line)
    lines.extend(f"{key}={value}" for key, value in remaining.items())
    content = "\n".join(lines) + "\n"
    # Write via a temp file + atomic replace so a crash can't leave a half-written
    # secrets file (and the key is never split across a partial write).
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
