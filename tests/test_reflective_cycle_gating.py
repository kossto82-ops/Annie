"""Reflection gating: stages run only when something is worth pursuing (P1).

Proves the cycle no longer executes every stage merely because it was
called: uninteresting input terminates after reflect; meaningful
uncertainty continues through hypothesise/challenge/learn; new evidence
changes the path taken; and unnecessary stages observably do not execute
(the cycle reports the path it actually ran).
"""

from __future__ import annotations

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.jarvis import Jarvis


def _ev(content: str, weight: float = 0.9) -> Evidence:
    return Evidence(
        content=content,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(weight),
    )


class TestReflectiveCycleGating:
    def test_uninteresting_input_terminates_early(self) -> None:
        jarvis = Jarvis()
        cycle = jarvis.reflect_cycle()
        assert cycle.path == ("connect", "reflect", "act", "scout")
        assert cycle.reflection is None
        assert cycle.hypothesis is None
        assert cycle.challenge is None
        assert cycle.learned is None
        assert cycle.action is None
        # Nothing was worth pursuing, so nothing was written either.
        assert jarvis.beliefs.all_beliefs() == ()
        assert jarvis.capability_needs() == ()

    def test_meaningful_uncertainty_continues(self) -> None:
        jarvis = Jarvis()
        shared = "the lighthouse keeper waves"
        jarvis.think("why did the light move?", evidence=[_ev(shared)])
        jarvis.think("who tends the light?", evidence=[_ev(shared)])
        cycle = jarvis.reflect_cycle()
        assert cycle.reflection is not None
        assert "hypothesise" in cycle.path
        assert "challenge" in cycle.path
        assert "learn" in cycle.path
        assert cycle.hypothesis is not None

    def test_new_evidence_changes_the_path(self) -> None:
        jarvis = Jarvis()
        idle = jarvis.reflect_cycle()
        assert "hypothesise" not in idle.path

        shared = "the lighthouse keeper waves"
        jarvis.think("why did the light move?", evidence=[_ev(shared)])
        jarvis.think("who tends the light?", evidence=[_ev(shared)])
        engaged = jarvis.reflect_cycle()
        assert "hypothesise" in engaged.path

    def test_unnecessary_stages_do_not_execute(self) -> None:
        # One grounded episode: history exists, but there is no shared
        # observation, no connection and no recurring failure -- nothing
        # worth pursuing, so the cognition chain stays skipped while the
        # self-guarded maintenance still runs.
        jarvis = Jarvis()
        jarvis.think("is the plan solid?", evidence=[_ev("one solid reason")])
        cycle = jarvis.reflect_cycle()
        assert "hypothesise" not in cycle.path
        assert "challenge" not in cycle.path
        assert "learn" not in cycle.path
        assert cycle.learned is None
        assert "act" in cycle.path
        assert "scout" in cycle.path
