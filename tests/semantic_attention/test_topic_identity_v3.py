"""Topic Identity v3 -- the architecture gate's acceptance invariants.

The gate decided: topic identity is HISTORICAL (resolved over the complete
external episode history), attention is TEMPORAL (signals bounded to the recent
external attention window), and identity is ABOUTNESS-ONLY (polarity lives in
evidence, never in the identity signature).  These tests pin the invariants the
implementation must satisfy; they are the acceptance tests of the Topic
Identity v3 change as re-expressed for the aboutness-only world.

Invariants pinned here:
A. Order reverse      -- A→B and B→A both produce one topic; the founder's
                         canonical anchors identity, so the *ids* may differ.
B. Narrowing          -- a generic repeat of a detailed mention joins, never
                         splits ({DELIVER,TIME,COST}→{DELIVER,TIME} is one topic).
C. Broadening         -- the founder's canonical signature survives later growth
                         ({DELIVER,TIME}→{DELIVER,TIME,COST}→{...,RISK}).
D. Eviction           -- identity stable as episodes leave the attention window;
                         only the signals shrink.  Resolution over the full
                         history never changes identity either.
E. Ambiguity          -- conservative: S after X,Y is its own topic (3 topics);
                         S first absorbs its narrower parts (1 topic).
F. No-pollution       -- single-concept overlap ({DELIVER,*} vs {DELIVER})
                         never merges topics: the {DELIVER}/{DELIVER,TIME}
                         split is intended, never bridged by a shared token.
G. Self-reinforcement -- 5× wake→pursue is a fixed point of attention.
H. Persistence        -- JSON and SQLite replay resolve identically.
I. Recency            -- attention is window-local: historical_count=20 with
                         window_count=0 yields no current priority.
"""
from __future__ import annotations

from pathlib import Path

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.attention_priority import derive_attention_priorities
from jarvis.domain.services.topic_resolution import resolve_episodes
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.jarvis import Jarvis

# Concept-signature vocabulary used below (verified against signature_of).
# Identity is aboutness-only: FAIL/SUCCEED are projected out, so these
# signatures carry no polarity token.
A = "supplier delivered"  # {DELIVER}
B = "supplier delivered on time"  # {DELIVER, TIME}
S = "the delayed delivery cost us"  # {DELIVER, TIME, COST}
Y = "the schedule had a cost overrun"  # {TIME, COST}
R = "the risky delayed delivery cost us"  # {DELIVER, TIME, COST, RISK}


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


def _family() -> list[EpisodeRecord]:
    return [_external("1", B), _external("2", S), _external("3", B)]


class TestAOrderReverse:
    def test_both_directions_form_one_topic(self):
        b = _external("1", B)
        s = _external("2", S)
        assert len(resolve_episodes([b, s])) == 1
        assert len(resolve_episodes([s, b])) == 1

    def test_founder_anchors_the_canonical(self):
        b = _external("1", B)
        s = _external("2", S)
        fwd = resolve_episodes([b, s])[0]
        rev = resolve_episodes([s, b])[0]
        # Identical content, different founder -> ids differ (never permutation-
        # invariant); both are single topics with the founder's canonical.
        assert fwd.topic_id == "DELIVER > TIME"
        assert fwd.canonical_signature == frozenset({"DELIVER", "TIME"})
        assert rev.topic_id == "COST > DELIVER > TIME"
        assert rev.canonical_signature == frozenset({"DELIVER", "TIME", "COST"})
        assert len(fwd.source_episode_ids) == len(rev.source_episode_ids) == 2


class TestBNarrowing:
    def test_generic_repeat_joins_the_detailed_topic(self):
        # {DELIVER, TIME, COST} then {DELIVER, TIME}: still one topic.
        topic = resolve_episodes([_external("1", S), _external("2", B)])[0]
        assert topic.canonical_signature == frozenset({"DELIVER", "TIME", "COST"})
        assert topic.topic_id == "COST > DELIVER > TIME"
        assert len(topic.source_episode_ids) == 2


class TestCBroadening:
    def test_founder_anchor_survives_growth(self):
        # {DELIVER, TIME} -> {DELIVER, TIME, COST} -> {DELIVER, TIME, COST, RISK}.
        topic = resolve_episodes(
            [_external("1", B), _external("2", S), _external("3", R)]
        )[0]
        assert topic.topic_id == "DELIVER > TIME"
        assert topic.canonical_signature == frozenset({"DELIVER", "TIME"})
        assert topic.external_count == 3
        assert topic.source_episode_ids == ("1", "2", "3")


class TestDEviction:
    def test_resolution_scope_never_changes_identity(self):
        family = _family()
        fillers = [_external(f"f{i}", f"token {i}") for i in range(60)]
        small = resolve_episodes(family)
        big = resolve_episodes([*family, *fillers])
        assert len(small) == 1
        fam_big = next(t for t in big if t.topic_id == "DELIVER > TIME")
        assert fam_big.canonical_signature == small[0].canonical_signature
        assert fam_big.source_episode_ids == small[0].source_episode_ids
        assert fam_big.external_count == 3

    def test_leaving_the_window_shrinks_signals_only(self):
        # 51 external episodes -> the 50-episode attention window evicts the
        # oldest family episode; identity of the topic must not change.
        evicted_one = [*_family(), *[_external(f"f{i}", f"token {i}") for i in range(48)]]
        priorities = derive_attention_priorities(evicted_one)
        had = next(p for p in priorities if p.topic == "DELIVER > TIME")
        assert had.episodes_on_topic == 2  # only S ("2") and the third B remain

        evicted_two = [*_family(), *[_external(f"f{i}", f"token {i}") for i in range(49)]]
        priorities = derive_attention_priorities(evicted_two)
        had = next(p for p in priorities if p.topic == "DELIVER > TIME")
        assert had.episodes_on_topic == 1  # only the last B remains


