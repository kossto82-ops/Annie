"""Fase 3: the deliberate-consult seam (KnowledgeSource, Vision §37, §38).

When an episode cannot conclude from what Jarvis knows, remembers, or reasons,
it may deliberately ask a KnowledgeSource to gather candidate evidence about the
trigger. The seam only *gathers* (D6);
- it is opt-in: no seam wired means the episode never consults (D8);
- it is guarded: a grounded belief or a strong memory suppresses the consult;
- a ``None`` consult is an honest "nothing gathered" -- the episode continues
  exactly as before;
- the episode records *which* edge was consulted, for provenance (Vision §26).
"""

from __future__ import annotations

import pytest

from jarvis import Jarvis
from jarvis.domain.aggregates.cognitive_episode import (
    CognitiveEpisode,
    InvalidStateTransition,
)
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.knowledge_source import KnowledgeSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


class _Source:
    kind = "test source"

    def __init__(self, evidence: Evidence | None = None) -> None:
        self.evidence = evidence
        self.calls: list[str] = []

    def gather(self, question: str) -> Evidence | None:
        self.calls.append(question)
        return self.evidence


def _sky_evidence() -> Evidence:
    return Evidence(
        content="Retrieved sources describe the sky as blue.",
        source=EvidenceSource.EXTERNAL_SOURCE,
        weight=Confidence(0.4),
    )


class TestTheSeamIsAProtocol:
    def test_a_wired_source_satisfies_the_protocol(self) -> None:
        assert isinstance(_Source(), KnowledgeSource)

    def test_no_seam_means_no_consult(self) -> None:
        jarvis = Jarvis()
        assert jarvis.knowledge_source is None
        episode = jarvis.think("is the sky blue?")
        assert episode.consulted is None
        assert episode.working_belief is not None
        assert episode.working_belief.evidence == ()


class TestEpisodeProvenance:
    def test_consulted_defaults_to_none(self) -> None:
        assert CognitiveEpisode(trigger="x").consulted is None

    def test_record_consult_records_the_edge_kind(self) -> None:
        episode = CognitiveEpisode(trigger="x")
        episode.record_consult("deep research")
        assert episode.consulted == "deep research"

    def test_recording_a_consult_into_a_completed_episode_is_rejected(self) -> None:
        episode = CognitiveEpisode(trigger="x")
        episode.begin_reasoning()
        episode.begin_reflecting()
        episode.begin_deciding()
        episode.complete("done")
        with pytest.raises(InvalidStateTransition):
            episode.record_consult("deep research")


class TestTheDeliberateConsult:
    def test_ungrounded_question_consults_and_observes_candidate_evidence(self) -> None:
        source = _Source(_sky_evidence())
        jarvis = Jarvis(knowledge_source=source)
        episode = jarvis.think("is the sky blue?")
        assert source.calls == ["is the sky blue?"]
        assert episode.consulted == "test source"
        belief = episode.working_belief
        assert belief is not None and len(belief.evidence) == 1
        assert belief.evidence[0].source is EvidenceSource.EXTERNAL_SOURCE
        # One external piece grounds the belief only thinly: positive but tentative.
        assert 0.0 < belief.confidence.value < 0.5
        assert "Tentative" in episode.result or "insufficient" in (episode.result or "")

    def test_a_none_consult_is_an_honest_empty_consult(self) -> None:
        source = _Source(None)
        jarvis = Jarvis(knowledge_source=source)
        episode = jarvis.think("is the sky blue?")
        assert source.calls == ["is the sky blue?"]
        assert episode.consulted == "test source"  # the attempt is provable
        assert episode.working_belief is not None
        assert episode.working_belief.evidence == ()
        assert "Insufficient evidence" in (episode.result or "")

    def test_a_supplied_seam_swaps_at_runtime(self) -> None:
        source = _Source(_sky_evidence())
        jarvis = Jarvis()
        jarvis.set_knowledge_source(source)
        assert jarvis.knowledge_source is source
        episode = jarvis.think("is the sky blue?")
        assert episode.consulted == "test source"
        jarvis.set_knowledge_source(None)
        episode = jarvis.think("is the sky blue?")
        assert episode.consulted is None


class TestTheConsultIsDeliberate:
    def test_a_grounded_belief_suppresses_the_consult(self) -> None:
        source = _Source(_sky_evidence())
        jarvis = Jarvis(knowledge_source=source)
        episode = jarvis.perceive("the plan is definitely ready")
        assert source.calls == []
        assert episode.consulted is None
        assert episode.working_belief is not None
        assert episode.working_belief.confidence.value >= 0.5

    def test_a_strong_memory_suppresses_the_consult(self) -> None:
        source = _Source(_sky_evidence())
        jarvis = Jarvis(knowledge_source=source, enable_recall=True)
        jarvis.observe_companion(
            "is named Raúl",
            Evidence(
                content="me llamo Raúl",
                source=EvidenceSource.USER_STATEMENT,
                weight=Confidence(0.9),
            ),
        )
        episode = jarvis.perceive("sabes mi nombre?", trigger="sabes mi nombre?")
        assert source.calls == []
        assert episode.consulted is None