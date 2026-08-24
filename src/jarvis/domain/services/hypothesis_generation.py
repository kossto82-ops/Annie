"""Brewing a hypothesis from reflection (Vision §17, §31).

Cycle stage three. Reflect (Increment 75) notices that one observation is
load-bearing -- several beliefs rest on it. Hypothesise turns that *noticing* into
a *proposed explanation*: perhaps that observation is a common cause of those
beliefs, rather than their sharing it by coincidence. The two candidates form a
`HypothesisSet` (§17), so nothing collapses prematurely; each belief resting on
the observation is evidence for the common-cause reading, so its confidence is
derived, not asserted. What confirms or refutes it is the input to Challenge.

Autonomous: unlike `consider()`, no companion triggers this -- it brews from
Jarvis's own reflection over what it already believes.
"""

from __future__ import annotations

from collections.abc import Sequence

from jarvis.domain.aggregates.hypothesis_set import HypothesisSet
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.reflection import Reflection


def generate_hypotheses(reflections: Sequence[Reflection]) -> HypothesisSet | None:
    """Form competing explanations for the most load-bearing observation, or None
    when there is nothing load-bearing to explain.

    The common-cause hypothesis is seeded with one piece of evidence per belief
    resting on the observation, so it grows more confident the more it explains;
    the independence (null) hypothesis stands beside it with none.
    """
    if not reflections:
        return None
    finding = reflections[0]
    hypotheses = HypothesisSet(observation=finding.observation)
    common_cause = hypotheses.propose(
        f'The observation "{finding.observation}" is a common cause '
        f"of {finding.load} of my beliefs"
    )
    hypotheses.propose(
        f'Those {finding.load} beliefs are independent — '
        f'"{finding.observation}" grounds them only by coincidence'
    )
    for statement in finding.beliefs:
        hypotheses.add_evidence(
            common_cause.id,
            Evidence(
                content=f"a belief rests on it: {statement}",
                source=EvidenceSource.SYSTEM_OBSERVATION,
                weight=Confidence(1.0),
            ),
        )
    return hypotheses
