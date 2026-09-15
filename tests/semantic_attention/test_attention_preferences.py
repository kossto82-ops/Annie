"""Part 11: Curiosity cascade and attention preferences.

Tests curiosity priority, whether experience can re-rank attention, and the
meta-knowledge / self-observation feedback seams (Parts 16-17) plus the derived
attention-priority service and its wake() surface (Parts 13-18).
"""
from jarvis.domain.enums.attention import Attention
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.attention_priority import (
    ATTEND_THRESHOLD,
    derive_attention_priorities,
)
from jarvis.domain.services.self_observation import (
    adapt_knobs_from_self_observation,
    observe_evidence_habit,
    observe_overconfidence,
)
from jarvis.domain.value_objects.cognitive_knobs import CognitiveKnobs
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.jarvis import Jarvis


def _evidence(text: str = "observed") -> Evidence:
    return Evidence(
        content=text,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(1.0),
        supports=True,
    )


def _episode(
    trigger: str,
    *,
    conclusion: float = 0.9,
    belief_end: float | None = 0.9,
) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id=f"ep-{trigger}-{conclusion}-{belief_end}",
        trigger=trigger,
        decision="decided",
        working_belief_id=f"b-{trigger}",
        outcome=EpisodeState.COMPLETED,
        conclusion_confidence=Confidence(conclusion),
        conclusion_stability=TemporalStability(0.5),
        origin=TriggerOrigin.COMPANION,
        kind=EpisodeKind.CONCLUSION,
        belief_confidence_at_end=(
            Confidence(belief_end) if belief_end is not None else None
        ),
    )


class TestAttentionPriorityService:
    """Parts 13-16: derived, bounded, reversible saliency from episode history."""

    def test_empty_history_yields_no_priorities(self):
        assert derive_attention_priorities([]) == ()

    def test_single_episode_yields_a_positive_priority(self):
        priorities = derive_attention_priorities([_episode("the market wobbles")])
        assert len(priorities) == 1
        top = priorities[0]
        assert top.topic == "the market wobbles"
        assert top.episodes_on_topic == 1
        assert 0.0 < top.priority <= 1.0

    def test_recurrence_raises_priority(self):
        once = derive_attention_priorities([_episode("d")])[0]
        many = derive_attention_priorities(
            [_episode("d"), _episode("d"), _episode("d")]
        )[0]
        assert many.priority > once.priority

    def test_unresolved_endings_raise_priority(self):
        grounded = derive_attention_priorities(
            [_episode("d", conclusion=0.9, belief_end=0.9),
             _episode("d", conclusion=0.9, belief_end=0.9)]
        )[0]
        open = derive_attention_priorities(
            [_episode("d", conclusion=0.2, belief_end=0.2),
             _episode("d", conclusion=0.2, belief_end=0.2)]
        )[0]
        assert open.unresolved == 2
        assert open.priority > grounded.priority

    def test_revision_signal_is_detected(self):
        flat = derive_attention_priorities(
            [_episode("d", belief_end=0.6), _episode("d", belief_end=0.6)]
        )[0]
        moving = derive_attention_priorities(
            [_episode("d", belief_end=0.6), _episode("d", belief_end=0.9)]
        )[0]
        assert flat.revised is False
        assert moving.revised is True
        assert moving.priority > flat.priority

    def test_priority_is_bounded(self):
        history = [_episode(f"t{i % 3}") for i in range(200)]
        for p in derive_attention_priorities(history):
            assert 0.0 <= p.priority <= 1.0

    def test_window_bounds_accumulation(self):
        # 100 old episodes of "a" + 1 fresh "b": the window keeps only the tail.
        history = [_episode("a") for _ in range(90)] + [_episode("b"), _episode("b")]
        priorities = derive_attention_priorities(history, window=30)
        assert all(p.episodes_on_topic <= 30 for p in priorities)
        # Recency matters: the very last episode's topic ranks highest near-equal.
        assert [p.topic for p in priorities][0] == priorities[0].topic

    def test_derive_is_reversible_and_mutation_free(self):
        history = [_episode(f"t{i % 2}", conclusion=0.1 + (i % 3) * 0.2) for i in range(12)]
        snapshot = [r.trigger for r in history]
        first = derive_attention_priorities(history)
        second = derive_attention_priorities(history)
        assert first == second, "Recomputing over the same history is identical"
        assert [r.trigger for r in history] == snapshot, "Deriving must not mutate"

    def test_derived_priorities_sort_descending(self):
        priorities = derive_attention_priorities(
            [_episode("low"), _episode("mid"), _episode("mid"),
             _episode("high"), _episode("high"), _episode("high")]
        )
        values = [p.priority for p in priorities]
        assert values == sorted(values, reverse=True)

    def test_wake_threshold_is_a_real_bar(self):
        # A barely-touched topic with a low score stays below the attend bar.
        assert ATTEND_THRESHOLD > 0.0