class TestEAmbiguity:
    def test_late_synthesis_starts_its_own_topic(self):
        # X, Y first: S (= X∪Y) is compatible with two topics -> new topic.
        topics = resolve_episodes([_external("x", B), _external("y", Y), _external("s", S)])
        assert len(topics) == 3

    def test_early_synthesis_absorbs_its_parts(self):
        # S first: the narrowed parts are absorbed into the founder family.
        topic = resolve_episodes([_external("s", S), _external("x", B), _external("y", Y)])[0]
        assert topic.topic_id == "COST > DELIVER > TIME"
        assert topic.canonical_signature == frozenset({"DELIVER", "TIME", "COST"})
        assert topic.external_count == 3


class TestFNoPollution:
    def test_single_concept_overlap_never_merges(self):
        # {DELIVER}, {DELIVER,TIME}, {DELIVER,COST} share only DELIVER: 3 topics.
        episodes = [
            _external("1", A),
            _external("2", B),
            _external("3", "the delivery cost us"),
        ]
        topics = resolve_episodes(episodes)
        assert len(topics) == 3
        assert [t.topic_id for t in topics] == [
            "DELIVER",
            "DELIVER > TIME",
            "COST > DELIVER",
        ]

    def test_outcome_polarity_never_bridges_topics(self):
        # The pre-aboutness bridge token (FAIL/SUCCEED) is gone from identity:
        # "failed to deliver" and "succeeded in delivering" are one DELIVER
        # topic, and neither pulls a deliver-on-time mention into it.
        topics = resolve_episodes(
            [
                _external("1", "supplier failed to deliver"),
                _external("2", "supplier succeeded in delivering"),
                _external("3", "supplier delivered on time"),
            ]
        )
        assert len(topics) == 2
        assert [t.topic_id for t in topics] == ["DELIVER", "DELIVER > TIME"]
        assert topics[0].source_episode_ids == ("1", "2")


class TestGSelfReinforcement:
    def test_five_wake_pursue_cycles_are_a_fixed_point(self):
        j = Jarvis()
        for _ in range(5):
            j.think("the contractor keeps failing deliveries")
        before = j.attention_priorities()
        for _ in range(5):
            impulse = j.wake()
            assert impulse is not None
            pursued = j.pursue(impulse)
            assert pursued is not None and pursued.origin.value == "curiosity"
        after = j.attention_priorities()
        assert before == after  # curiosity echoes never re-rank attention
        external = [
            r for r in j.episodes.history() if r.origin is TriggerOrigin.COMPANION
        ]
        assert len(external) == 5  # and the external signal is untouched


class TestHPersistence:
    def test_json_and_sqlite_replay_resolve_identically(self, tmp_path: Path) -> None:
        json_dir = tmp_path / "json"
        sql_dir = tmp_path / "sql"
        triggers = [B, S, B]

        json_first = Jarvis.persistent(json_dir)
        for t in triggers:
            json_first.think(t)
        sql_first = Jarvis.database(sql_dir)
        for t in triggers:
            sql_first.think(t)

        # Reload from disk and resolve: identical identity set and attention.
        json_second = Jarvis.persistent(json_dir)
        sql_second = Jarvis.database(sql_dir)
        json_topics = resolve_episodes(json_second.episodes.history())
        sql_topics = resolve_episodes(sql_second.episodes.history())
        assert [t.topic_id for t in json_topics] == [t.topic_id for t in sql_topics]
        assert [t.canonical_signature for t in json_topics] == [
            t.canonical_signature for t in sql_topics
        ]
        assert [t.external_count for t in json_topics] == [
            t.external_count for t in sql_topics
        ]
        assert json_second.attention_priorities() == sql_second.attention_priorities()


class TestICrossMatterStability:
    def test_matter_and_qualifier_never_collapse_in_any_order(self):
        # {DELIVER}, {TIME}, {DELIVER,TIME} are three distinct families in every
        # arrival order: a shared single concept never unites different matters.
        episodes_by_trigger = [
            _external("1", A),
            _external("2", "the schedule slipped"),
            _external("3", B),
        ]
        for start in range(3):
            ep = [episodes_by_trigger[(start + i) % 3] for i in range(3)]
            topics = resolve_episodes(ep)
            assert len(topics) == 3
            assert {t.topic_id for t in topics} == {
                "DELIVER",
                "TIME",
                "DELIVER > TIME",
            }


class TestJRecency:
    def test_historical_count_is_not_current_salience(self):
        # 20 mentions, then 50 concept-free episodes push them past the window:
        # historical identity has 20 members, current attention has none.
        history = [
            *[_external(f"e{i}", A) for i in range(20)],
            *[_external(f"f{i}", f"token {i}") for i in range(50)],
        ]
        priorities = derive_attention_priorities(history)
        assert all(p.topic != "DELIVER" for p in priorities)

        topics = resolve_episodes(history)
        family = next(t for t in topics if t.topic_id == "DELIVER")
        assert family.external_count == 20
        assert len(family.source_episode_ids) == 20

    def test_inside_the_window_the_sharp_topic_ranks(self):
        fresh = derive_attention_priorities([_external(f"e{i}", A) for i in range(20)])
        assert any(
            p.topic == "DELIVER" and p.episodes_on_topic == 20 for p in fresh
        )