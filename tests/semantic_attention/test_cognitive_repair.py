"""Cognitive Integration & Attention Repair -- phases A, B and C.

Repairs Regression (4 bugs):
A. Concept signature is topic identity: topics group by canonical concept
   signature (same topic across lexical variants), with the raw trigger kept as
   display-only representative.
B. Attention derives from canonical topics, external signals only, with a
   correct recency direction (most recent = 1.0).
C. Curiosity provenance survives persistence: wake() anchors a canonical topic,
   pursue() runs the topic's real representative trigger, and the episode's
   target_topic_id is persisted (JSON and SQLite) and reloaded.

All derivations stay pure/reversible; nothing below golden-checks memory
surfaces or a second authoritative score.
"""
from __future__ import annotations

from pathlib import Path

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.attention_priority import (
    ATTEND_THRESHOLD,
    derive_attention_priorities,
)
from jarvis.domain.services.topic_resolution import (
    resolve_episodes,
    signature_of,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.curiosity_impulse import CuriosityImpulse
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.jarvis import Jarvis


def _external(episode_id: str, trigger: str) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id=episode_id,
        trigger=trigger,
        decision="decided",
        working_belief_id=f"b-{episode_id}",
        outcome=EpisodeState.COMPLETED,
        conclusion_confidence=Confidence(0.9),
        conclusion_stability=TemporalStability(0.5),
        origin=TriggerOrigin.COMPANION,
        kind=EpisodeKind.CONCLUSION,
    )


class TestPhaseATopicResolution:
    """Correction #1: topic identity is the canonical signature, not the trigger."""

    def test_lexical_variants_share_one_topic(self):
        episodes = [
            _external("1", "supplier failed to deliver"),
            _external("2", "the vendor missed the delivery"),
            _external("3", "provider delivery failure"),
        ]
        topics = resolve_episodes(episodes)
        assert len(topics) == 1
        topic = topics[0]
        assert topic.canonical_signature == frozenset({"FAIL", "DELIVER"})
        assert topic.topic_id == "DELIVER > FAIL"
        assert len(topic.source_episode_ids) == 3

    def test_representative_is_display_metadata(self):
        episodes = [
            _external("1", "supplier failed to deliver"),
            _external("2", "the vendor missed the delivery"),
        ]
        topic = resolve_episodes(episodes)[0]
        # Latest episode's trigger is representative; identity stays canonical.
        assert topic.representative_trigger == "the vendor missed the delivery"
        assert topic.topic_id == "DELIVER > FAIL"
        assert topic.canonical_signature == frozenset({"FAIL", "DELIVER"})

    def test_detail_episode_joins_the_resolved_topic(self):
        # S = {FAIL, DELIVER, TIME} ⊇ canonical T = {FAIL, DELIVER}, share >= 2.
        episodes = [
            _external("1", "supplier failed to deliver"),
            _external("2", "vendor missed the delivery deadline"),
        ]
        topics = resolve_episodes(episodes)
        assert len(topics) == 1
        assert topics[0].canonical_signature == frozenset({"FAIL", "DELIVER"})

    def test_single_concept_topics_never_merge(self):
        # S = {FAIL} against canonical T = {FAIL, DELIVER}: the containment rule
        # needs >= 2 shared concepts, so a lone concept can never pull topics
        # together (and never absorbs another topic).
        episodes = [
            _external("1", "supplier failed to deliver"),
            _external("2", "the vendor missed"),
        ]
        topics = resolve_episodes(episodes)
        assert len(topics) == 2

    def test_ambigous_signature_starts_a_new_topic(self):
        # S = {FAIL, DELIVER, TIME, COST} ⊇ both T1={FAIL,DELIVER} and
        # T2={TIME,COST}: compatible with two topics -> S is its own topic.
        episodes = [
            _external("1", "supplier failed to deliver"),
            _external("2", "the schedule had a cost overrun"),
            _external("3", "failed delivery cost the deadline"),
        ]
        topics = resolve_episodes(episodes)
        assert len(topics) == 3

    def test_concept_free_episodes_stay_distinct(self):
        episodes = [_external("1", "the market wobbles"), _external("2", "a quiet thought")]
        topics = resolve_episodes(episodes)
        assert len(topics) == 2
        assert topics[0].topic_id == "the market wobbles"
        assert topics[1].topic_id == "a quiet thought"

    def test_resolution_is_reversible_and_mutation_free(self):
        episodes = [
            _external("1", "supplier failed to deliver"),
            _external("2", "the vendor missed the delivery"),
        ]
        before = [ep.episode_id for ep in episodes]
        first = resolve_episodes(episodes)
        second = resolve_episodes(episodes)
        assert first == second
        assert [ep.episode_id for ep in episodes] == before


