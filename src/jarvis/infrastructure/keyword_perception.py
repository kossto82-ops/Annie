"""A deliberately dumb rule-based PerceptionSource (Vision §32, §35).

This is NOT the intelligence -- it is the seam. It recognises a few certainty
cues in an observation and turns them into a single piece of `Evidence`, with a
weight from the strength of the cue and a polarity flipped by a negation word.
It knows nothing else: an observation with no recognised cue produces no evidence
at all (honest silence, Vision §37), rather than fabricating a reading.

Its whole purpose is to prove the boundary: a smarter perceiver (e.g. an
LLM-backed one) can drop in behind the same `PerceptionSource` Protocol without
the cognitive core changing (Vision §38). The rule stays dumb on purpose.
"""

from __future__ import annotations

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence

# Certainty cues → the raw weight the speaker's wording conveys. A short, honest
# vocabulary; unknown wording is simply not perceived.
_CUES: dict[str, float] = {
    "definitely": 1.0,
    "certainly": 1.0,
    "clearly": 0.9,
    "surely": 0.9,
    "probably": 0.6,
    "likely": 0.6,
    "maybe": 0.3,
    "might": 0.3,
    "possibly": 0.3,
}

# Words that flip a statement's polarity to contradicting.
_NEGATIONS: frozenset[str] = frozenset({"not", "no", "never", "n't", "cannot"})


class KeywordPerception:
    """Turns certainty cues in an observation into one piece of evidence."""

    def perceive(self, observation: str) -> tuple[Evidence, ...]:
        text = observation.strip()
        if not text:
            return ()
        lowered = text.lower()
        matched = [(cue, weight) for cue, weight in _CUES.items() if cue in lowered]
        if not matched:
            return ()  # nothing recognised -- stay silent (Vision §37)
        cue, weight = max(matched, key=lambda pair: pair[1])
        supports = not any(negation in lowered for negation in _NEGATIONS)
        # Stamp provenance so the weight is auditable, not magic (Vision §8): the
        # belief can later explain *why* this evidence carries the weight it does.
        # A perceived companion utterance is taken as their statement.
        return (
            Evidence(
                content=text,
                source=EvidenceSource.USER_STATEMENT,
                weight=Confidence(weight),
                supports=supports,
                context=f"perceived via the cue '{cue}'",
            ),
        )
