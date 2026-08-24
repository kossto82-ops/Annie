"""The Jarvis entry point.

``Jarvis.think(trigger)`` runs a complete cognitive lifecycle over a trigger and
returns the resulting episode. The nervous system is exposed so callers can
subscribe to cognitive events *before* thinking begins.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from jarvis.domain.aggregates.cognitive_episode import CognitiveEpisode
from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.events.action_events import ActionOutcomeRecorded
from jarvis.domain.events.belief_events import ContradictionDetected
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.repositories.belief_repository import BeliefRepository
from jarvis.domain.repositories.episode_repository import EpisodeRepository
from jarvis.domain.services.action_advisor import recommend as recommend_stance
from jarvis.domain.services.curiosity import wonder
from jarvis.domain.services.goal_reflection import recurring_goals, reflection_effort
from jarvis.domain.services.self_observation import (
    observe_evidence_habit,
    observe_overconfidence,
    observe_prediction_accuracy,
)
from jarvis.domain.value_objects.action import Action
from jarvis.domain.value_objects.action_recommendation import ActionRecommendation
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.curiosity_impulse import CuriosityImpulse
from jarvis.domain.value_objects.deliberation import Deliberation
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.goal import Goal
from jarvis.domain.value_objects.state_summary import LearnedAction, StateSummary
from jarvis.executive.executive_controller import ExecutiveController
from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore
from jarvis.infrastructure.in_memory_episode_store import InMemoryEpisodeStore
from jarvis.infrastructure.json_belief_store import JsonBeliefStore
from jarvis.infrastructure.json_episode_store import JsonEpisodeStore
from jarvis.nervous_system.nervous_system import NervousSystem
from jarvis.observability.episode_trace import EpisodeTrace


class Jarvis:
    """A long-term cognitive companion (first vertical slice)."""

    def __init__(
        self,
        nervous_system: NervousSystem | None = None,
        beliefs: BeliefRepository | None = None,
        episodes: EpisodeRepository | None = None,
        companion_store: BeliefRepository | None = None,
        actions_store: BeliefRepository | None = None,
        reversibility_store: BeliefRepository | None = None,
        goals_store: BeliefRepository | None = None,
    ) -> None:
        self.nervous_system = nervous_system or NervousSystem()
        self.beliefs: BeliefRepository = beliefs or InMemoryBeliefStore()
        self.episodes: EpisodeRepository = episodes or InMemoryEpisodeStore()
        self.companion = CompanionModel(companion_store or InMemoryBeliefStore())
        self.actions: BeliefRepository = actions_store or InMemoryBeliefStore()
        self._reversibility: BeliefRepository = (
            reversibility_store or InMemoryBeliefStore()
        )
        self._goals: BeliefRepository = goals_store or InMemoryBeliefStore()
        self._trace = EpisodeTrace()
        self.nervous_system.subscribe(CognitiveEvent, self._trace.handle)
        self._executive = ExecutiveController(
            self.nervous_system, self.beliefs, self.episodes, self.companion
        )

    @classmethod
    def persistent(cls, directory: str | Path) -> Jarvis:
        """A Jarvis whose whole memory lives on disk under one directory.

        Wires every store -- beliefs, episodes, companion model, action learning,
        reversibility and goal reachability -- to files under ``directory``, so a
        single call gives full continuity across restarts (Vision §3, §21).
        Nothing new is persisted; this is composition over the existing JSON stores.
        """
        base = Path(directory)
        return cls(
            beliefs=JsonBeliefStore(base / "beliefs.json"),
            episodes=JsonEpisodeStore(base / "episodes.json"),
            companion_store=JsonBeliefStore(base / "companion.json"),
            actions_store=JsonBeliefStore(base / "actions.json"),
            reversibility_store=JsonBeliefStore(base / "reversibility.json"),
            goals_store=JsonBeliefStore(base / "goals.json"),
        )

    def think(
        self,
        trigger: str,
        evidence: Iterable[Evidence] = (),
        goal: Goal | None = None,
    ) -> CognitiveEpisode:
        """Run a cognitive episode for ``trigger``, grounded in ``evidence``.

        An optional ``goal`` names what the episode is *toward* (Vision §12, §26).
        With no evidence the episode completes with an honest "insufficient
        evidence" conclusion rather than a fabricated answer (Vision §37).
        """
        episode = CognitiveEpisode(trigger=trigger, goal=goal)
        return self._executive.run(episode, evidence)

    def observe_self(self) -> Belief | None:
        """Look back over past episodes and form a belief about Jarvis's own
        tendencies (Vision §6, §31), or None if there is too little history.

        The self-belief is grounded in the episode history and revisable like any
        other belief -- it is not a fixed personality trait.
        """
        return observe_evidence_habit(self.episodes.history())

    def observe_overconfidence(self) -> Belief | None:
        """A belief about whether Jarvis concludes confidently on thin evidence
        (Vision §6, §11), or None if there is too little grounded history.
        """
        return observe_overconfidence(self.episodes.history())

    def observe_prediction_accuracy(self) -> Belief | None:
        """A belief about whether Jarvis mispredicts its actions' outcomes
        (Vision §31), or None if it has judged too few kinds of action.
        """
        return observe_prediction_accuracy(self.actions.all_beliefs())

    def recurring_goals(self) -> tuple[tuple[str, int], ...]:
        """The goals Jarvis keeps returning to, from its episodic memory
        (Vision §26, §31), as ``(goal, count)`` pairs ordered by descending count.

        A plain count over remembered purposes -- not a belief, not a plan. It
        names what Jarvis has come back to often enough to be a pattern, saying
        nothing about whether pursuing it is wise. Empty when nothing recurs.
        """
        return recurring_goals(self.episodes.history())

    def reflection_effort(self, goal_statement: str) -> int:
        """How many times Jarvis has wondered about this goal on its own initiative
        (Vision §26, §31): the count of self-directed episodes recorded toward it.

        The mirror of the companion-side :meth:`recurring_goals`. It measures
        effort, not progress -- a high count with low reachability is honest.
        """
        return reflection_effort(self.episodes.history(), goal_statement)

    def self_beliefs(self) -> tuple[Belief, ...]:
        """Every self-tendency Jarvis currently holds about its own cognition
        (Vision §6): the ones it has enough history to judge.
        """
        candidates = (
            self.observe_self(),
            self.observe_overconfidence(),
            self.observe_prediction_accuracy(),
        )
        return tuple(belief for belief in candidates if belief is not None)

    def introspect(self) -> str:
        """A plain-language account of who Jarvis is, assembled from real state.

        Personality emerges from the actual state, not a prompt (Vision §29): the
        self-tendencies it has noticed (narrated), what it believes about its
        companion, and an honest note about how little it may still know
        (Vision §30, §40). Every line traces to a real belief -- nothing invented.
        """
        lines = ["This is what I currently understand about myself and my companion."]

        tendencies = [
            belief for belief in self.self_beliefs() if belief.confidence.value > 0.0
        ]
        if tendencies:
            lines.append("About myself:")
            for belief in sorted(
                tendencies, key=lambda b: b.confidence.value, reverse=True
            ):
                lines.append("  - " + belief.explain().narrate())
        else:
            lines.append(
                "About myself: I have not yet noticed any consistent tendencies."
            )

        companion = self.companion.summarise()
        if companion:
            lines.append("About my companion:")
            lines.extend("  - " + line for line in companion)
        else:
            lines.append("About my companion: I do not yet know much about them.")

        recurring = self.recurring_goals()
        if recurring:
            lines.append("What I keep returning to:")
            for goal, count in recurring:
                lines.append(f"  - {goal} ({count} times){self._reachability_note(goal)}")

        episodes = len(self.episodes.history())
        lines.append(
            f"This rests on {episodes} past episode(s); everything here is "
            "provisional and open to revision."
        )
        return "\n".join(lines)

    def state_summary(self) -> StateSummary:
        """A compact, immutable snapshot of everything Jarvis currently holds.

        Assembled from the existing read surfaces (episodes, self-model, companion
        model, action learning); every field traces to real state (Vision §21).
        """
        return StateSummary(
            episode_count=len(self.episodes.history()),
            self_tendencies=tuple(
                (belief.statement, belief.confidence.value)
                for belief in self.self_beliefs()
                if belief.confidence.value > 0.0
            ),
            companion_traits=tuple(
                (belief.statement, belief.confidence.value)
                for belief in self.companion.beliefs()
            ),
            learned_actions=tuple(
                self._summarise_action(belief.statement, belief.confidence.value)
                for belief in self.actions.all_beliefs()
            ),
            recurring_goals=self.recurring_goals(),
        )

    def _summarise_action(self, statement: str, confidence: float) -> LearnedAction:
        description = self._action_description(statement)
        return LearnedAction(
            description=description,
            confidence=confidence,
            stance=self.recommend_action_by_description(description).stance,
        )

    def feel_curious(self) -> CuriosityImpulse | None:
        """Decide whether any known self-tendency is worth investigating (Vision §16).

        Considers Jarvis's whole self-model and raises an impulse for the most
        confident weakness worth acting on -- a recommendation, not an action, or
        None if nothing is confident enough (Vision §28).
        """
        by_confidence = sorted(
            self.self_beliefs(), key=lambda belief: belief.confidence.value, reverse=True
        )
        for belief in by_confidence:
            impulse = wonder(belief)
            if impulse is not None:
                return impulse

        # A contested belief about the companion is a valuable unknown to reduce
        # (Vision §16, §18): the tension itself warrants curiosity, whatever the
        # exact confidence -- a balanced belief is the most worth resolving.
        for belief in self.companion.beliefs():
            explanation = belief.explain()
            if explanation.supporting and explanation.contradicting:
                return CuriosityImpulse(
                    trigger=f"Find out whether my companion really: {belief.statement}",
                    rationale=(
                        f'my belief that my companion "{belief.statement}" is contested'
                    ),
                    prompted_by_belief_id=belief.id,
                )

        # A goal Jarvis keeps returning to is worth turning inward on (Vision §26,
        # §31): once self-reliability and companion tension are quiet, the pattern
        # in its own purposes becomes the most interesting unknown. Prompted by a
        # pattern in memory, not a single belief, so no belief id.
        recurring = self.recurring_goals()
        if recurring:
            # Sharpest tension first: a goal it keeps returning to yet has learned
            # it keeps *failing* to reach is more worth wondering about than one it
            # already knows it can reach. `recurring` is ordered by count, so the
            # first unreached one is also the most recurrent among the unreached.
            for goal, count in recurring:
                belief = self.belief_about_goal(goal)
                if belief is not None and belief.confidence.value < 0.5:
                    return CuriosityImpulse(
                        trigger=f"Why do I keep returning to {goal} without reaching it?",
                        rationale=(
                            f'I have pursued the goal "{goal}" {count} times '
                            "without reaching it"
                        ),
                        goal=goal,
                    )
            goal, count = recurring[0]
            return CuriosityImpulse(
                trigger=f"Why do I keep returning to: {goal}?",
                rationale=f'I have pursued the goal "{goal}" {count} times',
                goal=goal,
            )
        return None

    def pursue(self, impulse: CuriosityImpulse) -> CognitiveEpisode:
        """Run a self-triggered episode for a curiosity impulse (Vision §16, §31).

        This is the first episode Jarvis initiates on its own rather than in
        response to the companion; it is marked with a CURIOSITY origin. When the
        impulse concerns a goal, the episode is recorded *toward* that goal (Vision
        §26), so wondering about a stuck goal leaves a trace on the goal itself --
        this records the reflection, not that the goal was reached.
        """
        goal = Goal(statement=impulse.goal) if impulse.goal is not None else None
        episode = CognitiveEpisode(
            trigger=impulse.trigger, origin=TriggerOrigin.CURIOSITY, goal=goal
        )
        return self._executive.run(episode)

    def consider(
        self, observation: str, options: Mapping[str, Sequence[Evidence]]
    ) -> Deliberation:
        """Weigh competing explanations for ``observation`` (Vision §17).

        ``options`` maps each candidate explanation to the evidence bearing on it.
        Runs as a first-class deliberation episode (recorded and traceable) and
        returns the ranking plus the leading explanation -- or, when the top two
        are tied, no leader and a request for evidence that would decide.
        """
        return self._executive.deliberate(observation, options)

    def trace_of(self, episode: CognitiveEpisode) -> tuple[CognitiveEvent, ...]:
        """The ordered cognitive events of ``episode`` -- its decision provenance
        (Vision §26): started, the evidence and belief changes, then completed.
        """
        return self._trace.for_correlation(episode.id)

    def trace(self, correlation_id: str) -> tuple[CognitiveEvent, ...]:
        """The ordered cognitive events of a process by correlation id -- e.g. a
        deliberation's ``episode_id`` (Vision §26).
        """
        return self._trace.for_correlation(correlation_id)

    def act(
        self,
        description: str,
        expected: str,
        *,
        confidence: Confidence | None = None,
        reversible: bool = True,
    ) -> Action:
        """Declare an intention to act, with its expected outcome (Vision §27).

        This only *records* the intention -- it performs nothing in the world.
        Close the loop later with :meth:`record_outcome`.
        """
        return Action(
            description=description,
            expected=expected,
            confidence=confidence or Confidence(0.5),
            reversible=reversible,
        )

    def record_outcome(
        self, action: Action, actual: str, met_expectation: bool
    ) -> Belief:
        """Record what actually happened and learn from expected-vs-actual (Vision §20).

        The outcome becomes evidence for a belief about actions of this kind, so
        repeated matches build confidence and repeated mismatches erode it.
        """
        statement = self._action_statement(action.description)
        belief = self.actions.get_by_statement(statement) or Belief(statement=statement)
        belief.add_evidence(
            Evidence(
                content=(
                    f"acted '{action.description}': expected '{action.expected}', "
                    f"got '{actual}'"
                ),
                source=EvidenceSource.ACTION_OUTCOME,
                weight=Confidence(1.0),
                supports=met_expectation,
            )
        )
        self.actions.save(belief)
        self._remember_reversibility(action)
        for event in belief.pull_events():
            self.nervous_system.publish(event)
        self.nervous_system.publish(
            ActionOutcomeRecorded(
                action_id=action.id,
                description=action.description,
                met_expectation=met_expectation,
            )
        )
        self.nervous_system.dispatch()
        return belief

    def belief_about_action(self, description: str) -> Belief | None:
        """What Jarvis believes about how actions of this kind turn out."""
        return self.actions.get_by_statement(self._action_statement(description))

    def mark_goal_reached(self, goal: Goal, reached: bool = True) -> Belief:
        """Record that a goal was (or was not) reached, and learn from it (Vision §26, §27).

        The companion asserts the outcome -- Jarvis does not evaluate the goal's
        ``success_criterion`` itself yet. The outcome becomes evidence for a belief
        that goals of this kind are *reachable*, so repeated successes build
        confidence and repeated failures erode it (derived, revisable, exactly like
        action-outcome learning). Reaching it also supplies the criterion, if any,
        as context.
        """
        statement = self._goal_statement(goal.statement)
        belief = self._goals.get_by_statement(statement) or Belief(statement=statement)
        outcome = "reached" if reached else "not reached"
        belief.add_evidence(
            Evidence(
                content=f"goal '{goal.statement}' was {outcome}",
                source=EvidenceSource.ACTION_OUTCOME,
                weight=Confidence(1.0),
                supports=reached,
                context=goal.success_criterion,
            )
        )
        self._goals.save(belief)
        for event in belief.pull_events():
            self.nervous_system.publish(event)
        self.nervous_system.dispatch()
        return belief

    def belief_about_goal(self, goal: Goal | str) -> Belief | None:
        """What Jarvis has learned about whether a goal of this kind is reachable,
        or None if it has never been told an outcome for it (Vision §26).
        """
        statement = goal.statement if isinstance(goal, Goal) else goal
        return self._goals.get_by_statement(self._goal_statement(statement))

    @staticmethod
    def _goal_statement(goal_statement: str) -> str:
        return f"The goal '{goal_statement}' is reachable"

    def _reachability_note(self, goal_statement: str) -> str:
        """A truthful annotation of what Jarvis has learned about reaching a goal.

        Empty when no outcome is known yet; otherwise it reports learned
        reachability from the derived confidence -- never asserting more than the
        evidence supports (mirrors the grounded threshold, D14).
        """
        belief = self.belief_about_goal(goal_statement)
        if belief is None:
            return ""
        confidence = belief.confidence.value
        if confidence >= 0.5:
            return f" — I have learned I can reach this (confidence {confidence:.2f})"
        note = f" — I have not reliably reached this yet (confidence {confidence:.2f})"
        effort = self.reflection_effort(goal_statement)
        if effort > 0:
            times = "time" if effort == 1 else "times"
            note += f", and have turned it over {effort} {times}"
        return note

    def recommend_action_by_description(self, description: str) -> ActionRecommendation:
        """Recommend a stance for a *remembered* kind of action (Vision §28).

        Unlike :meth:`recommend_action`, this needs no live `Action`: it reads
        both the learned outcome belief and the learned reversibility belief, so
        the stance survives a restart. Reversibility unknown is treated
        conservatively (not reversible → ask first).
        """
        outcome = self.belief_about_action(description)
        reversible = self._believed_reversible(description)
        return recommend_stance(outcome, reversible=reversible)

    def _remember_reversibility(self, action: Action) -> None:
        statement = self._reversibility_statement(action.description)
        belief = self._reversibility.get_by_statement(statement) or Belief(
            statement=statement
        )
        manner = "reversibly" if action.reversible else "irreversibly"
        belief.add_evidence(
            Evidence(
                content=f"acted '{action.description}' ({manner})",
                source=EvidenceSource.ACTION_OUTCOME,
                weight=Confidence(1.0),
                supports=action.reversible,
            )
        )
        belief.pull_events()  # bookkeeping belief -- its events are not dispatched
        self._reversibility.save(belief)

    def _believed_reversible(self, description: str) -> bool:
        belief = self._reversibility.get_by_statement(
            self._reversibility_statement(description)
        )
        return belief is not None and belief.confidence.value >= 0.5

    @staticmethod
    def _reversibility_statement(description: str) -> str:
        return f"The action '{description}' is reversible"

    def recommend_action(self, action: Action) -> ActionRecommendation:
        """Recommend a stance toward ``action`` from experience (Vision §28).

        Suggests only a confidently-learned, reversible action; asks first when
        unproven or irreversible; withholds one the record contradicts. It only
        recommends -- it performs nothing (autonomy is earned).
        """
        belief = self.belief_about_action(action.description)
        return recommend_stance(belief, reversible=action.reversible)

    @staticmethod
    def _action_statement(description: str) -> str:
        return f"My predictions about the action '{description}' hold"

    @staticmethod
    def _action_description(statement: str) -> str:
        # Exact inverse of _action_statement (a controlled template, not free text).
        return statement.removeprefix(
            "My predictions about the action '"
        ).removesuffix("' hold")

    def observe_companion(self, trait: str, evidence: Evidence) -> Belief:
        """Record an observation about the companion and evolve Jarvis's model of
        them (Vision §5). Returns the (revisable) belief; its events flow through
        the nervous system.
        """
        belief, _ = self._record_companion(trait, evidence)
        return belief

    def acknowledge_companion(self, trait: str, evidence: Evidence) -> str:
        """Record an observation and acknowledge it in conversation (Vision §18).

        When the observation contradicts a belief Jarvis actually held, it says
        so plainly -- the person has contradicted its model, and it holds the
        belief less firmly now. A first or consistent observation is just noted.
        """
        _, contradicted = self._record_companion(trait, evidence)
        if contradicted:
            return (
                f'You have contradicted what I believed about "{trait}". '
                "I may be wrong, so I am holding it less firmly now."
            )
        return f'Noted about "{trait}".'

    def _record_companion(self, trait: str, evidence: Evidence) -> tuple[Belief, bool]:
        belief = self.companion.observe(trait, evidence)
        events = self.companion.pull_events()
        contradicted = any(isinstance(event, ContradictionDetected) for event in events)
        for event in events:
            self.nervous_system.publish(event)
        self.nervous_system.dispatch()
        return belief, contradicted

    def explain_companion(self, trait: str) -> str:
        """Explain *why* Jarvis believes ``trait`` about its companion (Vision §5, §8).

        Returns the belief's provenance narrated -- the evidence for and against
        it, its confidence, and, when contested, an honest "I may be wrong". If no
        such belief is held yet, says so plainly (Vision §37).
        """
        belief = self.companion.belief_about(trait)
        if belief is None:
            return f'I don\'t hold a view on "{trait}" about my companion yet.'
        return belief.explain().narrate()
