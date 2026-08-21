"""Behavioural tests for the event hierarchy."""

from __future__ import annotations

import dataclasses
from datetime import UTC

import pytest

from jarvis.domain.events.domain_event import CognitiveEvent, DomainEvent
from jarvis.domain.events.episode_events import EpisodeCompleted, EpisodeStarted


class TestMetadata:
    def test_each_event_gets_a_unique_id(self) -> None:
        assert DomainEvent().event_id != DomainEvent().event_id

    def test_occurred_at_is_timezone_aware_utc(self) -> None:
        assert DomainEvent().occurred_at.tzinfo == UTC

    def test_correlation_and_causation_default_to_none(self) -> None:
        event = DomainEvent()
        assert event.correlation_id is None
        assert event.causation_id is None

    def test_causal_metadata_is_preserved(self) -> None:
        started = EpisodeStarted(episode_id="e1", correlation_id="e1", trigger="t")
        completed = EpisodeCompleted(
            episode_id="e1",
            correlation_id="e1",
            causation_id=started.event_id,
            result="r",
        )
        assert completed.correlation_id == started.correlation_id == "e1"
        assert completed.causation_id == started.event_id


class TestImmutability:
    def test_domain_event_is_frozen(self) -> None:
        event = DomainEvent()
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.event_id = "tampered"  # type: ignore[misc]

    def test_cognitive_event_payload_is_frozen(self) -> None:
        event = EpisodeStarted(episode_id="e1", trigger="t")
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.trigger = "changed"  # type: ignore[misc]


class TestBinding:
    def test_cognitive_event_episode_id_is_optional(self) -> None:
        # A belief-related event can be emitted outside any single episode (D9).
        assert CognitiveEvent().episode_id is None

    def test_cognitive_event_can_carry_an_episode(self) -> None:
        assert CognitiveEvent(episode_id="e1").episode_id == "e1"

    def test_episode_events_carry_payload(self) -> None:
        assert EpisodeStarted(episode_id="e1", trigger="hello").trigger == "hello"
        assert EpisodeCompleted(episode_id="e1", result="done").result == "done"