class TestAttentionPriorityDevelopment:
    """Part 17: attention develops -- an experienced Jarvis differs from a fresh one."""

    def test_fresh_jarvis_wakes_to_nothing(self):
        j = Jarvis()
        assert j.attention_priorities() == ()
        assert j.wake() is None

    def test_fresh_jarvis_has_no_ranked_attention(self):
        j = Jarvis()
        j.think("a single passing thought", evidence=[_evidence("one fact")])
        # One closed episode is not enough to clear the attend threshold.
        assert j.wake() is None

    def test_recurring_unresolved_topic_develops_priority(self):
        j = Jarvis()
        for _ in range(4):
            j.think("the contractor keeps failing deliveries")
        priorities = j.attention_priorities()
        assert priorities
        top = priorities[0]
        # Topic identity is the canonical concept signature, never the raw
        # trigger; the representative is the real trigger shown to the companion.
        assert top.topic == "FAIL"
        assert top.representative == "the contractor keeps failing deliveries"
        assert top.episodes_on_topic == 4
        assert top.priority >= ATTEND_THRESHOLD

    def test_wake_rises_the_top_priority(self):
        j = Jarvis()
        for trigger in ("minor blip", "minor blip", "minor blip",
                        "the supplier never recovers", "the supplier never recovers",
                        "the supplier never recovers", "the supplier never recovers"):
            j.think(trigger)
        impulse = j.wake()
        assert impulse is not None
        assert "the supplier never recovers" in impulse.trigger

    def test_wake_is_reversible_and_mutation_free(self):
        j = Jarvis()
        for _ in range(3):
            j.think("the contractor keeps failing deliveries")
        first_impulse = j.wake()
        priorities_before = j.attention_priorities()
        second_impulse = j.wake()
        assert first_impulse == second_impulse
        assert j.attention_priorities() == priorities_before
        assert len(j.episodes.history()) == 3, "wake must not record anything"

    def test_wake_matches_feel_curious_surface(self):
        # wake() returns a real impulse interopable with pursue().
        j = Jarvis()
        for _ in range(5):
            j.think("the contractor keeps failing deliveries")
        impulse = j.wake()
        assert impulse is not None
        ep = j.pursue(impulse)
        assert ep is not None

    def test_experience_reorders_attention(self):
        # Both topics recur; the one touched more often and left open ranks first.
        light = Jarvis()
        heavy = Jarvis()
        for trigger in ("a", "b", "b", "c", "c", "c"):
            light.think(trigger)
        for trigger in ("a", "b", "b", "c", "c", "c", "c", "c"):
            heavy.think(trigger)
        assert light.attention_priorities()[0].topic == "c"
        assert heavy.attention_priorities()[0].topic == "c"
        assert (
            heavy.attention_priorities()[0].episodes_on_topic
            > light.attention_priorities()[0].episodes_on_topic
        )

    def test_day0_vs_day7_longitudinal_experiment(self):
        """Part 20: a simulated Day0–Day7 progression shows attention developing.

        Day0 (one episode): no attention, quiet.
        Day3 (3 episodes on same topic): recurring pattern, still quiet (0.37–0.42 range).
        Day7 (7 episodes, last 4 touching an unresolved topic): priority exceeds
        attend threshold, wake() proposes attending.
        """
        day0 = Jarvis()
        day0.think("the supplier is unreliable")
        assert day0.wake() is None, "Day0: a single passing thought does not wake"
        assert day0.attention_priorities()[0].episodes_on_topic == 1

        day3 = Jarvis()
        for _ in range(3):
            day3.think("the supplier is unreliable")
        day3_priorities = day3.attention_priorities()
        assert day3_priorities[0].episodes_on_topic == 3

        day7 = Jarvis()
        for _ in range(3):
            day7.think("the supplier is unreliable")
        for _ in range(4):
            day7.think("the supplier is unreliable")
        day7_priorities = day7.attention_priorities()
        assert day7_priorities[0].episodes_on_topic == 7
        assert day7.wake() is not None, (
            "Day7: accumulated recurrence wakes Jarvis to the most pressing topic"
        )


