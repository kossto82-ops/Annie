"""Instrumented task agent: wrap a `TaskAgent` and observe each run (Phase 4).

The delegated counterpart of `InstrumentedLanguageModel`: a thin decorator over the
`TaskAgent` seam that records one `ProviderCall` (channel ``"agent"``) per ``run_task``
invocation -- whether the delegated task succeeded, its wall-clock duration, and the
tokens the underlying model-driven agent reported. Same shared `InstrumentationStore`,
so chat ``complete`` calls and ``run_task`` loops are totalled together per Jarvis.
"""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import cast

from jarvis.domain.retrieval.task_agent_source import TaskAgent
from jarvis.domain.value_objects.task_result import TaskResult
from jarvis.infrastructure.provider_stats import (
    InMemoryInstrumentation,
    InstrumentationStore,
    ProviderCall,
    ProviderSnapshot,
)
from jarvis.infrastructure.usage import Usage


class InstrumentedTaskAgent:
    """Wrap a `TaskAgent`, recording a `ProviderCall` (channel ``"agent"``) per run."""

    def __init__(
        self,
        inner: TaskAgent,
        *,
        instrumentation: InstrumentationStore | None = None,
    ) -> None:
        self._inner = inner
        self._instrumentation = instrumentation or InMemoryInstrumentation()

    @property
    def inner(self) -> TaskAgent:
        return self._inner

    def instrumentation(self) -> InstrumentationStore:
        return self._instrumentation

    def snapshot(self) -> ProviderSnapshot:
        return self._instrumentation.snapshot()

    def run_task(self, task: str) -> TaskResult:
        started = perf_counter()
        result = self._inner.run_task(task)
        self._instrumentation.record(
            ProviderCall(
                channel="agent",
                ok=result.success,
                duration_seconds=perf_counter() - started,
                usage=Usage(),
            )
        )
        return result

    def usage(self) -> Usage:
        """The inner agent's own bookkeeping, forwarded for parity (Phase 5)."""
        inner_usage = cast(
            "Callable[[], Usage]", getattr(self._inner, "usage", None)
        )
        return inner_usage() if callable(inner_usage) else Usage()


def instrument_agent(
    agent: TaskAgent,
    *,
    instrumentation: InstrumentationStore | None = None,
) -> InstrumentedTaskAgent:
    """Wrap a `TaskAgent` so every delegated run is observed and counted."""
    return InstrumentedTaskAgent(agent, instrumentation=instrumentation)