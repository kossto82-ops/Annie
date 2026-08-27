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
import re
from collections.abc import Mapping, MutableMapping
from pathlib import Path

_PREFIX = "JARVIS_LLM_"
_ENV_FILE_VAR = "JARVIS_ENV_FILE"
_DEFAULT_ENV_FILE = ".env"
_LEGACY_KEY = f"{_PREFIX}API_KEY"


def _slug(provider: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", provider.upper()).strip("_")


def key_var(provider: str) -> str:
    """The env var that holds ``provider``'s API key — one slot PER provider.

    So a Groq key and an NVIDIA key coexist (`JARVIS_LLM_KEY_GROQ`, `JARVIS_LLM_KEY_NVIDIA`)
    and switching providers reuses each without re-entering it.
    """
    return f"{_PREFIX}KEY_{_slug(provider)}"


def model_var(provider: str) -> str:
    """The env var that holds ``provider``'s last model — one slot PER provider, so
    switching back to a provider restores its model without retyping it.
    """
    return f"{_PREFIX}MODEL_{_slug(provider)}"


def resolve_api_key(provider: str, environ: Mapping[str, str]) -> str | None:
    """The stored key for ``provider``: its own slot, else the legacy single key."""
    return environ.get(key_var(provider)) or environ.get(_LEGACY_KEY) or None


def resolve_model(provider: str, environ: Mapping[str, str]) -> str:
    """The stored model for ``provider``: its own slot, else the legacy single model."""
    return environ.get(model_var(provider)) or environ.get(f"{_PREFIX}MODEL") or ""


def _updates(
    provider: str, model: str, base_url: str | None, api_key: str
) -> dict[str, str]:
    """The non-empty ``JARVIS_LLM_*`` values to set. Empty fields are left untouched.

    A provided key is stored under this provider's own slot (`key_var`), never the shared
    one — so it persists alongside other providers' keys instead of overwriting them.
    """
    updates: dict[str, str] = {}
    if provider:
        updates[f"{_PREFIX}PROVIDER"] = provider  # the active provider
    if model and provider:
        updates[model_var(provider)] = model  # remembered per provider
    if base_url:
        updates[f"{_PREFIX}BASE_URL"] = base_url
    if api_key and provider:
        updates[key_var(provider)] = api_key  # remembered per provider
    return updates


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


def load_env_file(
    env_path: str | Path | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> None:
    """Load ``KEY=VALUE`` lines from ``.env`` into the environment at startup.

    The missing half of `persist`: a saved provider/model/key only resumes across a
    restart if something reads the file back. This is a tiny, dependency-free reader —
    it skips blanks and ``#`` comments, splits on the first ``=``, and **never overrides
    a variable already set in the real environment** (an explicit env var wins over the
    file). Absent file → no-op. Values (including the API key) are set, never logged.
    """
    env = environ if environ is not None else os.environ
    path = Path(env_path or env.get(_ENV_FILE_VAR) or _DEFAULT_ENV_FILE)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key and key not in env:  # a real environment variable always wins
            env[key] = value.strip()


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
