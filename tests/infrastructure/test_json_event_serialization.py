"""Cognitive events round-trip through JSON; every event type is registered."""

from __future__ import annotations

import pytest

from jarvis.domain.events.action_events import ActionOutcomeRecorded
from jarvis.domain.events.belief_events import (
    BeliefStrengthened,
    BeliefWeakened,
    ContradictionDetected,
)
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.events.episode_events import (
    EpisodeCompleted,
    EpisodeFailed,
    EpisodeReflected,
    EpisodeStarted,
)
from jarvis.domain.events.evidence_events import EvidenceAdded
from jarvis.domain.events.hypothesis_events import HypothesisCreated
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.infrastructure.json_event_serialization import (
    UnregisteredEventError,
    deserialise_event,
    serialise_event,
)


def _concrete_subclasses(base: type) -> set[type]:
    found: set[type] = set()
    for sub in base.__subclasses__():
        found.add(sub)
        found |= _concrete_subclasses(sub)
    return found


_SAMPLES: list[CognitiveEvent] = [
    EpisodeStarted(episode_id="e", correlation_id="e", trigger="why?"),
    EpisodeReflected(
        episode_id="e", correlation_id="e", note="well grounded", contested=False
    ),
    EpisodeCompleted(episode_id="e", correlation_id="e", result="done"),
    EpisodeFailed(episode_id="e", correlation_id="e", reason="boom"),
    EvidenceAdded(correlation_id="e", subject_id="b", evidence_id="v", supports=True),
    BeliefStrengthened(correlation_id="e", belief_id="b", confidence=Confidence(0.73)),
    BeliefWeakened(correlation_id="e", belief_id="b", confidence=Confidence(0.21)),
    ContradictionDetected(correlation_id="e", belief_id="b", evidence_id="v"),
    HypothesisCreated(correlation_id="e", hypothesis_id="h", statement="a common cause"),
    ActionOutcomeRecorded(
        correlation_id="e", action_id="a", description="did it", met_expectation=True
    ),
]


class TestRegistration:
    def test_every_cognitive_event_subclass_is_serialisable(self) -> None:
        # Guards the maintenance hazard: a new event type must be registered or its
        # sample round-trip below (and real traces) would fail. Only production event
        # types count (test modules may define throwaway subclasses).
        production = {
            cls
            for cls in _concrete_subclasses(CognitiveEvent)
            if cls.__module__.startswith("jarvis.domain.events")
        }
        covered = {type(sample) for sample in _SAMPLES}
        assert production == covered


class TestRoundTrip:
    @pytest.mark.parametrize("event", _SAMPLES, ids=lambda e: type(e).__name__)
    def test_serialise_then_deserialise_preserves_the_event(
        self, event: CognitiveEvent
    ) -> None:
        restored = deserialise_event(serialise_event(event))
        assert restored == event

    def test_confidence_survives_as_a_value_object(self) -> None:
        event = BeliefStrengthened(
            correlation_id="e", belief_id="b", confidence=Confidence(0.5)
        )
        restored = deserialise_event(serialise_event(event))
        assert isinstance(restored, BeliefStrengthened)
        assert isinstance(restored.confidence, Confidence)
        assert restored.confidence.value == pytest.approx(0.5)


class TestTolerance:
    def test_an_unknown_event_type_deserialises_to_none(self) -> None:
        assert deserialise_event({"type": "SomeFutureEvent", "event_id": "x"}) is None

    def test_serialising_an_unregistered_event_raises(self) -> None:
        class MadeUpEvent(CognitiveEvent):
            pass

        with pytest.raises(UnregisteredEventError):
            serialise_event(MadeUpEvent(correlation_id="e"))
