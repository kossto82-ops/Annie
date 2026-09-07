"""ReasoningSpan: the short-term thread of this conversation's reasoning.

Each message that produces a provisional answer is treated as a *step* in the
current reasoning span, not as a fresh, stateless model call: the span carries the
threads Jarvis has been reasoning through in this session, so a follow-up can resolve
references that reach back beyond the raw recent-dialogue window.

The §38 boundary holds here as everywhere: the language model only *proposes* answer
content. The span's life�cycle is driven by deterministic signals the domain already
reads -- a new answered query opens or revises a thread, a later query moves the
previous one on, and ``confirm`` seals (grounded by the learning loop, the thread then
leaves the span) or corrects (flagged as disputed, so it is never carried as an active
proposal again). No thread decision is ever delegated to the model.

The span is explicitly weaker than a belief (Vision §3): bounded (the oldest non-active
threads are evicted), session-scoped, never persisted, never evidence. Grounding
happens only through the normal belief loop once the companion confirms an answer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class ThreadPosture(Enum):
    """Honest state of one reasoning thread after the latest turn."""

    ACTIVE = "active"  # the newest answered question, still being carried
    MOVED_ON = "moved_on"  # superseded by a later question in the same session
    DISPUTED = "disputed"  # the companion corrected this proposal; stop asserting it


@dataclass(frozen=True, slots=True)
class SpanThread:
    """One step in the reasoning span, immutable and prompt-shaped as-is.

    ``trigger`` is the query Jarvis answered and ``statement`` the provisional answer
    it proposed. Nothing here is evidence; it is the honest trace of what was proposed,
    so the model can continue it and knows when a proposal was corrected.
    """

    trigger: str
    statement: str
    posture: ThreadPosture
    order: int


class ReasoningSpan:
    """Bounded, session-scoped short-term reasoning state across turns."""

    def __init__(self, capacity: int = 4) -> None:
        if capacity < 1:
            raise ValueError("A reasoning span needs capacity >= 1")
        self._capacity = capacity
        self._threads: list[SpanThread] = []
        self._order = 0

    def threads(self) -> tuple[SpanThread, ...]:
        """Newest first, for prompt shaping (the current thread leads)."""
        return tuple(reversed(self._threads))

    def record(self, trigger: str, statement: str) -> None:
        """Record answering ``trigger`` with ``statement`` as the next reasoning step.

        Revising the same trigger keeps one thread (its statement as of the latest
        turn); a new trigger opens a thread and moves the previously active one on.
        The oldest non-active threads are evicted once capacity is reached.
        """
        cleaned_trigger = trigger.strip()
        cleaned_statement = statement.strip()
        if not cleaned_trigger or not cleaned_statement:
            return
        self._order += 1
        for index, thread in enumerate(self._threads):
            if thread.trigger == cleaned_trigger:
                self._threads[index] = replace(
                    thread,
                    statement=cleaned_statement,
                    posture=ThreadPosture.ACTIVE,
                    order=self._order,
                )
                return
        for index, thread in enumerate(self._threads):
            if thread.posture is ThreadPosture.ACTIVE:
                self._threads[index] = replace(thread, posture=ThreadPosture.MOVED_ON)
        self._threads.append(
            SpanThread(
                trigger=cleaned_trigger,
                statement=cleaned_statement,
                posture=ThreadPosture.ACTIVE,
                order=self._order,
            )
        )
        self._evict()

    def resolve(self, trigger: str, affirm: bool) -> bool:
        """Record the companion's verdict on the newest thread matching ``trigger``.

        ``affirm`` seals the thread (the learning loop has grounded it -- it leaves the
        span, memory now owns it); ``False`` flags it as disputed so it is carried as a
        corrected proposal, never an active one. Returns whether a thread matched.
        """
        for index in range(len(self._threads) - 1, -1, -1):
            thread = self._threads[index]
            if thread.trigger != trigger:
                continue
            if affirm:
                del self._threads[index]  # grounded by the belief loop; span forgets it
            else:
                self._threads[index] = replace(
                    thread, posture=ThreadPosture.DISPUTED
                )
            return True
        return False

    def reset(self) -> None:
        """Drop the whole session span (a fresh session / topic)."""
        self._threads.clear()
        self._order = 0

    def _evict(self) -> None:
        while len(self._threads) > self._capacity:
            evictable = next(
                (
                    index
                    for index, thread in enumerate(self._threads)
                    if thread.posture is not ThreadPosture.ACTIVE
                ),
                0,
            )
            del self._threads[evictable]