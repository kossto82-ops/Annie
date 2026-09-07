"""Challenge: the test that would refute a hypothesis (Vision §11, §17, §37).

Cycle stage four. Having proposed that an observation is a common cause
(Increment 76), a mind that only *confirms* its own guesses is not thinking. A
Challenge names, concretely, what would *falsify* the leading hypothesis: if a
belief that rests on the observation would still hold with the observation gone,
the common cause is wrong. It asserts nothing about the hypothesis being false --
it states the test, so the refutation can be sought (and, when found, dethrones
the hypothesis by removing what it explained).

The challenge also carries the leading hypothesis's *derived* axes (Increment 146):
its confidence and its temporal stability. They are reported, never decisive --
stability is the same anti-overfit signal beliefs already narrate (Vision §11): a
hypothesis supported only by a recent burst is flagged as such, without its derived
strength being touched.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.entities.belief import LOW_STABILITY_THRESHOLD
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.temporal_stability import TemporalStability


@dataclass(frozen=True, slots=True, kw_only=True)
class Challenge:
    """A leading hypothesis and the concrete evidence that would refute it."""

    hypothesis: str  # the statement being challenged
    observation: str  # the load-bearing observation it rests on
    falsifier: str  # what, if true, would refute the hypothesis
    beliefs: tuple[str, ...]  # the beliefs the hypothesis claims to explain
    confidence: Confidence  # the leading hypothesis's derived confidence
    stability: TemporalStability  # how steadily that support has held over time

    def describe(self) -> str:
        text = f"I hold that {self.hypothesis}. But {self.falsifier}"
        if self.stability.value < LOW_STABILITY_THRESHOLD:
            text += (
                " (Caution: this rests on a narrow time window — "
                "possible overfitting to recent events.)"
            )
        return text