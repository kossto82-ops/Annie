"""ProviderStats: live, healthy accounting of live-model calls (Phase 4).

Instrumentation, not cognition: a wrapper records *what actually happened* when a
`LanguageModel` or a model-driven `TaskAgent` was called -- how many times, how many
were honest successes, how long they took, and how many tokens they consumed. It never
influences a decision or a reply; it only makes the live frontier observable so an
operator (or a future surface) can see it is alive and how much it costs.

Calls accumulate behind an `InstrumentationStore` protocol so a consumer can pass the
in-memory default (or a future durable store); wrappers in one Jarvis instance share a
store, so commissioning, monitoring and sizing read a single number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from jarvis.infrastructure.usage import Usage


@dataclass(frozen=True, slots=True)
class ProviderCall:
    """A single live-model call as it was observed, for a committed record."""

    channel: str  # "chat" (LanguageModel.complete/stream) or "agent" (task loop)
    ok: bool
    duration_seconds: float
    usage: Usage


class InstrumentationStore(Protocol):
    """Where observed calls are accumulated and read back."""

    def record(self, call: ProviderCall) -> None: ...
    def snapshot(self) -> ProviderSnapshot: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderSnapshot:
    """Aggregate of every recorded live call, reported to a surface."""

    calls: int = 0
    successes: int = 0
    failures: int = 0
    chat_calls: int = 0
    agent_calls: int = 0
    total_seconds: float = 0.0
    slowest_seconds: float = 0.0
    usage: Usage = field(default_factory=Usage)

    @property
    def success_rate(self) -> float:
        return self.successes / self.calls if self.calls else 0.0

    def extend(self, call: ProviderCall) -> ProviderSnapshot:
        return ProviderSnapshot(
            calls=self.calls + 1,
            successes=self.successes + (1 if call.ok else 0),
            failures=self.failures + (0 if call.ok else 1),
            chat_calls=self.chat_calls + (1 if call.channel == "chat" else 0),
            agent_calls=self.agent_calls + (1 if call.channel == "agent" else 0),
            total_seconds=self.total_seconds + call.duration_seconds,
            slowest_seconds=max(self.slowest_seconds, call.duration_seconds),
            usage=self.usage + call.usage,
        )


class InMemoryInstrumentation:
    """The default live collector: an in-memory running total seen by a Jarvis."""

    def __init__(self) -> None:
        self._snapshot = ProviderSnapshot()

    def record(self, call: ProviderCall) -> None:
        self._snapshot = self._snapshot.extend(call)

    def snapshot(self) -> ProviderSnapshot:
        return self._snapshot