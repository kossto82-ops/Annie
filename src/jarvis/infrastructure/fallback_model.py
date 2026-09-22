"""A LanguageModel with automatic fallback to a backup provider.

When the primary model fails (network error, timeout, provider error),
the fallback model is tried. This gives Jarvis resilience against provider
outages without changing the core cognition (Vision §38, D6).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import cast

from jarvis.infrastructure.language_model import LanguageModel

_log = logging.getLogger(__name__)


def _stream_of(model: LanguageModel, prompt: str) -> Iterator[str]:
    """The model's stream seam when it has one, else its completion in one piece.

    Mirrors the probe used by the reasoner/renderer/instrumentation: the
    ``LanguageModel`` seam is deliberately tiny (``complete`` only), so streaming
    is detected, never assumed.
    """
    stream_fn = cast("Callable[[str], Iterator[str]]", getattr(model, "stream", None))
    if callable(stream_fn):
        yield from stream_fn(prompt)
    else:
        answer = model.complete(prompt)
        if answer:
            yield answer


class FallbackLanguageModel:
    """Tries the primary model, falls back to a backup on failure."""

    def __init__(
        self,
        primary: LanguageModel,
        backup: LanguageModel,
        *,
        backup_errors: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        self._primary = primary
        self._backup = backup
        self._backup_errors = backup_errors

    def complete(self, prompt: str) -> str:
        try:
            result = self._primary.complete(prompt)
            if result.strip():
                return result
            # Empty result from primary -> try backup
            _log.debug("primary returned empty, trying backup")
        except self._backup_errors as exc:
            _log.warning("primary failed (%s: %s), trying backup", type(exc).__name__, exc)
        return self._backup.complete(prompt)

    def stream(self, prompt: str) -> Iterator[str]:
        try:
            chunks = list(_stream_of(self._primary, prompt))
            text = "".join(chunks).strip()
            if text:
                return iter(chunks)
            # Empty stream from primary -> try backup
            _log.debug("primary stream empty, trying backup")
        except self._backup_errors as exc:
            _log.warning(
                "primary stream failed (%s: %s), trying backup",
                type(exc).__name__,
                exc,
            )
        return _stream_of(self._backup, prompt)
