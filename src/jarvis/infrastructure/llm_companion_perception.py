"""LlmCompanionPerception: an LLM-backed CompanionPerceptionSource (Vision §5, §38).

The relational sibling of `LlmPerception`. It asks a `LanguageModel` to read what the
person said into stable facts *about the person themselves* — preferences, traits,
habits, situation, feelings — and turns each into a `CompanionObservation` (a trait plus
the evidence that grounds it). It depends only on the `LanguageModel` Protocol, so any
provider (or a test stub) plugs in unchanged.

The §38 boundary is the whole point: the model only *extracts candidate observations
about the companion* and how strongly the text asserts each — it does NOT decide what is
true. Confidence in any companion belief is still derived downstream from that evidence,
and the companion can contradict it later (Vision §5, §18). Unreadable or empty output
yields no observations (honest silence, §37) rather than an invented trait.
"""

from __future__ import annotations

from typing import Any, cast

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.perception.companion_perception import CompanionObservation
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.json_extraction import extract_json_array
from jarvis.infrastructure.language_model import LanguageModel

_INSTRUCTIONS = (
    "Read what the person said and extract stable facts ABOUT THE PERSON THEMSELVES "
    "— their preferences, traits, habits, situation, feelings, or values — NOT facts "
    "about the world. Respond with ONLY a JSON array. Each element is an object with "
    'keys: "trait" (string: a short third-person description of the person, e.g. '
    '"is learning Spanish", "prefers working late", "feels drained after releases"), '
    '"supports" (boolean: false only if the person denies or negates it), and '
    '"weight" (number strictly between 0 and 1: how strongly the text asserts it, not '
    "whether it is objectively true). If the text reveals nothing about the person, "
    "respond with []."
)


class LlmCompanionPerception:
    """Turns a language model's reading of an utterance into companion observations."""

    def __init__(self, model: LanguageModel) -> None:
        self._model = model

    def read_companion(self, utterance: str) -> tuple[CompanionObservation, ...]:
        text = utterance.strip()
        if not text:
            return ()
        raw = self._model.complete(f"{_INSTRUCTIONS}\n\nThe person said: {text}")
        return self._to_observations(raw, text)

    @staticmethod
    def _to_observations(raw: str, utterance: str) -> tuple[CompanionObservation, ...]:
        parsed = extract_json_array(raw)
        if parsed is None:
            return ()  # unreadable output -> stay silent (Vision §37)
        observations: list[CompanionObservation] = []
        for item in parsed:
            observation = _item_to_observation(item, utterance)
            if observation is not None:
                observations.append(observation)
        return tuple(observations)


def _item_to_observation(item: Any, utterance: str) -> CompanionObservation | None:
    if not isinstance(item, dict):
        return None
    data = cast("dict[str, Any]", item)
    trait = data.get("trait")
    weight = data.get("weight")
    supports = data.get("supports", True)
    if not isinstance(trait, str) or not trait.strip():
        return None
    if not isinstance(weight, int | float) or isinstance(weight, bool):
        return None
    if not 0.0 < float(weight) <= 1.0:
        return None  # out of range -> skip, never clamp (mirrors Confidence, D7)
    evidence = Evidence(
        content=utterance,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(float(weight)),
        supports=bool(supports),
        context="perceived about the companion via language model",
    )
    return CompanionObservation(trait=trait.strip(), evidence=evidence)
