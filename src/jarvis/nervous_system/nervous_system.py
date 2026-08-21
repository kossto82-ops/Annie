"""NervousSystem -- the signalling substrate that lets cognitive components
react to events without depending on one another directly.

This first implementation is deliberately minimal: ``subscribe`` registers a
handler for an event type, ``publish`` queues an event, and ``dispatch``
delivers all queued events to matching handlers. Handlers match by type *and
subtype* (subscribing to ``CognitiveEvent`` receives every subclass), so
components can listen broadly or narrowly.

Priority, routing, signal metadata, asynchronous delivery, backpressure and
cognitive-resource constraints are explicitly out of scope for now; they are
future evolutions of this same interface.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from jarvis.domain.events.domain_event import DomainEvent

Handler = Callable[[DomainEvent], None]


class NervousSystem:
    """A minimal synchronous publish/subscribe event dispatcher."""

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Handler]] = defaultdict(list)
        self._pending: list[DomainEvent] = []

    def subscribe(self, event_type: type[DomainEvent], handler: Handler) -> None:
        """Register ``handler`` to receive events of ``event_type`` (or subtypes)."""
        self._handlers[event_type].append(handler)

    def publish(self, event: DomainEvent) -> None:
        """Queue ``event`` for delivery on the next :meth:`dispatch`."""
        self._pending.append(event)

    def dispatch(self) -> None:
        """Deliver every queued event to all matching handlers, then clear the queue.

        New events published by a handler during dispatch are delivered in the
        same drain, so a reaction can trigger further reactions.
        """
        while self._pending:
            event = self._pending.pop(0)
            for registered_type, handlers in self._handlers.items():
                if isinstance(event, registered_type):
                    for handler in handlers:
                        handler(event)
