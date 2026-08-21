"""Behavioural tests for the NervousSystem."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.events.domain_event import CognitiveEvent, DomainEvent
from jarvis.nervous_system.nervous_system import NervousSystem


@dataclass(frozen=True, slots=True, kw_only=True)
class _Ping(CognitiveEvent):
    label: str = "ping"


class TestDispatch:
    def test_subscriber_receives_published_event(self) -> None:
        system = NervousSystem()
        received: list[DomainEvent] = []
        system.subscribe(_Ping, received.append)

        event = _Ping(episode_id="e1")
        system.publish(event)
        assert received == []  # nothing delivered until dispatch
        system.dispatch()
        assert received == [event]

    def test_queue_is_cleared_after_dispatch(self) -> None:
        system = NervousSystem()
        received: list[DomainEvent] = []
        system.subscribe(_Ping, received.append)
        system.publish(_Ping(episode_id="e1"))
        system.dispatch()
        system.dispatch()  # second drain delivers nothing
        assert len(received) == 1

    def test_multiple_handlers_all_fire(self) -> None:
        system = NervousSystem()
        first: list[DomainEvent] = []
        second: list[DomainEvent] = []
        system.subscribe(_Ping, first.append)
        system.subscribe(_Ping, second.append)
        system.publish(_Ping(episode_id="e1"))
        system.dispatch()
        assert len(first) == 1
        assert len(second) == 1


class TestTypeMatching:
    def test_subscription_matches_subtypes(self) -> None:
        system = NervousSystem()
        seen: list[DomainEvent] = []
        system.subscribe(CognitiveEvent, seen.append)  # broad subscription
        ping = _Ping(episode_id="e1")
        system.publish(ping)
        system.dispatch()
        assert seen == [ping]

    def test_unrelated_type_is_not_delivered(self) -> None:
        system = NervousSystem()
        seen: list[DomainEvent] = []
        system.subscribe(_Ping, seen.append)
        system.publish(DomainEvent())  # not a _Ping
        system.dispatch()
        assert seen == []


class TestReentrantPublish:
    def test_event_published_during_dispatch_is_delivered(self) -> None:
        system = NervousSystem()
        seen: list[str] = []

        def on_ping(event: DomainEvent) -> None:
            seen.append("ping")
            if len(seen) == 1:
                system.publish(_Ping(episode_id="e2"))  # react by emitting another

        system.subscribe(_Ping, on_ping)
        system.publish(_Ping(episode_id="e1"))
        system.dispatch()
        assert seen == ["ping", "ping"]  # both drained in one dispatch
