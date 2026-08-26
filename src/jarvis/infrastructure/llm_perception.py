"""LlmPerception: an LLM-backed PerceptionSource (Vision §32, §8, §38).

A `PerceptionSource` that asks a `LanguageModel` to read an observation into
candidate claims, then turns each claim into `Evidence`. It depends only on the
`LanguageModel` Protocol, so it is provider-agnostic: any model (real or a test
stub) plugs in unchanged.

The Vision §38 boundary is enforced here and is the whole point: the model only
*extracts candidate evidence* -- it reports the claims a text makes and how
strongly the text asserts each (NOT whether they are true). Confidence in any
belief is still derived downstream from that evidence, and the executive still
decides. A model that returns nothing usable yields no evidence (honest silence,
§37) rather than a fabricated reading.
"""

from __future__ import annotations

import json
from typing import Any, cast

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.language_model import LanguageModel

_INSTRUCTIONS = (
    "Read the observation and extract the factual claims it makes. Respond with "
    "ONLY a JSON array. Each element is an object with keys: "
    '"content" (string: the claim), '
    '"supports" (boolean: false only if the text negates the claim), and '
    '"weight" (number strictly between 0 and 1: how strongly the TEXT asserts it, '
    "not whether it is true). If the text makes no claims, respond with []."
)


class LlmPerception:
    """Turns a language model's reading of an observation into evidence."""

    def __init__(
        self,
        model: LanguageModel,
        *,
        provider: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self._model = model
        # Identity for self-report only (which provider/model is live) -- never used
        # in judgment. Optional so a bare LlmPerception(model) still works unchanged.
        self._provider = provider
        self._model_name = model_name

    def describe(self) -> dict[str, str | None]:
        """Self-report for a surface: which LLM provider/model is producing evidence.

        Purely descriptive (Vision §38): it names the capability provider, it does not
        decide anything.
        """
        return {"kind": "llm", "provider": self._provider, "model": self._model_name}

    def perceive(self, observation: str) -> tuple[Evidence, ...]:
        text = observation.strip()
        if not text:
            return ()
        raw = self._model.complete(f"{_INSTRUCTIONS}\n\nObservation: {text}")
        return self._to_evidence(raw)

    @staticmethod
    def _to_evidence(raw: str) -> tuple[Evidence, ...]:
        try:
            parsed: Any = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return ()  # unreadable output -> stay silent (Vision §37)
        if not isinstance(parsed, list):
            return ()
        evidence: list[Evidence] = []
        for claim in cast("list[Any]", parsed):
            piece = _claim_to_evidence(claim)
            if piece is not None:
                evidence.append(piece)
        return tuple(evidence)


def _claim_to_evidence(claim: Any) -> Evidence | None:
    if not isinstance(claim, dict):
        return None
    data = cast("dict[str, Any]", claim)
    content = data.get("content")
    weight = data.get("weight")
    supports = data.get("supports", True)
    if not isinstance(content, str) or not content.strip():
        return None
    if not isinstance(weight, int | float) or isinstance(weight, bool):
        return None
    if not 0.0 < float(weight) <= 1.0:
        return None  # out of range -> skip, never clamp (mirrors Confidence, D7)
    return Evidence(
        content=content.strip(),
        source=EvidenceSource.EXTERNAL_SOURCE,
        weight=Confidence(float(weight)),
        supports=bool(supports),
        context="perceived via language model",
    )
