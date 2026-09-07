"""Increment 146: TemporalStability for hypotheses.

Hypotheses gain the *same* derived stability estimator beliefs use (how steadily
the supporting evidence is spread over time, Vision §10, §11) — but it stays its
own axis: it never re-ranks the set, never breaks a tie, never changes derived
confidence. Its honest job is that of the belief conclusion's narration: the
Challenge the reflective cycle issues carries the leading hypothesis's confidence
and stability and flags a narrow-time-window leader as possibly overfitting, with
the strength untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis import Jarvis
from jarvis.domain.aggregates.hypothesis_set import HypothesisSet
from jarvis.domain.entities.hypothesis import Hypothesis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.challenge import Challenge
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.temporal_stability import TemporalStability

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _ev(
    at: datetime,
    *,
    supports: bool = True,
    weight: float = 1.0,
) -> Evidence:
    return Evidence(
        content="observation",
        source=EvidenceSource.SYSTEM_OBSERVATION,
        weight=Confidence(weight),
        supports=supports,
        observed_at=at,
    )


def _hypothesis(*evidence: Evidence) -> Hypothesis:
    hypothesis = Hypothesis(statement="a candidate explanation")
    for piece in evidence:
        hypothesis.add_evidence(piece)
    return hypothesis


class TestHypothesisStability:
    def test_a_single_observation_is_not_stable(self) -> None:
        assert _hypothesis(_ev(_EPOCH)).stability == TemporalStability.none()

    def test_simultaneous_evidence_is_not_stable(self) -> None:
        assert _hypothesis(_ev(_EPOCH), _ev(_EPOCH)).stability == TemporalStability.none()

    def test_support_spread_over_time_is_more_stable(self) -> None:
        narrow = _hypothesis(_ev(_EPOCH), _ev(_EPOCH + timedelta(hours=1)))
        wide = _hypothesis(_ev(_EPOCH), _ev(_EPOCH + timedelta(days=90)))
        assert wide.stability.is_more_stable_than(narrow.stability)

    def test_stability_is_independent_of_confidence(self) -> None:
        burst = _hypothesis(_ev(_EPOCH), _ev(_EPOCH))
        sustained = _hypothesis(_ev(_EPOCH), _ev(_EPOCH + timedelta(days=60)))
        assert burst.confidence == sustained.confidence
        assert sustained.stability.is_more_stable_than(burst.stability)

    def test_contradicting_evidence_does_not_count_toward_stability(self) -> None:
        hypothesis = _hypothesis(
            _ev(_EPOCH), _ev(_EPOCH + timedelta(days=90), supports=False)
        )
        assert hypothesis.stability == TemporalStability.none()

    def test_a_recent_burst_reads_confident_but_utterly_unstable(self) -> None:
        # Three supports at one instant: high confidence, zero stability. Vision §10
        # keeps the axes separate -- the anti-overfit signal lives in the narrative.
        hypothesis = _hypothesis(_ev(_EPOCH), _ev(_EPOCH), _ev(_EPOCH))
        assert hypothesis.confidence.value > 0.5
        assert hypothesis.stability.value == 0.0


class TestRankingStaysOnConfidence:
    def test_stability_never_reorders_or_breaks_ties(self) -> None:
        # The bursty hypothesis is more confident; an equally-confident and much more
        # stable rival ties exactly. Stability is not a ranking key and ties survive.
        bursty = _hypothesis(_ev(_EPOCH), _ev(_EPOCH))
        steady = _hypothesis(_ev(_EPOCH), _ev(_EPOCH + timedelta(days=90)))
        assert bursty.confidence == steady.confidence  # a real tie
        assert steady.stability.is_more_stable_than(bursty.stability)

        hypotheses = HypothesisSet(observation="o")
        hypotheses.propose("bursty view")
        steady_id = hypotheses.propose("steady view").id
        bursty_id = hypotheses.propose("bursty view").id
        hypotheses.add_evidence(steady_id, _ev(_EPOCH))
        hypotheses.add_evidence(steady_id, _ev(_EPOCH + timedelta(days=90)))
        hypotheses.add_evidence(bursty_id, _ev(_EPOCH))
        hypotheses.add_evidence(bursty_id, _ev(_EPOCH))
        ranked = hypotheses.ranked()
        assert len(ranked) == 3
        # Tied top two -> strictly confidence-driven, no stability tie-break.
        assert hypotheses.leading() is None


class TestChallengeCarriesTheDerivedAxes:
    def _challenge(self, leading: Hypothesis) -> Challenge:
        return Challenge(
            hypothesis=leading.statement,
            observation="o",
            falsifier="if a belief would still hold without it",
            beliefs=("b",),
            confidence=leading.confidence,
            stability=leading.stability,
        )

    def test_a_bursty_leader_is_cautioned_about_narrowness(self) -> None:
        challenge = self._challenge(_hypothesis(_ev(_EPOCH), _ev(_EPOCH), _ev(_EPOCH)))
        assert "narrow time window" in challenge.describe()

    def test_a_steady_leader_is_not_cautioned(self) -> None:
        challenge = self._challenge(
            _hypothesis(_ev(_EPOCH), _ev(_EPOCH + timedelta(days=60)))
        )
        assert "narrow time window" not in challenge.describe()


class TestChallengeIntegration:
    def _with_hypothesis(self) -> Jarvis:
        jarvis = Jarvis()
        cause = "the client moved the deadline up"
        for question in ("is the schedule at risk?", "should we cut scope?", "is morale ok?"):
            jarvis.think(
                question,
                evidence=[
                    Evidence(
                        content=cause,
                        source=EvidenceSource.USER_STATEMENT,
                        weight=Confidence(0.9),
                    )
                ],
            )
        return jarvis

    def test_the_real_challenge_carries_the_derived_axes(self) -> None:
        challenge = self._with_hypothesis().challenge()
        assert challenge is not None
        assert isinstance(challenge.confidence, Confidence)
        assert isinstance(challenge.stability, TemporalStability)
        assert "common cause" in challenge.hypothesis