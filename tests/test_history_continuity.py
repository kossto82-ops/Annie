"""Historical cognition: beliefs, decisions and change across restarts (P1).

Proves Jarvis distinguishes what it believed *then* from what it believes
*now*, reconstructing historical state from persisted provenance (never from
current state plus timestamps), and can account for a past decision after a
restart -- including whether it would decide the same today.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.jarvis import Jarvis


def _support(content: str, weight: float = 1.0) -> Evidence:
    return Evidence(
        content=content,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(weight),
    )


def _oppose(content: str, weight: float = 1.0) -> Evidence:
    return Evidence(
        content=content,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(weight),
        supports=False,
    )


class TestTemporalContinuity:
    def test_then_vs_now_survives_restart(self, tmp_path: Path) -> None:
        question = "is the northern trail open?"
        first_run = Jarvis.persistent(tmp_path)
        first_run.think(question, evidence=[_support("trail crew says open")])
        first_run.think(question, evidence=[_support("ranger confirms open")])
        middle = datetime.now(UTC)
        first_run.think(question, evidence=[_oppose("landslide reported")])
        first_run.think(question, evidence=[_oppose("rangers closed the gate")])

        then = first_run.belief_snapshot_at(question, middle)
        assert then is not None
        assert then.confidence.value >= 0.5
        now = first_run.belief_snapshot_at(question, datetime.now(UTC))
        assert now is not None
        assert now.confidence.value < then.confidence.value
        changes = first_run.what_changed(
            question, datetime(2020, 1, 1, tzinfo=UTC), datetime.now(UTC)
        )
        assert changes, "the contradiction must register as a change"
        assert any(change.confidence_delta < 0.0 for change in changes)

        # Restart: history reconstructs identically from storage.
        second_run = Jarvis.persistent(tmp_path)
        revived_then = second_run.belief_snapshot_at(question, middle)
        assert revived_then is not None
        assert revived_then.confidence.value == then.confidence.value
        revived_now = second_run.belief_snapshot_at(question, datetime.now(UTC))
        assert revived_now is not None
        assert revived_now.confidence.value == now.confidence.value
        assert second_run.belief_timeline(question)[-1].confidence.value < 0.5

    def test_unknown_subject_has_no_history(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        assert jarvis.belief_timeline("nothing ever asked") == ()
        assert jarvis.belief_snapshot_at("nothing ever asked", datetime.now(UTC)) is None


class TestDecisionContinuity:
    def test_why_decision_is_grounded_after_restart(self, tmp_path: Path) -> None:
        question = "should we launch on friday?"
        first_run = Jarvis.persistent(tmp_path)
        first_run.think(question, evidence=[_support("forecast is clear")])
        first_run.think(question, evidence=[_support("crew is ready")])

        account = first_run.why_decision(question)
        assert account is not None
        assert account.decision
        assert account.confidence_then >= 0.5
        assert any("forecast" in snap.content for snap in account.evidence_then)
        assert account.reflection_note is not None
        assert account.confidence_now is not None
        assert account.same_today is True

        # Restart: the account rebuilds from storage, then new evidence
        # changes the live view without rewriting the past.
        second_run = Jarvis.persistent(tmp_path)
        revived = second_run.why_decision(question)
        assert revived is not None
        assert revived.decision == account.decision
        assert revived.confidence_then == account.confidence_then
        assert revived.same_today is True

        second_run.think(question, evidence=[_oppose("storm warning issued")])
        second_run.think(question, evidence=[_oppose("crew called in sick")])
        revised = second_run.why_decision(question)
        assert revised is not None
        # The past is untouched...
        assert revised.confidence_then == account.confidence_then
        assert any("forecast" in snap.content for snap in revised.evidence_then)
        # ...but today Jarvis would decide differently.
        assert revised.confidence_now is not None
        assert revised.confidence_now < revised.confidence_then
        assert revised.same_today is False

    def test_why_decision_unknown_is_honest_none(self, tmp_path: Path) -> None:
        assert Jarvis.persistent(tmp_path).why_decision("never asked") is None