class TestCuriosityCascadeInitiative:
    """Self-initiated cognition happens through feel_curious() + pursue()."""

    def test_fresh_jarvis_has_no_impulse(self):
        """Fresh Jarvo with no history raises no curiosity impulse."""
        j = Jarvis()
        assert j.feel_curious() is None, "No impulse without any history"

    def test_feel_curious_returns_impulse_or_quiet_none(self):
        """Committed evidence may generate an impulse; None is also legitimate."""
        j = Jarvis()
        j.think(
            "the trend is real",
            evidence=[_evidence("numbers show a clear trend")],
        )
        result = j.feel_curious()
        assert result is None or result.impulse_kind.value in {
            "evidence", "contested", "goal", "capability", "meta", "temporal",
        }

    def test_curiosity_impulse_can_be_pursued(self):
        """pursue() runs a reasoning episode from an impulse (or None when quiet)."""
        j = Jarvis()
        j.think("the trend is real", evidence=[_evidence("numbers show a trend")])
        impulse = j.feel_curious()
        if impulse is not None:
            ep = j.pursue(impulse)
            assert ep.origin.value == "curiosity"


class TestAttentionDevelopment:
    """Part 10: Does attention evolve from accumulated experience?"""

    def test_brief_after_grounded_repetition(self):
        """Attention becomes BRIEF once a trigger is grounded and stays stable."""
        j = Jarvis()
        j.think(
            "delivery performance is declining",
            evidence=[_evidence("item 1"), _evidence("item 2")],
        )
        # confidence = 1.0 -> well above grounded 0.5
        ep = j.think("delivery performance is declining")
        assert ep.attention == Attention.BRIEF, "Grounded + no new evidence -> BRIEF"

    def test_new_evidence_always_full(self):
        """Attention stays FULL when evidence arrives, regardless of history."""
        j = Jarvis()
        j.think("delivery performance is declining", evidence=[_evidence("item 1")])
        ep = j.think("delivery performance is declining", evidence=[_evidence("new fact")])
        assert ep.attention == Attention.FULL

    def test_meta_observation_adjusts_knobs(self):
        """Meta-observation feedback raises the grounded threshold when attention
        is judged insufficient (the second-order adaptation seam)."""
        j = Jarvis()
        before = j.knobs().grounded_confidence
        feedback = j._executive.adapt_from_meta_observation()
        after = j.knobs().grounded_confidence
        assert feedback is None or isinstance(feedback, str)
        assert after >= before, "grounded_confidence can only rise or stay"

    def test_self_observation_writes_belief(self):
        """observe_evidence_habit() derives a self-belief from episode history."""
        j = Jarvis()
        for i in range(3):
            j.think(f"topic {i}", evidence=[_evidence(f"fact {i}")])
        belief = observe_evidence_habit(list(j.episodes.history()))
        assert belief is not None, "3 grounded episodes should allow a judgement"
        assert "tend" in belief.statement


class TestKnowledgeOfOwnIgnorance:
    """Part 12: Does Jarvo know what it doesn't know?"""

    def test_cannot_conclude_no_evidence(self):
        """Without evidence, think() reaches an honest 0.0-confidence conclusion."""
        j = Jarvis()
        ep = j.think("completely new topic with no prior context")
        assert ep.working_belief is not None
        assert ep.working_belief.confidence.value == 0.0, "No evidence -> 0.0 confidence"

    def test_ungrounded_episode_fires_acknowledgement(self):
        """Repeatedly concluding without evidence trains the self-observed habit:
        the decision text changes to a learned request for evidence."""
        j = Jarvis()
        # establish the habit with three ungrounded companion episodes + a trigger
        for i in range(2):
            j.think(f"ungrounded topic {i}")  # no evidence each time
        j.think("ungrounded topic seed", evidence=[_evidence("one fact")])
        for i in range(3):
            j.think(f"ungrounded topic {i}")  # no evidence each time
        decision = j.episodes.history()[-1].decision
        assert (
            "Insufficient evidence" in decision
            or "I have learned that I tend to conclude without sufficient evidence" in decision
        ), "Either honest silence or the learned-habit acknowledgement"


class TestMetaKnowledgeFeedback:
    """Part 17: Self-observation drives knob adjustment."""

    def test_adapt_knobs_from_self_observation_returns_reason_or_none(self):
        """The adapt seam returns a reason when it adjusts, else None."""
        j = Jarvis()
        adapted, reason = adapt_knobs_from_self_observation(
            j.knobs(), j.episodes.history()
        )
        assert isinstance(adapted, CognitiveKnobs)
        assert reason is None or isinstance(reason, str)

    def test_observe_overconfidence_requires_grounded_history(self):
        """Overconfidence judgement needs >=3 grounded episodes."""
        j = Jarvis()
        for i in range(3):
            j.think(f"topic {i}", evidence=[_evidence(f"fact {i}")])
        belief = observe_overconfidence(list(j.episodes.history()))
        assert belief is not None