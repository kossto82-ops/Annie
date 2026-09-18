"""A deliberately dumb rule-based PerceptionSource (Vision §32, §35).
This is NOT the intelligence -- it is the seam. It recognises a few certainty
cues in an observation and turns them into a single piece of `Evidence`, with a
weight from the strength of the cue. Negation recognition and polarity direction
delegate to the abstraction layer's shared normalization (contraction expansion,
marker parity, valence), so both layers always read the same phrase the same
way; the perception seam itself adds no interpretation. An observation with no
recognised cue produces no evidence at all (honest silence, Vision §37), rather
than fabricating a reading.

Its whole purpose is to prove the boundary: a smarter perceiver (e.g. an
LLM-backed one) can drop in behind the same `PerceptionSource` Protocol without
the cognitive core changing (Vision §38). The rule stays dumb on purpose.
"""

from __future__ import annotations

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.abstraction import (
    NEGATION_MARKERS,
    conceptual_tokens,
    expand_contractions,
    valence,
)
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

# Negation is the abstraction layer's own normalized contract (NEGATION_MARKERS
# plus contraction expansion): the perception seam must not keep a second
# negation vocabulary, or the two layers could read the same phrase differently
# (H4). It only handles certainty-detection and affirmation/denial direction.
_NEGATION_WINDOW = 3


def _strip(word: str) -> str:
    """A bare token: lowercased already, with surrounding punctuation removed."""
    return word.strip(".,;:!?\"'()[]")


class KeywordPerception:
    """Turns certainty cues in an observation into one piece of evidence per cue."""

    def describe(self) -> dict[str, str | None]:
        """Self-report for a surface: the dumb, offline, no-LLM perceiver (Vision §35)."""
        return {"kind": "keyword", "provider": "keyword", "model": None}

    def perceive(self, observation: str) -> tuple[Evidence, ...]:
        text = observation.strip()
        if not text:
            return ()
        words = [_strip(w) for w in expand_contractions(text).split()]
        # One piece of evidence per recognised cue, in the order it appears -- so a
        # multi-cue observation ("definitely X but maybe not Y") yields several
        # readings rather than being flattened to one (Vision §8, §17). Subjects are
        # not parsed here (that is a smarter perceiver's job); every piece still
        # bears on the one belief the episode is about.
        evidence: list[Evidence] = []
        for index, word in enumerate(words):
            weight = _CUES.get(word)
            if weight is None:
                continue
            supports, neutral = self._reading(
                text, self._negated_near(words, index)
            )
            evidence.append(
                Evidence(
                    content=text,
                    source=EvidenceSource.USER_STATEMENT,
                    weight=Confidence(weight),
                    supports=supports,
                    is_neutral=neutral,
                    # Stamp provenance so the weight is auditable (Vision §8): the
                    # belief can later explain why this evidence carries this weight.
                    context=f"perceived via the cue '{word}'",
                )
            )
        return tuple(evidence)

    @staticmethod
    def _negated_near(words: list[str], index: int) -> bool:
        """True when a negation marker sits within a few words of the cue.

        The window scans the *expanded* tokens (contractions normalized), and the
        marker set is the abstraction layer's NEGATION_MARKERS -- so this is the
        same phrase reading the valence parity counter sees, never a second
        negation vocabulary (H4).
        """
        window = words[max(0, index - _NEGATION_WINDOW) : index + _NEGATION_WINDOW + 1]
        return any(word in NEGATION_MARKERS for word in window)

    @staticmethod
    def _reading(observation: str, negated: bool) -> tuple[bool, bool]:
        """Evidence direction as ``(supports, is_neutral)`` for one cued phrase.

        An affirmation always supports. A denial contradicts the belief, except
        when the observation carries explicit polarity (a FAIL/SUCCEED outcome
        token) or negated role matter (the DELIVER class) -- then the
        abstraction's shared reading is authoritative, so both layers agree on
        direction: polar phrases follow its sign, negated dimension verbs stay
        neutral (M2) and are skipped by confidence.
        """
        if not negated:
            return True, False
        polar = valence(observation)
        if polar == "positive":
            return True, False
        if polar == "negative":
            return False, False
        if conceptual_tokens(observation):
            # Negated dimension/role matter: no polarity signal (M2).
            return True, True
        return False, False
