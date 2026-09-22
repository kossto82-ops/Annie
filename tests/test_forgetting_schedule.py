"""Roadmap F2: scheduled honest forgetting.

Forgetting is *suggested* and applied explicitly, never automatic:

1. faded beliefs (stale / low effective confidence / evidence-less) become
   candidates under the injected weighting policy, judged on a fixed clock;
2. grounded companion traits are protected by the grounded gate;
3. recently-renewed beliefs are excluded by the anti-nagging gate;
4. identifying never deletes anything; only an explicit apply touches the store,
   and it is re-gated at apply time;
5. an apply survives a persistent restart;
6. a wired decaying policy also biases recall ranking (old, equally-relevant
   topics rank below fresh ones) -- the same recency, on the read side.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.evidence_weighting import DecayingWeightingPolicy
from jarvis.domain.services.forgetting import ForgettingCandidates
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore
from jarvis.interface.command_center import handle
from jarvis.jarvis import Jarvis

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _decaying() -> DecayingWeightingPolicy:
    return DecayingWeightingPolicy(now=lambda: _NOW, half_life=timedelta(days=30))


def _candidate_statements(health: dict[str, object]) -> list[str]:
    """The statements in a health report, JSON-shaped, pyright-clean."""
    raw = health.get("candidates", [])
    if not isinstance(raw, list):
        return []
    items = cast("list[object]", raw)
    statements: list[str] = []
    for item in items:
        entry = cast("dict[str, object]", item)
        statements.append(str(entry.get("statement", "")))
    return statements


def _belief(
    statement: str,
    weight: float = 0.5,
    age_days: int = 0,
) -> Belief:
    """A belief both formed and last renewed ``age_days`` before the fixed clock."""
    formed = _NOW - timedelta(days=age_days)
    belief = Belief(statement=statement, formed_at=formed)
    belief.add_evidence(
        Evidence(
            content=f"evidence for {statement}",
            source=EvidenceSource.DIRECT_OBSERVATION,
            weight=Confidence(weight),
            supports=True,
            context="test",
            observed_at=formed,
        )
    )
    return belief


def _stale_belief(statement: str, weight: float = 0.8) -> Belief:
    return _belief(statement, weight=weight, age_days=100)


def _trait_evidence() -> Evidence:
    """Who the companion says they are: strong, stated, but long un-refreshed."""
    return Evidence(
        content="she said so",
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(0.9),
        observed_at=_NOW - timedelta(days=100),
    )


class TestForgettingCandidates:
    def test_stale_belief_is_a_candidate_and_fresh_one_is_not(self) -> None:
        store = InMemoryBeliefStore()
        store.save(_stale_belief("old topic"))
        store.save(_belief("fresh topic", weight=0.9, age_days=5))
        service = ForgettingCandidates(store, companion=Jarvis().companion, now=lambda: _NOW)

        profile = service.identify()

        assert [c.belief.statement for c in profile.candidates] == ["old topic"]
        assert "not reinforced" in profile.candidates[0].reason
        assert profile.grounded_protected == ()
        assert profile.reaffirmed_excluded == ()

    def test_low_effective_confidence_becomes_a_candidate(self) -> None:
        # A lone faint inference, last renewed long enough ago that the
        # anti-nagging gate does not hold it back.
        store = InMemoryBeliefStore()
        store.save(_belief("faint topic", weight=0.1, age_days=40))
        service = ForgettingCandidates(store, companion=Jarvis().companion, now=lambda: _NOW)

        profile = service.identify()

        assert [c.belief.statement for c in profile.candidates] == ["faint topic"]
        assert "below threshold" in profile.candidates[0].reason

    def test_grounded_companion_trait_is_protected(self) -> None:
        store = InMemoryBeliefStore()
        trait = Belief(statement="she prefers tea", formed_at=_NOW - timedelta(days=100))
        trait.add_evidence(_trait_evidence())
        store.save(trait)
        companion = Jarvis().companion
        # The same faded trait is also who the companion says they are: stale but
        # still grounded, so the gate shields it from being suggested at all.
        companion.observe("she prefers tea", _trait_evidence())
        service = ForgettingCandidates(
            store, companion=companion, now=lambda: _NOW,
            grounded_confidence=lambda: 0.4,
        )

        profile = service.identify()

        assert profile.candidates == ()
        assert profile.grounded_protected == ("she prefers tea",)

    def test_just_renewed_belief_is_excluded(self) -> None:
        # Confidence below threshold (would fade), but its memory was renewed a
        # week ago: suggesting it now would be nagging.
        store = InMemoryBeliefStore()
        store.save(_belief("faint topic", weight=0.1, age_days=7))
        service = ForgettingCandidates(store, companion=Jarvis().companion, now=lambda: _NOW)

        profile = service.identify()

        assert profile.candidates == ()
        assert profile.reaffirmed_excluded == ("faint topic",)

    def test_identify_is_read_only(self) -> None:
        store = InMemoryBeliefStore()
        store.save(_stale_belief("old topic"))
        store.save(_stale_belief("another old topic"))
        service = ForgettingCandidates(store, companion=Jarvis().companion, now=lambda: _NOW)

        service.identify()

        assert len(store.all_beliefs()) == 2, "a dry-run must never delete"

    def test_decaying_policy_drives_candidate_selection(self) -> None:
        # A belief sustained only by evidence 2 half-lives old: with decay wired it
        # fades below threshold and becomes a candidate; without it the same belief
        # still holds (it is not stale by the 90-day bar, and confidence is high).
        store = InMemoryBeliefStore()
        store.save(_belief("old but trusted", weight=0.9, age_days=60))
        decaying = ForgettingCandidates(
            store, companion=Jarvis().companion, now=lambda: _NOW,
            weighting_policy=_decaying(),
        )
        plain = ForgettingCandidates(
            store, companion=Jarvis().companion, now=lambda: _NOW
        )

        assert [c.belief.statement for c in decaying.identify().candidates] == [
            "old but trusted"
        ]
        assert plain.identify().candidates == ()


class TestExplicitApply:
    def test_apply_forgets_exactly_the_named_statements(self) -> None:
        store = InMemoryBeliefStore()
        store.save(_stale_belief("old topic"))
        store.save(_stale_belief("keep this one"))
        service = ForgettingCandidates(store, companion=Jarvis().companion, now=lambda: _NOW)

        result = service.apply(["old topic"])

        assert result.forgotten == ("old topic",)
        assert result.refused == ()
        assert result.missing == ()
        assert [b.statement for b in store.all_beliefs()] == ["keep this one"]

    def test_apply_refuses_protected_and_reports_missing(self) -> None:
        companion = Jarvis().companion
        store = InMemoryBeliefStore()
        trait = Belief(statement="she prefers tea", formed_at=_NOW - timedelta(days=100))
        trait.add_evidence(_trait_evidence())
        store.save(trait)
        companion.observe("she prefers tea", _trait_evidence())
        store.save(_stale_belief("old topic"))
        service = ForgettingCandidates(
            store, companion=companion, now=lambda: _NOW,
            grounded_confidence=lambda: 0.4,
        )

        result = service.apply(["she prefers tea", "old topic", "never existed"])

        assert result.forgotten == ("old topic",)
        assert result.refused == ("she prefers tea",)
        assert result.missing == ("never existed",)
        # The protected trait really is still there afterwards.
        assert [b.statement for b in store.all_beliefs()] == ["she prefers tea"]

    def test_apply_with_no_statements_deletes_nothing(self) -> None:
        store = InMemoryBeliefStore()
        store.save(_stale_belief("old topic"))
        service = ForgettingCandidates(store, companion=Jarvis().companion, now=lambda: _NOW)

        result = service.apply([])

        assert result.forgotten == () and result.refused == () and result.missing == ()
        assert len(store.all_beliefs()) == 1

    def test_apply_persists_across_a_restart(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        store = jarvis.beliefs
        store.save(_stale_belief("old topic"))
        jarvis.forget(["old topic"])

        revived = Jarvis.persistent(tmp_path)  # same directory, new process state

        assert [b.statement for b in revived.beliefs.all_beliefs()] == []


class TestJarvisFacadeAndSchedule:
    def test_rest_refreshes_memory_health_without_deleting(self) -> None:
        jarvis = Jarvis()
        jarvis.beliefs.save(_stale_belief("old topic"))
        health_before = jarvis.memory_health()

        jarvis.rest()

        health_after = jarvis.memory_health()
        assert isinstance(health_before, dict) and isinstance(health_after, dict)
        assert len(jarvis.beliefs.all_beliefs()) == 1, "rest must never delete"
        assert _candidate_statements(health_after) == ["old topic"]

    def test_memory_health_reports_honest_shapes(self) -> None:
        jarvis = Jarvis()
        health = jarvis.memory_health()
        assert health["decay_wired"] is False
        assert health["candidates"] == []
        assert health["protected"] == []
        assert health["reaffirmed"] == []
        assert "swept_at" in health

        with_decay = Jarvis(weighting_policy=_decaying())
        assert with_decay.memory_health()["decay_wired"] is True

    def test_forgetting_profile_is_a_read_only_dry_run(self) -> None:
        jarvis = Jarvis()
        jarvis.beliefs.save(_stale_belief("old topic"))
        profile = jarvis.forgetting_profile()
        assert [c.belief.statement for c in profile.candidates] == ["old topic"]
        assert len(jarvis.beliefs.all_beliefs()) == 1


class TestRecallDecayBias:
    def test_old_equally_relevant_topic_ranks_below_fresh_one(self) -> None:
        # Two beliefs with identical relevance to a query; only age differs.
        # With decay wired the stale one must rank below, the read side agreeing
        # with the belief engine's honest forgetting.
        store = InMemoryBeliefStore()
        store.save(_belief("the plan is solid", weight=0.9, age_days=0))
        store.save(_belief("revisit the plan again", weight=0.9, age_days=60))
        jarvis = Jarvis(
            beliefs=store,
            enable_recall=True,
            weighting_policy=_decaying(),
        )

        recalled = jarvis.recall("the plan")

        ranked = [m.content for m in recalled]
        assert ranked[0] == "the plan is solid"
        assert ranked[1] == "revisit the plan again"
        assert recalled[0].relevance == 1.0
        assert recalled[1].relevance < recalled[0].relevance

    def test_without_decay_the_tie_breaks_as_always(self) -> None:
        store = InMemoryBeliefStore()
        store.save(_belief("the plan is solid", weight=0.9, age_days=0))
        store.save(_belief("revisit the plan again", weight=0.9, age_days=90))
        jarvis = Jarvis(beliefs=store, enable_recall=True)  # no decay -> unchanged

        recalled = jarvis.recall("the plan")

        # No recency at all: the equal-relevance pair stays equal, and the stale
        # memory is NOT silently discounted.
        relevances = [m.relevance for m in recalled]
        assert len(recalled) >= 2
        assert relevances[0] == relevances[1] == 1.0


class TestForgettingCommand:
    def test_command_dry_run_lists_candidates(self) -> None:
        jarvis = Jarvis()
        jarvis.beliefs.save(_stale_belief("old topic"))
        reply = handle(jarvis, "forgetting", {"action": "dry-run"})

        assert "old topic" in str(reply["reply"])
        forgetting = cast(dict[str, object], reply.get("forgetting", {}))
        assert _candidate_statements(forgetting) == ["old topic"]
        assert "state" in reply

    def test_command_apply_removes_named_beliefs_and_reports_refusal(self) -> None:
        jarvis = Jarvis()
        jarvis.beliefs.save(_stale_belief("old topic"))
        jarvis.beliefs.save(_stale_belief("keep"))
        reply = handle(
            jarvis,
            "forgetting",
            {"action": "apply", "statements": ["old topic", "never"]},
        )

        assert "old topic" in str(reply["reply"])
        assert "never" in str(reply["reply"])
        assert [b.statement for b in jarvis.beliefs.all_beliefs()] == ["keep"]

    def test_command_apply_all_requires_candidates(self) -> None:
        jarvis = Jarvis()
        empty = handle(jarvis, "forgetting", {"action": "apply", "all": True})
        assert "all" in str(empty["reply"])
        assert jarvis.beliefs.all_beliefs() == ()

        jarvis.beliefs.save(_stale_belief("old topic"))
        done = handle(jarvis, "forgetting", {"action": "apply", "all": True})
        assert "old topic" in str(done["reply"])
        assert jarvis.beliefs.all_beliefs() == ()

    def test_command_unknown_action_is_an_error(self) -> None:
        reply = handle(Jarvis(), "forgetting", {"action": "nuke"})
        assert "error" in reply

    def test_command_health_reads_without_writing(self) -> None:
        jarvis = Jarvis()
        jarvis.beliefs.save(_stale_belief("old topic"))
        reply = handle(jarvis, "forgetting", {"action": "health"})
        assert "decision" in str(reply["reply"]).lower()
        assert len(jarvis.beliefs.all_beliefs()) == 1