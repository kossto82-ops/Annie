"""Jarvis thinking about what it knows — the reflective cycle (no LLM involved).

Run from the repo root:

    PYTHONPATH=src python examples/reflecting.py

This walks the cycle built across Increments 74-80:
Remember → Connect → Reflect → Hypothesise → Challenge → Learn, self-triggered by
curiosity. Jarvis grounds several beliefs on one shared observation, then — with
no prompt — notices the pattern, wants to reflect, runs the whole cycle, and
adopts the insight as a new belief. A second run shows a refutation dethroning the
hypothesis. Everything is derived from evidence, revisable, and auditable.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _ev(content: str, *, at: datetime) -> Evidence:
    return Evidence(
        content=content,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(0.9),
        observed_at=at,
    )


def _ground(jarvis: Jarvis, cause: str) -> None:
    # Each belief rests on the *shared* observation plus its own reason, and its two
    # pieces are well spread in time — so each conclusion is grounded and not
    # overconfident (the self-model stays quiet), while the shared observation is
    # load-bearing across all of them (what Reflect will notice).
    for question in ("is the schedule at risk?", "should we cut scope?", "is morale ok?"):
        jarvis.think(
            question,
            evidence=[
                _ev(cause, at=_EPOCH),
                _ev(f"and separately: {question}", at=_EPOCH + timedelta(days=40)),
            ],
        )


def main() -> None:
    cause = "the client moved the deadline up"

    print("== several beliefs quietly come to rest on one observation ==")
    jarvis = Jarvis()
    _ground(jarvis, cause)
    finding = jarvis.reflect()[0]
    print(" ", finding.describe())

    print("\n== unprompted, Jarvis wants to reflect ==")
    impulse = jarvis.feel_curious()
    assert impulse is not None
    print("  curious:", impulse.trigger)

    print("\n== pursuing it runs the whole cycle (Connect ... Learn) ==")
    jarvis.pursue(impulse)
    learned = next(
        b for b in jarvis.beliefs.all_beliefs() if "is a common cause" in b.statement
    )
    print("  learned:", learned.statement)
    print("  adopted, unprompted, at confidence", round(learned.confidence.value, 2))
    print("  curious again?:", jarvis.feel_curious(), "(the pattern is mined; it rests)")

    print("\n== a mind that challenges itself: a refutation can dethrone the insight ==")
    fresh = Jarvis()
    _ground(fresh, cause)
    challenge = fresh.challenge()
    assert challenge is not None
    print(" ", challenge.describe())
    fresh.refute(cause, "Working conclusion about: is morale ok?")
    fresh.refute(cause, "Working conclusion about: should we cut scope?")
    print("  after two counterexamples, hypothesis:", fresh.hypothesise())


if __name__ == "__main__":
    main()
