"""Usage: token accounting for the live model path (Phase 5).

A tiny, honest metric so an operator (or a future surface) can see how much the
pydantic-ai adapters consumed. It is operational bookkeeping, not cognition: it never
influences a decision, and it is read from the model run results only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Usage:
    """Tokens consumed by the live model path, accumulated per adapter."""

    request_tokens: int = 0
    response_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.request_tokens + self.response_tokens

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            request_tokens=self.request_tokens + other.request_tokens,
            response_tokens=self.response_tokens + other.response_tokens,
        )


def read_run_usage(result: Any) -> Usage:
    """Read pydantic-ai run usage defensively, so versions may vary the shape.

    Returns a zero :class:`Usage` when the result carries no usage (offline models,
    futures, or a provider that does not report tokens) -- accounting never crashes
    the call that produced it.
    """
    recorded = getattr(result, "usage", None)
    if recorded is None:
        return Usage()
    request_tokens = getattr(recorded, "request_tokens", None)
    response_tokens = getattr(recorded, "response_tokens", None)
    return Usage(
        request_tokens=request_tokens if isinstance(request_tokens, int) else 0,
        response_tokens=response_tokens if isinstance(response_tokens, int) else 0,
    )