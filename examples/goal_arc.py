"""The whole life of a goal, end to end (no LLM involved).

Run from the repo root:

    PYTHONPATH=src python examples/goal_arc.py

One persistent Jarvis walks the arc built across Increments 40-55: it takes on a
goal, keeps returning to it, learns it is stuck, wonders about it until it has
had enough, asks its companion for help, receives it, and ends believing the
goal is reachable -- the request warming once the companion has proven helpful.
Every belief here is derived from evidence and revisable; nothing is scripted.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.goal import Goal

# Fixed timestamps keep the example deterministic (no wall-clock branching): two
# well-spread, strong pieces ground a belief without looking overconfident, so the
# self-model stays quiet and curiosity can reach the goal it keeps failing.
_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _grounded() -> tuple[Evidence, ...]:
    return (
        Evidence(
            content="a solid reason",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(0.9),
            observed_at=_EPOCH,
        ),
        Evidence(
            content="a second solid reason later",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(0.9),
            observed_at=_EPOCH + timedelta(days=40),
        ),
    )


def main() -> None:
    jarvis = Jarvis.persistent(tempfile.mkdtemp())
    goal = Goal(statement="master recursion", success_criterion="solve it unaided")

    print("== take on a goal, and keep returning to it ==")
    jarvis.think("is my base case right?", evidence=_grounded(), goal=goal)
    jarvis.think("is my base case right?", goal=goal)
    jarvis.think("is my base case right?", goal=goal)
    print(" recurring goals:", jarvis.recurring_goals())

    print("\n== learn it is stuck ==")
    jarvis.mark_goal_reached(goal, reached=False)
    print(" ask for help now?:", jarvis.ask_for_help())  # None -- not exhausted yet

    print("\n== wonder about it until I have had enough ==")
    for _ in range(3):
        impulse = jarvis.feel_curious()
        assert impulse is not None
        print("  curious:", impulse.trigger)
        jarvis.pursue(impulse)
    print(" reflection effort:", jarvis.reflection_effort(goal.statement))
    print(" curiosity now    :", jarvis.feel_curious())  # None -- given up alone

    print("\n== ask the companion for help ==")
    print(" ", jarvis.ask_for_help())

    print("\n== receive help, and learn from it ==")
    jarvis.receive_help(goal)
    jarvis.receive_help(goal)
    print(" still stuck?:", jarvis.stuck_goals())  # () -- lifted
    belief = jarvis.belief_about_goal(goal)
    assert belief is not None
    print(" reachability:", round(belief.confidence.value, 2))

    print("\n== a warmed relationship, and the self-account ==")
    # A fresh stuck goal shows the ask is now warm (the companion has proven helpful).
    other = Goal(statement="prove the invariant")
    jarvis.think("does it hold at the boundary?", evidence=_grounded(), goal=other)
    jarvis.think("does it hold at the boundary?", goal=other)
    jarvis.think("does it hold at the boundary?", goal=other)
    jarvis.mark_goal_reached(other, reached=False)
    for _ in range(3):
        impulse = jarvis.feel_curious()
        assert impulse is not None
        jarvis.pursue(impulse)
    print(" ", jarvis.ask_for_help())
    print()
    print(jarvis.introspect())


if __name__ == "__main__":
    main()
