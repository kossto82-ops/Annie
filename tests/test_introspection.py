"""Tests for Jarvis narrating itself from real state (Vision §29, §30, §40)."""

from __future__ import annotations

from datetime import UTC, datetime

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _ev(weight: float, *, at: datetime | None = None) -> Evidence:
    kwargs: dict[str, object] = {
        "content": "an observation",
        "source": EvidenceSource.USER_STATEMENT,
        "weight": Confidence(weight),
    }
    if at is not None:
        kwargs["observed_at"] = at
    return Evidence(**kwargs)  # type: ignore[arg-type]


class TestIntrospect:
    def test_a_fresh_jarvis_admits_it_knows_little(self) -> None:
        text = Jarvis().introspect()
        assert "have not yet noticed any consistent tendencies" in text
        assert "do not yet know much about them" in text
        assert "0 past episode(s)" in text

    def test_it_surfaces_a_recognised_self_tendency(self) -> None:
        jarvis = Jarvis()
        for topic in ("a", "b", "c"):
            # grounded but same-instant evidence -> overconfidence
            jarvis.think(f"q {topic}", evidence=[_ev(0.9, at=_EPOCH), _ev(0.9, at=_EPOCH)])
        text = jarvis.introspect()
        assert "overconfident on thin evidence" in text

    def test_it_surfaces_what_it_believes_about_its_companion(self) -> None:
        jarvis = Jarvis()
        jarvis.observe_companion("prefers simplicity", _ev(0.9))
        text = jarvis.introspect()
        assert "prefers simplicity" in text

    def test_it_invents_nothing_it_does_not_hold(self) -> None:
        # A trait never observed must not appear in the self-account.
        text = Jarvis().introspect()
        assert "prefers simplicity" not in text

    def test_it_surfaces_a_recurring_goal(self) -> None:
        from jarvis.domain.value_objects.goal import Goal

        jarvis = Jarvis()
        goal = Goal(statement="ship the parser")
        for question in ("q1", "q2", "q3"):
            jarvis.think(question, goal=goal)
        text = jarvis.introspect()
        assert "What I keep returning to:" in text
        assert "ship the parser (3 times)" in text

    def test_a_goal_less_jarvis_says_nothing_about_recurring_goals(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a plain question")
        assert "keep returning to" not in jarvis.introspect()

    def test_a_reached_recurring_goal_reads_as_reachable(self) -> None:
        from jarvis.domain.value_objects.goal import Goal

        jarvis = Jarvis()
        goal = Goal(statement="ship the parser")
        for question in ("q1", "q2", "q3"):
            jarvis.think(question, goal=goal)
        jarvis.mark_goal_reached(goal)
        jarvis.mark_goal_reached(goal)
        text = jarvis.introspect()
        assert "ship the parser (3 times)" in text
        assert "I have learned I can reach this" in text

    def test_a_failed_recurring_goal_reads_as_unmet(self) -> None:
        from jarvis.domain.value_objects.goal import Goal

        jarvis = Jarvis()
        goal = Goal(statement="ship the parser")
        for question in ("q1", "q2", "q3"):
            jarvis.think(question, goal=goal)
        jarvis.mark_goal_reached(goal, reached=False)
        assert "I have not reliably reached this yet" in jarvis.introspect()

    def test_a_recurring_goal_with_no_outcome_carries_no_annotation(self) -> None:
        from jarvis.domain.value_objects.goal import Goal

        jarvis = Jarvis()
        goal = Goal(statement="ship the parser")
        for question in ("q1", "q2", "q3"):
            jarvis.think(question, goal=goal)
        line = next(
            row for row in jarvis.introspect().splitlines() if "ship the parser" in row
        )
        assert line.strip() == "- ship the parser (3 times)"

    def test_an_unmet_goal_reports_how_often_it_was_reflected_on(self) -> None:
        from jarvis.domain.value_objects.goal import Goal

        jarvis = Jarvis()
        goal = Goal(statement="the hard goal")
        jarvis.think("is it correct?", evidence=[_ev(0.9, at=_EPOCH), _ev(0.9)], goal=goal)
        for _ in range(2):
            jarvis.think("is it correct?", goal=goal)
        jarvis.mark_goal_reached(goal, reached=False)
        for _ in range(2):
            impulse = jarvis.feel_curious()
            assert impulse is not None
            jarvis.pursue(impulse)
        assert "have turned it over 2 times" in jarvis.introspect()