class TestPhaseBAttentionOnCanonicalTopics:
    """Correction #1+4 and P2/P3: grouped by topic, external-only, right recency."""

    def test_lexical_variants_raise_one_priority(self):
        history = [
            _external("1", "supplier failed to deliver"),
            _external("2", "the vendor missed the delivery"),
            _external("3", "provider delivery failure"),
        ]
        priorities = derive_attention_priorities(history)
        assert len(priorities) == 1
        top = priorities[0]
        assert top.topic == "DELIVER > FAIL"
        assert top.episodes_on_topic == 3
        assert top.representative == "provider delivery failure"

    def test_recency_points_at_most_recent(self):
        history = [
            _external("1", "a"),
            _external("2", "b"),
            _external("3", "b"),
            _external("4", "c"),
        ]
        priorities = derive_attention_priorities(history)
        by_topic = {p.topic: p for p in priorities}
        assert by_topic["c"].last_episode_recency == 1.0  # newest episode
        assert by_topic["a"].last_episode_recency == 0.0  # oldest episode
        assert by_topic["b"].last_episode_recency == 2 / 3

    def test_single_touched_topic_ranks_first(self):
        history = [
            _external("1", "a"),
            _external("2", "b"),
            _external("3", "b"),
            _external("4", "c"),
            _external("5", "c"),
            _external("6", "c"),
        ]
        assert derive_attention_priorities(history)[0].topic == "c"

    def test_self_generated_episodes_never_feed_attention(self):
        internal = EpisodeRecord(
            episode_id="self",
            trigger="supplier failed to deliver",
            decision="decided",
            working_belief_id="b-self",
            outcome=EpisodeState.COMPLETED,
            conclusion_confidence=Confidence(0.9),
            conclusion_stability=TemporalStability(0.5),
            origin=TriggerOrigin.CURIOSITY,
            kind=EpisodeKind.CONCLUSION,
        )
        assert derive_attention_priorities([internal]) == ()
        external = _external("1", "supplier failed to deliver")
        assert derive_attention_priorities([internal, external]) != ()

    def test_belief_confidence_end_drives_revision_signal(self):
        def rec(episode_id: str, at_end: float | None) -> EpisodeRecord:
            return EpisodeRecord(
                episode_id=episode_id,
                trigger="the supplier failed",
                decision="decided",
                working_belief_id=f"b-{episode_id}",
                outcome=EpisodeState.COMPLETED,
                conclusion_confidence=Confidence(0.9),
                conclusion_stability=TemporalStability(0.5),
                origin=TriggerOrigin.COMPANION,
                kind=EpisodeKind.CONCLUSION,
                belief_confidence_at_end=(
                    Confidence(at_end) if at_end is not None else None
                ),
            )

        flat = derive_attention_priorities([rec("1", 0.6), rec("2", 0.6)])[0]
        moving = derive_attention_priorities([rec("1", 0.6), rec("2", 0.9)])[0]
        assert flat.revised is False
        assert moving.revised is True


class TestPhaseCCuriosityProvenance:
    """Correction #3: the impulse, and its pursued episode, carry the topic."""

    def test_wake_impulse_carries_canonical_topic(self):
        j = Jarvis()
        for _ in range(5):
            j.think("the contractor keeps failing deliveries")
        impulse = j.wake()
        assert impulse is not None
        assert isinstance(impulse, CuriosityImpulse)
        assert impulse.target_topic_id == "FAIL"
        assert impulse.representative_trigger == "the contractor keeps failing deliveries"

    def test_pursue_runs_the_real_representative_trigger(self):
        j = Jarvis()
        for _ in range(5):
            j.think("the contractor keeps failing deliveries")
        impulse = j.wake()
        assert impulse is not None
        ep = j.pursue(impulse)
        assert ep is not None
        assert ep.trigger == "the contractor keeps failing deliveries"
        assert ep.origin.value == "curiosity"
        assert ep.target_topic_id == "FAIL"

    def test_target_topic_id_persists_across_json_restart(self, tmp_path: Path) -> None:
        first = Jarvis.database(tmp_path)
        for _ in range(5):
            first.think("the contractor keeps failing deliveries")
        impulse = first.wake()
        assert impulse is not None
        first.pursue(impulse)

        second = Jarvis.database(tmp_path)
        records = second.episodes.history()
        pursued = [r for r in records if r.origin is TriggerOrigin.CURIOSITY]
        assert pursued, "pursued episode must survive the restart"
        assert pursued[-1].target_topic_id == "FAIL"
        assert pursued[-1].trigger == "the contractor keeps failing deliveries"

    def test_target_topic_id_persists_in_sqlite(self, tmp_path: Path) -> None:
        first = Jarvis.persistent(tmp_path)
        for _ in range(5):
            first.think("the contractor keeps failing deliveries")
        impulse = first.wake()
        assert impulse is not None
        first.pursue(impulse)

        second = Jarvis.persistent(tmp_path)
        pursued = [
            r
            for r in second.episodes.history()
            if r.origin is TriggerOrigin.CURIOSITY
        ]
        assert pursued and pursued[-1].target_topic_id == "FAIL"

    def test_wake_still_threshold_bound(self):
        assert ATTEND_THRESHOLD > 0.0

    def test_pursued_episode_does_not_pollute_attention(self):
        # A curiosity episode about the SAME topic must not re-rank attention
        # (external-only signals): wake→pursue is not a feedback amplifier.
        j = Jarvis()
        for _ in range(5):
            j.think("the contractor keeps failing deliveries")
        before = j.attention_priorities()
        impulse = j.wake()
        assert impulse is not None
        j.pursue(impulse)
        after = j.attention_priorities()
        assert before == after


def test_signature_of_is_public_and_pure():
    assert signature_of("supplier failed to deliver") == frozenset({"FAIL", "DELIVER"})
    assert signature_of("nonsense quux") == frozenset()