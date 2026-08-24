"""Tests for goals attached to episodes (Vision §12, §26)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis import Jarvis
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.goal_reflection import recurring_goals
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.goal import Goal
from jarvis.domain.value_objects.temporal_stability import TemporalStability


def _grounded_evidence() -> tuple[Evidence, ...]:
    """Two strong, well-spread supporting pieces: grounds a belief (confidence
    above the threshold) with enough temporal spread that the conclusion is not
    overconfident -- so the self-model stays quiet.
    """
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return (
        Evidence(
            content="a solid reason",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(0.9),
            observed_at=base,
        ),
        Evidence(
            content="a second solid reason later",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(0.9),
            observed_at=base + timedelta(days=40),
        ),
    )


class TestGoal:
    def test_requires_a_statement(self) -> None:
        with pytest.raises(ValueError):
            Goal(statement="  ")

    def test_may_carry_a_success_criterion(self) -> None:
        goal = Goal(statement="understand the problem", success_criterion="I can restate it")
        assert goal.success_criterion == "I can restate it"


class TestGoalDecomposition:
    def test_a_goal_may_name_a_larger_goal_it_is_part_of(self) -> None:
        child = Goal(statement="write the base case", part_of="master recursion")
        assert child.part_of == "master recursion"

    def test_a_goal_cannot_be_part_of_itself(self) -> None:
        with pytest.raises(ValueError):
            Goal(statement="x", part_of="x")

    def test_an_empty_parent_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            Goal(statement="x", part_of="  ")

    def test_reaching_a_sub_goal_credits_the_parent(self) -> None:
        jarvis = Jarvis()
        child = Goal(statement="write the base case", part_of="master recursion")
        jarvis.mark_goal_reached(child)
        parent = jarvis.belief_about_goal("master recursion")
        assert parent is not None and parent.confidence.value > 0.0

    def test_an_unmet_sub_goal_does_not_raise_the_parent(self) -> None:
        jarvis = Jarvis()
        child = Goal(statement="write the base case", part_of="master recursion")
        jarvis.mark_goal_reached(child, reached=False)
        parent = jarvis.belief_about_goal("master recursion")
        assert parent is not None and parent.confidence.value == 0.0

    def test_a_parentless_goal_creates_no_parent_belief(self) -> None:
        jarvis = Jarvis()
        jarvis.mark_goal_reached(Goal(statement="write the base case"))
        assert jarvis.belief_about_goal("master recursion") is None

    def test_the_parent_credit_survives_a_restart(self, tmp_path: Path) -> None:
        child = Goal(statement="write the base case", part_of="master recursion")
        first = Jarvis.persistent(tmp_path)
        first.mark_goal_reached(child)
        before = first.belief_about_goal("master recursion")
        assert before is not None

        restarted = Jarvis.persistent(tmp_path)
        after = restarted.belief_about_goal("master recursion")
        assert after is not None
        assert after.confidence.value == before.confidence.value


class TestGoalProgress:
    _PARENT = "master recursion"
    _PARTS = ("write the base case", "handle the recursive step", "test the edge cases")

    def _reach(self, jarvis: Jarvis, part: str, *, reached: bool = True) -> None:
        jarvis.mark_goal_reached(
            Goal(statement=part, part_of=self._PARENT), reached=reached
        )

    def test_sub_goals_and_progress_track_recorded_parts(self) -> None:
        jarvis = Jarvis()
        self._reach(jarvis, self._PARTS[0])
        self._reach(jarvis, self._PARTS[1])
        self._reach(jarvis, self._PARTS[2], reached=False)
        assert set(jarvis.sub_goals(self._PARENT)) == set(self._PARTS)
        assert jarvis.goal_progress(self._PARENT) == (2, 3)

    def test_a_goal_with_no_parts_has_no_progress(self) -> None:
        jarvis = Jarvis()
        jarvis.mark_goal_reached(Goal(statement="a plain goal"))
        assert jarvis.sub_goals("a plain goal") == ()
        assert jarvis.goal_progress("a plain goal") == (0, 0)

    def test_progress_shows_in_introspection(self) -> None:
        jarvis = Jarvis()
        # Make the parent a recurring goal so it appears in the self-account.
        for question in ("q1", "q2", "q3"):
            jarvis.think(question, goal=Goal(statement=self._PARENT))
        self._reach(jarvis, self._PARTS[0])
        self._reach(jarvis, self._PARTS[1])
        self._reach(jarvis, self._PARTS[2], reached=False)
        text = jarvis.introspect()
        assert "2 of 3 parts reached" in text

    def test_progress_survives_a_restart(self, tmp_path: Path) -> None:
        first = Jarvis.persistent(tmp_path)
        self._reach(first, self._PARTS[0])
        self._reach(first, self._PARTS[1])
        assert first.goal_progress(self._PARENT) == (2, 2)

        restarted = Jarvis.persistent(tmp_path)
        assert restarted.goal_progress(self._PARENT) == (2, 2)
        assert set(restarted.sub_goals(self._PARENT)) == set(self._PARTS[:2])


class TestThinkWithAGoal:
    def test_an_episode_without_a_goal_has_none(self) -> None:
        assert Jarvis().think("a question").goal is None

    def test_a_goal_is_attached_to_the_episode(self) -> None:
        goal = Goal(statement="decide whether to refactor")
        episode = Jarvis().think("is the module too complex?", goal=goal)
        assert episode.goal is goal

    def test_the_decision_names_the_goal_when_present(self) -> None:
        goal = Goal(statement="decide whether to refactor")
        episode = Jarvis().think("is the module too complex?", goal=goal)
        assert episode.result is not None
        assert "decide whether to refactor" in episode.result

    def test_the_decision_is_unaffected_without_a_goal(self) -> None:
        episode = Jarvis().think("is the module too complex?")
        assert episode.result is not None
        assert "Toward" not in episode.result


class TestGoalIsRemembered:
    def test_a_goal_directed_episode_records_its_goal(self) -> None:
        jarvis = Jarvis()
        jarvis.think("is the module too complex?", goal=Goal(statement="decide to refactor"))
        record = jarvis.episodes.history()[-1]
        assert record.goal == "decide to refactor"

    def test_a_goal_less_episode_records_none(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a plain question")
        assert jarvis.episodes.history()[-1].goal is None


class TestRecurringGoals:
    def test_a_goal_pursued_repeatedly_is_surfaced_with_its_count(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="ship the parser")
        for question in ("is it too slow?", "is it too complex?", "is it well tested?"):
            jarvis.think(question, goal=goal)
        assert jarvis.recurring_goals() == (("ship the parser", 3),)

    def test_a_one_off_goal_does_not_recur(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a question", goal=Goal(statement="a passing thought"))
        jarvis.think("another", goal=Goal(statement="a passing thought"))
        assert jarvis.recurring_goals() == ()

    def test_goal_less_episodes_never_appear(self) -> None:
        jarvis = Jarvis()
        for _ in range(4):
            jarvis.think("a plain question")
        assert jarvis.recurring_goals() == ()

    def test_goals_are_ordered_by_descending_count(self) -> None:
        jarvis = Jarvis()
        for _ in range(3):
            jarvis.think("q", goal=Goal(statement="lesser"))
        for _ in range(5):
            jarvis.think("q", goal=Goal(statement="greater"))
        assert jarvis.recurring_goals() == (("greater", 5), ("lesser", 3))


class TestRecurringGoalsService:
    def test_self_directed_episodes_with_goals_are_ignored(self) -> None:
        def record(origin: TriggerOrigin) -> EpisodeRecord:
            return EpisodeRecord(
                episode_id="e",
                trigger="t",
                decision="d",
                working_belief_id="b",
                outcome=EpisodeState.COMPLETED,
                conclusion_confidence=Confidence(0.6),
                conclusion_stability=TemporalStability(0.5),
                origin=origin,
                kind=EpisodeKind.CONCLUSION,
                goal="a self goal",
            )

        history = [record(TriggerOrigin.CURIOSITY) for _ in range(4)]
        assert recurring_goals(history) == ()


class TestGoalReachability:
    def test_marking_a_goal_reached_forms_a_reachable_belief(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="ship the parser")
        assert jarvis.belief_about_goal(goal) is None
        belief = jarvis.mark_goal_reached(goal)
        assert belief.confidence.value > 0.0
        assert jarvis.belief_about_goal(goal) is belief

    def test_repeated_reaches_build_confidence_failures_erode_it(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="ship the parser")
        jarvis.mark_goal_reached(goal)
        jarvis.mark_goal_reached(goal)
        confident = jarvis.belief_about_goal(goal)
        assert confident is not None
        high = confident.confidence.value

        jarvis.mark_goal_reached(goal, reached=False)
        lowered = jarvis.belief_about_goal(goal)
        assert lowered is not None
        assert lowered.confidence.value < high

    def test_an_unmarked_goal_has_no_reachability_belief(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a question", goal=Goal(statement="never marked"))
        assert jarvis.belief_about_goal("never marked") is None

    def test_belief_about_goal_accepts_a_statement_string(self) -> None:
        jarvis = Jarvis()
        jarvis.mark_goal_reached(Goal(statement="ship the parser"))
        assert jarvis.belief_about_goal("ship the parser") is not None

    def test_reachability_survives_a_restart(self, tmp_path: Path) -> None:
        goal = Goal(statement="ship the parser")
        first = Jarvis.persistent(tmp_path)
        first.mark_goal_reached(goal)
        before = first.belief_about_goal(goal)
        assert before is not None

        restarted = Jarvis.persistent(tmp_path)
        after = restarted.belief_about_goal(goal)
        assert after is not None
        assert after.confidence.value == before.confidence.value


class TestRecurringGoalBecomesCuriosity:
    def test_a_recurring_goal_raises_curiosity_when_self_model_is_quiet(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="ship the parser")
        # Grounded, well-spread episodes keep the self-model quiet, so the
        # recurring goal is the most interesting remaining unknown.
        jarvis.think("is it correct?", evidence=_grounded_evidence(), goal=goal)
        jarvis.think("is it correct?", goal=goal)
        jarvis.think("is it correct?", goal=goal)
        assert jarvis.self_beliefs() == () or all(
            b.confidence.value == 0.0 for b in jarvis.self_beliefs()
        )
        impulse = jarvis.feel_curious()
        assert impulse is not None
        assert "ship the parser" in impulse.trigger
        assert impulse.prompted_by_belief_id is None

    def test_no_recurring_goal_raises_no_goal_curiosity(self) -> None:
        jarvis = Jarvis()
        # Same quiet self-model, but distinct goals -> nothing recurs.
        jarvis.think("is it correct?", evidence=_grounded_evidence(), goal=Goal(statement="alpha"))
        jarvis.think("is it correct?", goal=Goal(statement="beta"))
        jarvis.think("is it correct?", goal=Goal(statement="gamma"))
        assert jarvis.recurring_goals() == ()
        assert jarvis.feel_curious() is None

    def test_curiosity_prefers_a_goal_it_keeps_failing_to_reach(self) -> None:
        jarvis = Jarvis()
        reachable = Goal(statement="the easy goal")
        unreached = Goal(statement="the hard goal")
        # One grounded belief keeps the self-model quiet; both goals recur equally.
        jarvis.think("is it correct?", evidence=_grounded_evidence(), goal=reachable)
        for _ in range(2):
            jarvis.think("is it correct?", goal=reachable)
        for _ in range(3):
            jarvis.think("is it correct?", goal=unreached)
        # Two reaches ground the reachable goal above the threshold; the hard goal
        # is marked unreached, so it is the sharper tension.
        jarvis.mark_goal_reached(reachable)
        jarvis.mark_goal_reached(reachable)
        jarvis.mark_goal_reached(unreached, reached=False)

        impulse = jarvis.feel_curious()
        assert impulse is not None
        assert "the hard goal" in impulse.trigger
        assert "without reaching it" in impulse.trigger

    def test_curiosity_still_raises_a_reachable_recurring_goal(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="the easy goal")
        jarvis.think("is it correct?", evidence=_grounded_evidence(), goal=goal)
        for _ in range(2):
            jarvis.think("is it correct?", goal=goal)
        jarvis.mark_goal_reached(goal)
        jarvis.mark_goal_reached(goal)

        impulse = jarvis.feel_curious()
        assert impulse is not None
        assert "the easy goal" in impulse.trigger
        assert "without reaching it" not in impulse.trigger


class TestPursuingAGoalCuriosityRecordsIt:
    def test_pursuing_a_recurring_goal_impulse_records_the_episode_toward_it(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="the hard goal")
        jarvis.think("is it correct?", evidence=_grounded_evidence(), goal=goal)
        for _ in range(2):
            jarvis.think("is it correct?", goal=goal)
        jarvis.mark_goal_reached(goal, reached=False)

        impulse = jarvis.feel_curious()
        assert impulse is not None and impulse.goal == "the hard goal"
        jarvis.pursue(impulse)
        assert jarvis.episodes.history()[-1].goal == "the hard goal"

    def test_pursuing_a_self_tendency_impulse_records_no_goal(self) -> None:
        jarvis = Jarvis()
        # Ungrounded episodes make the evidence-habit self-belief confident, so
        # feel_curious raises a self-tendency impulse (which concerns no goal).
        for topic in ("a", "b", "c"):
            jarvis.think(f"q {topic}")
        impulse = jarvis.feel_curious()
        assert impulse is not None and impulse.goal is None
        jarvis.pursue(impulse)
        assert jarvis.episodes.history()[-1].goal is None


class TestReflectionEffort:
    def test_it_counts_self_directed_episodes_toward_a_goal(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="the hard goal")
        jarvis.think("is it correct?", evidence=_grounded_evidence(), goal=goal)
        for _ in range(2):
            jarvis.think("is it correct?", goal=goal)
        jarvis.mark_goal_reached(goal, reached=False)
        for _ in range(2):
            impulse = jarvis.feel_curious()
            assert impulse is not None and impulse.goal == "the hard goal"
            jarvis.pursue(impulse)
        assert jarvis.reflection_effort("the hard goal") == 2

    def test_a_never_pursued_goal_has_no_effort(self) -> None:
        jarvis = Jarvis()
        jarvis.think("q", goal=Goal(statement="untouched"))
        assert jarvis.reflection_effort("untouched") == 0

    def test_companion_goal_episodes_are_not_reflection_effort(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="companion goal")
        for _ in range(3):
            jarvis.think("q", goal=goal)
        assert jarvis.reflection_effort("companion goal") == 0


class TestGivingUpOnAStuckGoal:
    @staticmethod
    def _with_two_stuck_goals() -> Jarvis:
        jarvis = Jarvis()
        alpha = Goal(statement="alpha")
        beta = Goal(statement="beta")
        # One grounded belief (shared trigger) keeps the self-model quiet; both
        # goals recur equally and are both learned unreachable.
        jarvis.think("q", evidence=_grounded_evidence(), goal=alpha)
        for _ in range(2):
            jarvis.think("q", goal=alpha)
        for _ in range(3):
            jarvis.think("q", goal=beta)
        jarvis.mark_goal_reached(alpha, reached=False)
        jarvis.mark_goal_reached(beta, reached=False)
        return jarvis

    def test_an_exhausted_stuck_goal_yields_to_a_less_wrestled_one(self) -> None:
        jarvis = self._with_two_stuck_goals()
        # Wonder about alpha (first by recurrence) until it is exhausted.
        for _ in range(3):
            impulse = jarvis.feel_curious()
            assert impulse is not None and impulse.goal == "alpha"
            jarvis.pursue(impulse)
        assert jarvis.reflection_effort("alpha") == 3

        # Alpha is now wondered-out; curiosity turns to the less-wrestled beta.
        nxt = jarvis.feel_curious()
        assert nxt is not None and nxt.goal == "beta"

    def _exhaust(self, jarvis: Jarvis, goal: str) -> None:
        for _ in range(3):
            impulse = jarvis.feel_curious()
            assert impulse is not None and impulse.goal == goal
            jarvis.pursue(impulse)

    def test_curiosity_moves_on_when_the_only_stuck_goal_is_exhausted(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="the hard goal")
        jarvis.think("q", evidence=_grounded_evidence(), goal=goal)
        for _ in range(2):
            jarvis.think("q", goal=goal)
        jarvis.mark_goal_reached(goal, reached=False)
        self._exhaust(jarvis, "the hard goal")
        # Turned over enough, no progress, nothing else to wonder about.
        assert jarvis.feel_curious() is None

    def test_reaching_a_goal_clears_the_suppression(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="the hard goal")
        jarvis.think("q", evidence=_grounded_evidence(), goal=goal)
        for _ in range(2):
            jarvis.think("q", goal=goal)
        jarvis.mark_goal_reached(goal, reached=False)
        self._exhaust(jarvis, "the hard goal")
        assert jarvis.feel_curious() is None  # suppressed

        # Learning it is reachable clears the suppression: it may surface again.
        # (Enough reaches to outweigh the earlier failure and cross the threshold.)
        for _ in range(4):
            jarvis.mark_goal_reached(goal)
        reachable = jarvis.belief_about_goal(goal)
        assert reachable is not None and reachable.confidence.value >= 0.5
        revived = jarvis.feel_curious()
        assert revived is not None and revived.goal == "the hard goal"


class TestAskingForHelp:
    @staticmethod
    def _exhausted_stuck(jarvis: Jarvis, goal: Goal) -> None:
        jarvis.think("q", evidence=_grounded_evidence(), goal=goal)
        for _ in range(2):
            jarvis.think("q", goal=goal)
        jarvis.mark_goal_reached(goal, reached=False)
        for _ in range(3):
            impulse = jarvis.feel_curious()
            assert impulse is not None and impulse.goal == goal.statement
            jarvis.pursue(impulse)

    def test_an_exhausted_stuck_goal_is_asked_about(self) -> None:
        jarvis = Jarvis()
        self._exhausted_stuck(jarvis, Goal(statement="master recursion"))
        assert jarvis.stuck_goals() == ("master recursion",)
        message = jarvis.ask_for_help()
        assert message is not None
        assert "master recursion" in message
        assert "can you help?" in message

    def test_a_goal_still_under_the_effort_threshold_is_not_asked_about(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="the hard goal")
        jarvis.think("q", evidence=_grounded_evidence(), goal=goal)
        for _ in range(2):
            jarvis.think("q", goal=goal)
        jarvis.mark_goal_reached(goal, reached=False)
        # Only one reflection so far -- not yet exhausted.
        impulse = jarvis.feel_curious()
        assert impulse is not None
        jarvis.pursue(impulse)
        assert jarvis.stuck_goals() == ()
        assert jarvis.ask_for_help() is None

    def test_a_reached_goal_is_no_longer_asked_about(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="master recursion")
        self._exhausted_stuck(jarvis, goal)
        assert jarvis.stuck_goals() == ("master recursion",)

        for _ in range(4):
            jarvis.mark_goal_reached(goal)
        assert jarvis.stuck_goals() == ()
        assert jarvis.ask_for_help() is None


class TestReceivingHelp:
    @staticmethod
    def _exhausted_stuck(jarvis: Jarvis, goal: Goal) -> None:
        jarvis.think("q", evidence=_grounded_evidence(), goal=goal)
        for _ in range(2):
            jarvis.think("q", goal=goal)
        jarvis.mark_goal_reached(goal, reached=False)
        for _ in range(3):
            impulse = jarvis.feel_curious()
            assert impulse is not None
            jarvis.pursue(impulse)

    def test_help_is_recorded_with_companion_provenance(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="master recursion")
        belief = jarvis.receive_help(goal)
        assert belief.confidence.value > 0.0
        assert "companion" in belief.explain().narrate()

    def test_sustained_help_lifts_a_stuck_goal_and_ends_the_asking(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="master recursion")
        self._exhausted_stuck(jarvis, goal)
        assert jarvis.stuck_goals() == ("master recursion",)

        # One answer is not proof; sustained helpful guidance lifts it.
        jarvis.receive_help(goal)
        jarvis.receive_help(goal)
        assert jarvis.stuck_goals() == ()
        assert jarvis.ask_for_help() is None

    def test_unhelpful_guidance_does_not_lift_a_stuck_goal(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="master recursion")
        self._exhausted_stuck(jarvis, goal)
        jarvis.receive_help(goal, helpful=False)
        jarvis.receive_help(goal, helpful=False)
        assert jarvis.stuck_goals() == ("master recursion",)
        assert jarvis.ask_for_help() is not None

    def test_helpful_guidance_teaches_that_the_companion_is_helpful(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="master recursion")
        jarvis.receive_help(goal)
        belief = jarvis.companion.belief_about("is helpful when I am stuck")
        assert belief is not None and belief.confidence.value > 0.0
        assert "is helpful when I am stuck" in jarvis.introspect()

    def test_unhelpful_guidance_weakens_the_companion_helpfulness_belief(self) -> None:
        jarvis = Jarvis()
        goal = Goal(statement="master recursion")
        jarvis.receive_help(goal)
        jarvis.receive_help(goal)
        strong = jarvis.companion.belief_about("is helpful when I am stuck")
        assert strong is not None
        high = strong.confidence.value

        jarvis.receive_help(goal, helpful=False)
        weakened = jarvis.companion.belief_about("is helpful when I am stuck")
        assert weakened is not None
        assert weakened.confidence.value < high

    def test_a_goal_with_no_help_leaves_the_companion_model_untouched(self) -> None:
        jarvis = Jarvis()
        jarvis.mark_goal_reached(Goal(statement="master recursion"), reached=False)
        assert jarvis.companion.belief_about("is helpful when I am stuck") is None


class TestAskPhrasing:
    @staticmethod
    def _exhausted_stuck(jarvis: Jarvis, goal: Goal) -> None:
        jarvis.think("q", evidence=_grounded_evidence(), goal=goal)
        for _ in range(2):
            jarvis.think("q", goal=goal)
        jarvis.mark_goal_reached(goal, reached=False)
        for _ in range(3):
            impulse = jarvis.feel_curious()
            assert impulse is not None
            jarvis.pursue(impulse)

    def test_a_proven_helpful_companion_warms_the_request(self) -> None:
        jarvis = Jarvis()
        # Build a confident "companion is helpful" belief on an unrelated goal.
        past = Goal(statement="a past goal")
        jarvis.receive_help(past)
        jarvis.receive_help(past)
        # A fresh, un-helped stuck goal remains to ask about.
        self._exhausted_stuck(jarvis, Goal(statement="the hard goal"))

        message = jarvis.ask_for_help()
        assert message is not None
        assert "You've helped me get unstuck before" in message
        assert "the hard goal" in message

    def test_without_a_helpfulness_belief_the_request_is_neutral(self) -> None:
        jarvis = Jarvis()
        self._exhausted_stuck(jarvis, Goal(statement="the hard goal"))
        message = jarvis.ask_for_help()
        assert message is not None
        assert "You've helped me get unstuck before" not in message
        assert "on my own — can you help?" in message


class TestRelationshipContinuity:
    @staticmethod
    def _exhausted_stuck(jarvis: Jarvis, goal: Goal) -> None:
        jarvis.think("q", evidence=_grounded_evidence(), goal=goal)
        for _ in range(2):
            jarvis.think("q", goal=goal)
        jarvis.mark_goal_reached(goal, reached=False)
        for _ in range(3):
            impulse = jarvis.feel_curious()
            assert impulse is not None
            jarvis.pursue(impulse)

    def test_a_warmed_relationship_survives_a_restart(self, tmp_path: Path) -> None:
        first = Jarvis.persistent(tmp_path)
        # Earn a confident "companion is helpful" belief, and leave a stuck goal.
        past = Goal(statement="a past goal")
        first.receive_help(past)
        first.receive_help(past)
        self._exhausted_stuck(first, Goal(statement="the hard goal"))
        warm_before = first.ask_for_help()
        assert warm_before is not None
        assert "You've helped me get unstuck before" in warm_before

        # A fresh process wired to the same directory must remember the warmth.
        restarted = Jarvis.persistent(tmp_path)
        belief = restarted.companion.belief_about("is helpful when I am stuck")
        assert belief is not None and belief.confidence.value >= 0.5
        warm_after = restarted.ask_for_help()
        assert warm_after is not None
        assert "You've helped me get unstuck before" in warm_after
        assert "the hard goal" in warm_after
