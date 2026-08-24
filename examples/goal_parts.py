"""A goal made of parts, worked one blocker at a time (no LLM involved).

Run from the repo root:

    PYTHONPATH=src python examples/goal_parts.py

Where examples/main_loop.py walks the core loop and examples/goal_arc.py walks an
atomic goal, this shows the decomposition machinery (Increments 57-61): a goal
made of parts, some reached and some not, curiosity fixing on the *specific*
unreached part, an ask that names that part, and help that advances exactly it --
with progress climbing one part at a time. Every belief is derived from evidence.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.goal import Goal

# Fixed timestamps keep the example deterministic: two well-spread, strong pieces
# ground a belief without looking overconfident, so the self-model stays quiet and
# curiosity is free to fix on the goal's blocking part.
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
    whole = Goal(statement="prove the theorem")
    parts = ("state the lemma", "prove the base case", "prove the inductive step")

    print("== a goal made of parts, one already done ==")
    for _ in range(3):
        jarvis.think("is the lemma sound?", evidence=_grounded(), goal=whole)
    jarvis.mark_goal_reached(Goal(statement=parts[0], part_of=whole.statement))
    for part in parts[1:]:
        jarvis.mark_goal_reached(Goal(statement=part, part_of=whole.statement), reached=False)
    jarvis.mark_goal_reached(whole, reached=False)  # the whole is not there yet
    print(" parts   :", jarvis.sub_goals(whole.statement))
    print(" progress:", jarvis.goal_progress(whole.statement))

    print("\n== curiosity fixes on the specific blocking part ==")
    for _ in range(3):
        impulse = jarvis.feel_curious()
        assert impulse is not None
        print("  curious:", impulse.trigger)
        jarvis.pursue(impulse)

    print("\n== ask names the blocker, help advances exactly it ==")
    print(" ask       :", jarvis.ask_for_help())
    jarvis.receive_help(whole)
    print(" progress  :", jarvis.goal_progress(whole.statement))
    print(" next ask  :", jarvis.ask_for_help())
    jarvis.receive_help(whole)
    print(" progress  :", jarvis.goal_progress(whole.statement))

    print("\n== the self-account shows the structure ==")
    line = next(
        row
        for row in jarvis.introspect().splitlines()
        if row.strip().startswith(f"- {whole.statement} (")
    )
    print(line.strip())


if __name__ == "__main__":
    main()
