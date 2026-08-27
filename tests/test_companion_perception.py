"""The relational channel: learning about the companion from an utterance (§5, §38).

Offline and deterministic — the LLM is a fake model returning canned JSON, so the
extraction + folding into the companion model is exercised without a network.
"""

from __future__ import annotations

from jarvis import Jarvis
from jarvis.domain.perception.companion_perception import (
    CompanionObservation,
    CompanionPerceptionSource,
)
from jarvis.infrastructure.llm_companion_perception import LlmCompanionPerception
from jarvis.infrastructure.silent_companion_perception import SilentCompanionPerception


class _FakeModel:
    """A LanguageModel stub that always returns the same completion."""

    def __init__(self, completion: str) -> None:
        self._completion = completion

    def complete(self, prompt: str) -> str:
        return self._completion


class TestSilentCompanionPerception:
    def test_it_reveals_nothing(self) -> None:
        assert SilentCompanionPerception().read_companion("I love hiking") == ()


class TestLlmCompanionPerception:
    def test_it_extracts_traits_as_observations(self) -> None:
        model = _FakeModel(
            '[{"trait": "is learning Spanish", "supports": true, "weight": 0.8}]'
        )
        observations = LlmCompanionPerception(model).read_companion("I'm learning Spanish")
        assert len(observations) == 1
        assert observations[0].trait == "is learning Spanish"
        assert observations[0].evidence.supports is True
        assert observations[0].evidence.weight.value == 0.8

    def test_unreadable_output_is_silent(self) -> None:
        assert LlmCompanionPerception(_FakeModel("not json")).read_companion("hi") == ()

    def test_out_of_range_weight_is_skipped_not_clamped(self) -> None:
        model = _FakeModel('[{"trait": "x", "supports": true, "weight": 2.0}]')
        assert LlmCompanionPerception(model).read_companion("x") == ()

    def test_empty_utterance_stays_silent(self) -> None:
        assert LlmCompanionPerception(_FakeModel("[]")).read_companion("  ") == ()

    def test_a_fenced_or_wrapped_json_array_is_still_read(self) -> None:
        # Reasoning models often wrap the array in a ```json fence or prose.
        fenced = '```json\n[{"trait": "likes hiking", "supports": true, "weight": 0.7}]\n```'
        observations = LlmCompanionPerception(_FakeModel(fenced)).read_companion("...")
        assert len(observations) == 1
        assert observations[0].trait == "likes hiking"


class _ScriptedCompanion(CompanionPerceptionSource):
    """Yields fixed observations, for testing the Jarvis-level wiring offline."""

    def __init__(self, *observations: CompanionObservation) -> None:
        self._observations = observations

    def read_companion(self, utterance: str) -> tuple[CompanionObservation, ...]:
        return self._observations


class TestNoteCompanion:
    def test_it_folds_observations_into_the_companion_model(self) -> None:
        model = _FakeModel(
            '[{"trait": "prefers working late", "supports": true, "weight": 0.9}]'
        )
        jarvis = Jarvis(companion_perception=LlmCompanionPerception(model))
        learned = jarvis.note_companion("I always work best at night")
        assert [b.statement for b in learned] == ["prefers working late"]
        # It is now a real, revisable belief in the companion model.
        belief = jarvis.companion.belief_about("prefers working late")
        assert belief is not None
        assert belief.confidence.value > 0.0

    def test_the_default_jarvis_learns_nothing_from_conversation(self) -> None:
        # Offline default is silent — no fabricated traits (Vision §37).
        jarvis = Jarvis()
        assert jarvis.note_companion("I love the mountains") == ()

    def test_the_companion_perceiver_can_be_swapped_at_runtime(self) -> None:
        jarvis = Jarvis()
        assert isinstance(jarvis.companion_perception, SilentCompanionPerception)
        jarvis.set_companion_perception(_ScriptedCompanion())
        assert not isinstance(jarvis.companion_perception, SilentCompanionPerception)
