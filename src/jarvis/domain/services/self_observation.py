"""Jarvis observing its own cognition (Vision §6, §31).

This is the first fragment of a model of *itself*. It must not be fake
personality text -- it emerges from measurable history. It reuses the ordinary
epistemology: each past episode is a piece of *evidence about Jarvis*, and the
self-observation is just a `Belief` whose confidence is derived from that
evidence. So "I tend to X" is provisional and revisable, exactly like any other
belief.

The single tendency measured here: does Jarvis habitually conclude without
enough evidence? Each episode that ended ungrounded supports that belief; each
grounded episode contradicts it. More tendencies can be added the same way.

Second-order reflection (Phase 5) adds meta-observations about reasoning
strategies, retrieval quality, and attention patterns via the
``jarvis.domain.services.meta_observation`` module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from jarvis.domain.entities.belief import LOW_STABILITY_THRESHOLD, Belief
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.evidence_weighting import EvidenceWeightingPolicy
from jarvis.domain.value_objects.cognitive_knobs import CognitiveKnobs
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence

# The grounded threshold is owned by ``CognitiveKnobs`` (single source, D14);
# these observers take it as an injectable knob (default = the value above).

# Too few episodes to judge a tendency honestly.
_MINIMUM_HISTORY = 3

_OBSERVATION_WEIGHT = Confidence(1.0)

INSUFFICIENT_EVIDENCE_HABIT = "I tend to conclude without sufficient evidence"
OVERCONFIDENCE_HABIT = "I tend to be overconfident on thin evidence"
POOR_PREDICTION_HABIT = "My predictions about my actions tend to be wrong"


def observe_evidence_habit(
    history: Sequence[EpisodeRecord],
    *,
    knobs: CognitiveKnobs | None = None,
    policy: EvidenceWeightingPolicy | None = None,
) -> Belief | None:
    """Form a belief about whether Jarvis concludes without enough evidence.

    Returns None when there is too little history to judge. Otherwise returns a
    belief about Jarvis, grounded in one piece of evidence per past episode, so
    its confidence reflects how often conclusions were actually ungrounded.
    ``policy`` is the belief's default weighting policy (the root per-belief
    default when Jarvis injects one).
    """
    # Judge only how Jarvis handled the companion's questions. Self-triggered
    # (curiosity) episodes must not inflate the very habit they respond to, and
    # deliberations are a different cognition shape (no single conclusion).
    relevant = [
        r
        for r in history
        if r.origin is TriggerOrigin.COMPANION and r.kind is EpisodeKind.CONCLUSION
    ]
    if len(relevant) < _MINIMUM_HISTORY:
        return None
    grounded = (knobs or CognitiveKnobs()).grounded_confidence

    belief = (
        Belief(statement=INSUFFICIENT_EVIDENCE_HABIT, weighting_policy=policy)
        if policy is not None
        else Belief(statement=INSUFFICIENT_EVIDENCE_HABIT)
    )
    for record in relevant:
        ungrounded = record.conclusion_confidence.value < grounded
        belief.add_evidence(
            Evidence(
                content=(
                    f"episode about '{record.trigger}' concluded at confidence "
                    f"{record.conclusion_confidence.value:.2f}"
                ),
                source=EvidenceSource.SYSTEM_OBSERVATION,
                weight=_OBSERVATION_WEIGHT,
                supports=ungrounded,
                observed_at=record.recorded_at,
            )
        )
    return belief


def observe_overconfidence(
    history: Sequence[EpisodeRecord],
    *,
    knobs: CognitiveKnobs | None = None,
    policy: EvidenceWeightingPolicy | None = None,
) -> Belief | None:
    """Form a belief about whether Jarvis is overconfident on thin evidence.

    Only *grounded* conclusions are candidates -- an ungrounded one is not
    confident at all. Among them, a conclusion reached on temporally narrow
    (low-stability) evidence supports the belief; one resting on well-spread
    evidence contradicts it (Vision §6, §11). Returns None with too little
    grounded history to judge.
    """
    grounded_confidence = (knobs or CognitiveKnobs()).grounded_confidence
    grounded = [
        r
        for r in history
        if r.origin is TriggerOrigin.COMPANION
        and r.kind is EpisodeKind.CONCLUSION
        and r.conclusion_confidence.value >= grounded_confidence
    ]
    if len(grounded) < _MINIMUM_HISTORY:
        return None

    belief = (
        Belief(statement=OVERCONFIDENCE_HABIT, weighting_policy=policy)
        if policy is not None
        else Belief(statement=OVERCONFIDENCE_HABIT)
    )
    for record in grounded:
        overconfident = record.conclusion_stability.value < LOW_STABILITY_THRESHOLD
        belief.add_evidence(
            Evidence(
                content=(
                    f"episode about '{record.trigger}' concluded grounded "
                    f"(confidence {record.conclusion_confidence.value:.2f}) on "
                    f"stability {record.conclusion_stability.value:.2f}"
                ),
                source=EvidenceSource.SYSTEM_OBSERVATION,
                weight=_OBSERVATION_WEIGHT,
                supports=overconfident,
                observed_at=record.recorded_at,
            )
        )
    return belief


def observe_prediction_accuracy(
    action_beliefs: Sequence[Belief],
    *,
    knobs: CognitiveKnobs | None = None,
    policy: EvidenceWeightingPolicy | None = None,
) -> Belief | None:
    """Form a belief about whether Jarvis mispredicts its actions' outcomes.

    Reads the *action-outcome* beliefs (one per action kind, Increment 25). A kind
    whose predictions clearly failed (confidence below grounded, with contradicting
    outcomes) supports the belief; a kind whose predictions held contradicts it.
    Thin, undecided kinds are skipped. Returns None with too few judged kinds.
    This measures predictive reliability (Vision §31 "poor predictions"), a
    distinct tendency from the episode-based ones.
    """
    judged: list[tuple[Belief, bool]] = []
    grounded_confidence = (knobs or CognitiveKnobs()).grounded_confidence
    for action_belief in action_beliefs:
        confidence = action_belief.confidence.value
        if confidence >= grounded_confidence:
            judged.append((action_belief, False))  # predictions held
        elif action_belief.explain().contradicting:
            judged.append((action_belief, True))  # predictions failed
        # else: too thin to judge -> skip

    if len(judged) < _MINIMUM_HISTORY:
        return None

    belief = (
        Belief(statement=POOR_PREDICTION_HABIT, weighting_policy=policy)
        if policy is not None
        else Belief(statement=POOR_PREDICTION_HABIT)
    )
    for action_belief, mispredicted in judged:
        belief.add_evidence(
            Evidence(
                content=(
                    f"{action_belief.statement} -> predictions "
                    f"{'failed' if mispredicted else 'held'} "
                    f"(confidence {action_belief.confidence.value:.2f})"
                ),
                source=EvidenceSource.SYSTEM_OBSERVATION,
                weight=_OBSERVATION_WEIGHT,
                supports=mispredicted,
                observed_at=action_belief.formed_at,
            )
        )
    return belief


# ---------------------------------------------------------------------------
# Adaptation bridge: self-observation → CognitiveKnobs adjustment
# ---------------------------------------------------------------------------

# Maximum single-step adjustment to any confidence threshold.
_ADAPTATION_STEP: float = 0.05

# The baseline default knobs (used as the target for reversal).
_DEFAULT_KNOBS = CognitiveKnobs()


def adapt_knobs_from_self_observation(
    knobs: CognitiveKnobs,
    history: Sequence[EpisodeRecord],
    *,
    policy: EvidenceWeightingPolicy | None = None,
) -> tuple[CognitiveKnobs, str | None]:
    """Evaluate self-observation and return adjusted knobs if warranted.

    When a self-observation belief crosses the learned-habit threshold, the
    relevant knob is adjusted *toward* a more conservative posture. When the
    habit fades, the knob drifts back toward the baseline.

    Returns the (possibly unchanged) knobs and a reason string when an
    adjustment was made, or None when no adjustment was needed.

    Design principles:
    - **Evidence-backed**: adjustment only happens when a self-belief has
      sufficient evidence (>= 3 episodes, confidence >= 0.5).
    - **Bounded**: max ±0.05 per call, knobs stay in [0.1, 0.9].
    - **Reversible**: when the habit fades, knobs return toward baseline.
    - **Inspectable**: the reason string explains what changed and why.
    """
    _HABIT_THRESHOLD = 0.5
    _FLOOR = 0.1
    _CEIL = 0.9

    adjusted = knobs
    reason: str | None = None

    # Evidence habit: "I conclude without enough evidence"
    # -> raise grounded_confidence (need more evidence before concluding)
    evidence_belief = observe_evidence_habit(history, knobs=knobs, policy=policy)
    if (
        evidence_belief is not None
        and evidence_belief.confidence.value >= _HABIT_THRESHOLD
    ):
        current = adjusted.grounded_confidence
        baseline = _DEFAULT_KNOBS.grounded_confidence
        if current < baseline:
            # Drift back toward baseline
            new_val = min(baseline, current + _ADAPTATION_STEP)
        else:
            # Habit detected, raise threshold (more conservative)
            new_val = min(_CEIL, current + _ADAPTATION_STEP)
        if new_val != current:
            adjusted = replace(adjusted, grounded_confidence=new_val)
            reason = (
                f"raised grounded_confidence from {current:.2f} to {new_val:.2f} "
                f"(evidence habit detected, confidence "
                f"{evidence_belief.confidence.value:.2f})"
            )

    # Overconfidence habit: "I am overconfident on thin evidence"
    # -> raise grounded_confidence (stricter bar for "grounded")
    overconfidence_belief = observe_overconfidence(history, knobs=knobs, policy=policy)
    if (
        overconfidence_belief is not None
        and overconfidence_belief.confidence.value >= _HABIT_THRESHOLD
    ):
        current = adjusted.grounded_confidence
        baseline = _DEFAULT_KNOBS.grounded_confidence
        if current < baseline:
            new_val = min(baseline, current + _ADAPTATION_STEP)
        else:
            new_val = min(_CEIL, current + _ADAPTATION_STEP)
        if new_val != current:
            adjusted = replace(adjusted, grounded_confidence=new_val)
            reason = (
                f"raised grounded_confidence from {current:.2f} to {new_val:.2f} "
                f"(overconfidence habit detected, confidence "
                f"{overconfidence_belief.confidence.value:.2f})"
            )

    # When no habit is detected but the threshold was previously raised,
    # drift it back toward baseline (reversibility).
    if reason is None:
        current = adjusted.grounded_confidence
        baseline = _DEFAULT_KNOBS.grounded_confidence
        if current > baseline:
            new_val = max(baseline, current - _ADAPTATION_STEP)
            if new_val != current:
                adjusted = replace(adjusted, grounded_confidence=new_val)
                reason = (
                    f"lowered grounded_confidence from {current:.2f} to {new_val:.2f} "
                    f"(no habit detected, drifting toward baseline)"
                )

    return adjusted, reason
