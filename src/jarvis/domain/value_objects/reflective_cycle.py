"""ReflectiveCycle: the report of one full pass of the reflective loop (Vision §31).

Remember → Connect → Reflect → Hypothesise → Challenge → Learn, run end to end and
summarised: the load-bearing observation Jarvis noticed, the explanation it brewed,
the challenge it raised against it, and the belief it learned if the insight
survived. Any stage may be empty (there was nothing load-bearing, or the
hypothesis did not clear the bar) -- the summary is honest about where it stopped.

It is a report, not a new epistemic act: every field is what the derived stages
already produced.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.value_objects.challenge import Challenge
from jarvis.domain.value_objects.reflection import Reflection


@dataclass(frozen=True, slots=True, kw_only=True)
class ReflectiveCycle:
    """What one run of the reflective cycle produced."""

    reflection: Reflection | None  # the top load-bearing observation, if any
    hypothesis: str | None  # the leading explanation it brewed, if any
    challenge: Challenge | None  # the falsifier it raised, if any
    learned: str | None  # the statement of the belief it adopted, if any

    @property
    def produced_insight(self) -> bool:
        """True when the cycle carried an insight all the way to a learned belief."""
        return self.learned is not None
