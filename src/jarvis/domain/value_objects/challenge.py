"""Challenge: the test that would refute a hypothesis (Vision §11, §17, §37).

Cycle stage four. Having proposed that an observation is a common cause
(Increment 76), a mind that only *confirms* its own guesses is not thinking. A
Challenge names, concretely, what would *falsify* the leading hypothesis: if a
belief that rests on the observation would still hold with the observation gone,
the common cause is wrong. It asserts nothing about the hypothesis being false --
it states the test, so the refutation can be sought (and, when found, dethrones
the hypothesis by removing what it explained).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Challenge:
    """A leading hypothesis and the concrete evidence that would refute it."""

    hypothesis: str  # the statement being challenged
    observation: str  # the load-bearing observation it rests on
    falsifier: str  # what, if true, would refute the hypothesis
    beliefs: tuple[str, ...]  # the beliefs the hypothesis claims to explain

    def describe(self) -> str:
        return f"I hold that {self.hypothesis}. But {self.falsifier}"
