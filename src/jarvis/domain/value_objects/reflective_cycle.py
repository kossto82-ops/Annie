"""ReflectiveCycle: the report of one full pass of the reflective loop (Vision §31).

Connect → Reflect → Hypothesise → Challenge → Learn → Act, run end to end and
summarised: the beliefs it linked by shared evidence, the load-bearing observation
it noticed, the explanation it brewed, the challenge it raised against it, the
belief it learned if the insight survived, and the action it would take on that
insight. Any stage may be empty (there was nothing load-bearing, or the hypothesis
did not clear the bar) -- the summary is honest about where it stopped.

It is a report, not a new epistemic act: every field is what the derived stages
already produced. The Learn stage is the one that also changes state (it adopts a
surviving insight as a belief); Act only *recommends* (autonomy is earned, §28).
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.value_objects.action_recommendation import ActionRecommendation
from jarvis.domain.value_objects.challenge import Challenge
from jarvis.domain.value_objects.connection import Connection
from jarvis.domain.value_objects.reflection import Reflection


@dataclass(frozen=True, slots=True, kw_only=True)
class ReflectiveCycle:
    """What one run of the reflective cycle produced."""

    connections: tuple[Connection, ...]  # beliefs linked by shared evidence (Connect)
    reflection: Reflection | None  # the top load-bearing observation, if any
    hypothesis: str | None  # the leading explanation it brewed, if any
    challenge: Challenge | None  # the falsifier it raised, if any
    learned: str | None  # the statement of the belief it adopted, if any
    action: ActionRecommendation | None  # the stance it would take on the insight (Act)

    @property
    def produced_insight(self) -> bool:
        """True when the cycle carried an insight all the way to a learned belief."""
        return self.learned is not None

    @property
    def reached_action(self) -> bool:
        """True when a learned insight went all the way to a recommended action."""
        return self.action is not None
