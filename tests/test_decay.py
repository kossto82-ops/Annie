"""End-to-end: a decaying weighting policy makes a belief on stale evidence weaker.

Forgetting (Vision §10, §22): the same old evidence grounds a belief less strongly
when Jarvis is wired with a DecayingWeightingPolicy, and that stays true across a
restart (the JSON store rehydrates beliefs with the policy).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.evidence_weighting import DecayingWeightingPolicy
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.jarvis import Jarvis

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _decaying() -> DecayingWeightingPolicy:
    return DecayingWeightingPolicy(now=lambda: _NOW, half_life=timedelta(days=30))


def _old_evidence() -> Evidence:
    # ~3 half-lives old -> heavily decayed.
    return Evidence(
        content="the plan is solid",
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(1.0),
        observed_at=_NOW - timedelta(days=90),
    )


def _confidence_of(jarvis: Jarvis, trigger: str, evidence: Evidence) -> float:
    episode = jarvis.think(trigger, evidence=[evidence])
    assert episode.working_belief is not None
    return episode.working_belief.confidence.value


class TestDecayThroughJarvis:
    def test_stale_evidence_grounds_a_belief_less_strongly_under_decay(self) -> None:
        trigger = "is the plan solid?"
        with_decay = _confidence_of(Jarvis(weighting_policy=_decaying()), trigger, _old_evidence())
        without_decay = _confidence_of(Jarvis(), trigger, _old_evidence())
        assert with_decay < without_decay

    def test_decay_survives_a_persistent_restart(self, tmp_path: Path) -> None:
        trigger = "is the plan solid?"
        jarvis = Jarvis.persistent(tmp_path, weighting_policy=_decaying())
        first = _confidence_of(jarvis, trigger, _old_evidence())

        # Reload from disk with the same decaying policy: the rehydrated belief must
        # still weigh its stale evidence down, not snap back to the no-decay default.
        revived = Jarvis.persistent(tmp_path, weighting_policy=_decaying())
        reloaded = revived.beliefs.all_beliefs()
        assert len(reloaded) == 1
        assert reloaded[0].confidence.value == first

    def test_a_reload_without_decay_does_not_forget(self, tmp_path: Path) -> None:
        trigger = "is the plan solid?"
        jarvis = Jarvis.persistent(tmp_path, weighting_policy=_decaying())
        decayed = _confidence_of(jarvis, trigger, _old_evidence())

        plain = Jarvis.persistent(tmp_path)  # default policy, no clock, no decay
        assert plain.beliefs.all_beliefs()[0].confidence.value > decayed
