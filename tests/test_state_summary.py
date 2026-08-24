"""Tests for the compact state snapshot (Vision §21)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

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


class TestStateSummary:
    def test_a_fresh_jarvis_summary_is_empty(self) -> None:
        summary = Jarvis().state_summary()
        assert summary.episode_count == 0
        assert summary.self_tendencies == ()
        assert summary.companion_traits == ()
        assert summary.learned_actions == ()

    def test_the_summary_is_immutable(self) -> None:
        summary = Jarvis().state_summary()
        with pytest.raises(dataclasses.FrozenInstanceError):
            summary.episode_count = 1  # type: ignore[misc]


class TestSummaryReflectsState:
    def test_it_counts_episodes_and_lists_the_companion(self) -> None:
        jarvis = Jarvis()
        jarvis.think("q1")
        jarvis.think("q2")
        jarvis.observe_companion("prefers simplicity", _ev(0.9))

        summary = jarvis.state_summary()
        assert summary.episode_count == 2
        traits = [trait for trait, _ in summary.companion_traits]
        assert "prefers simplicity" in traits

    def test_it_lists_confident_self_tendencies_and_action_learning(self) -> None:
        from jarvis.domain.enums.action_stance import ActionStance

        jarvis = Jarvis()
        for topic in ("a", "b", "c"):
            # grounded but same-instant -> overconfidence tendency
            jarvis.think(f"q {topic}", evidence=[_ev(0.9, at=_EPOCH), _ev(0.9, at=_EPOCH)])
        for _ in range(3):
            action = jarvis.act("tidy the notes", expected="tidy", reversible=True)
            jarvis.record_outcome(action, actual="tidy", met_expectation=True)

        summary = jarvis.state_summary()
        tendencies = [statement for statement, _ in summary.self_tendencies]
        assert any("overconfident" in statement for statement in tendencies)
        assert len(summary.learned_actions) == 1
        learned = summary.learned_actions[0]
        assert learned.description == "tidy the notes"
        assert learned.stance is ActionStance.SUGGEST
