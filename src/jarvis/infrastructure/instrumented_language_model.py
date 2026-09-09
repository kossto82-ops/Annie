"""Instrumented model: wrap a `LanguageModel` and observe each call (Phase 4).

A thin, honest decorator over the `LanguageModel` seam. It holds a shared
`InstrumentationStore` and records one `ProviderCall` per ``complete``/``stream``
invocation -- outcome (did it return text vs fall silent), wall-clock duration, and the
tokens the underlying adapter reported. Splitting this from the adapter keeps the
counting universal: scripted, OpenAI-compatible, and pydantic-ai models are all
observed the same way, and an operator can compose with or without it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from time import perf_counter
from typing import cast

from jarvis.infrastructure.language_model import LanguageModel
from jarvis.infrastructure.provider_stats import (
    InMemoryInstrumentation,
    InstrumentationStore,
    ProviderCall,
    ProviderSnapshot,
)
from jarvis.infrastructure.usage import Usage


class InstrumentedLanguageModel:
    """Wrap a `LanguageModel`, recording a `ProviderCall` per invocation."""

    def __init__(
        self,
        inner: LanguageModel,
        *,
        instrumentation: InstrumentationStore | None = None,
    ) -> None:
        self._inner = inner
        self._instrumentation = instrumentation or InMemoryInstrumentation()

    @property
    def inner(self) -> LanguageModel:
        return self._inner

    def instrumentation(self) -> InstrumentationStore:
        return self._instrumentation

    def snapshot(self) -> ProviderSnapshot:
        return self._instrumentation.snapshot()

    def complete(self, prompt: str) -> str:
        started = perf_counter()
        output = self._inner.complete(prompt)
        self._record("chat", ok=bool(output), duration=perf_counter() - started)
        return output

    def stream(self, prompt: str) -> Iterator[str]:
        started = perf_counter()
        yielded = False
        stream_fn = cast(
            "Callable[[str], Iterator[str]]", getattr(self._inner, "stream", None)
        )
        if callable(stream_fn):
            for piece in stream_fn(prompt):
                if piece:
                    yielded = True
                    yield piece
        else:  # a model without a stream seam yields its finished answer in one piece
            answer = self._inner.complete(prompt)
            if answer:
                yielded = True
                yield answer
        self._record("chat", ok=yielded, duration=perf_counter() - started)

    def _record(self, channel: str, *, ok: bool, duration: float) -> None:
        self._instrumentation.record(
            ProviderCall(channel=channel, ok=ok, duration_seconds=duration, usage=Usage())
        )

    def usage(self) -> Usage:
        """The inner adapter's own bookkeeping, forwarded for parity (Phase 5)."""
        inner_usage = cast("Callable[[], Usage]", getattr(self._inner, "usage", None))
        return inner_usage() if callable(inner_usage) else Usage()


def instrument_model(
    model: LanguageModel,
    *,
    instrumentation: InstrumentationStore | None = None,
) -> InstrumentedLanguageModel:
    """Wrap a `LanguageModel` so every call is observed and counted."""
    return InstrumentedLanguageModel(model, instrumentation=instrumentation)