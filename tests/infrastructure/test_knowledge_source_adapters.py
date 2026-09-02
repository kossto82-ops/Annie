"""Fase 3: the KnowledgeSource adapters over the Odysseus edges (D6, D7, D8).

Each adapter wraps an existing edge -- deep research, blind model comparison --
behind the domain's deliberate-consult Protocol. They gather candidate evidence
and never conclude; a failed or empty edge is an honest ``None`` consult, never a
fabricated claim. Both are opt-in and offline-testable.
"""

from __future__ import annotations

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.knowledge_source import KnowledgeSource
from jarvis.domain.services.model_compare import ModelRun
from jarvis.domain.value_objects.research_report import ResearchReport
from jarvis.domain.value_objects.retrieved_document import RetrievedDocument
from jarvis.infrastructure.knowledge_source import (
    CompareKnowledgeSource,
    ResearchKnowledgeSource,
)


class _Research:
    def __init__(self, report: ResearchReport | None = None, fail: bool = False) -> None:
        self.report = report
        self.fail = fail
        self.asked: list[str] = []

    def deep_research(self, query: str, *, depth: int = 1) -> ResearchReport:
        self.asked.append(query)
        if self.fail:
            raise RuntimeError("instance unreachable")
        if self.report is None:
            return ResearchReport(query=query, summary="", documents=())
        return self.report


class _Compare:
    def __init__(self, runs: tuple[ModelRun, ...] = (), fail: bool = False) -> None:
        self.runs = runs
        self.fail = fail
        self.asked: list[str] = []

    def compare(
        self, prompt: str, *, models: list[str] | None = None
    ) -> tuple[ModelRun, ...]:
        self.asked.append(prompt)
        if self.fail:
            raise RuntimeError("models unreachable")
        return self.runs


def _report() -> ResearchReport:
    return ResearchReport(
        query="is the sky blue?",
        summary="Several sources say the sky is blue because of Rayleigh scattering.",
        documents=(
            RetrievedDocument(
                content="The sky is blue because of Rayleigh scattering.",
                source="web",
                title="Why is the sky blue?",
            ),
            RetrievedDocument(
                content="Scattering of shorter wavelengths dominates.",
                source="web",
                title="Atmospheric optics",
            ),
        ),
    )


class TestResearchAdapter:
    def test_gather_turns_a_report_into_candidate_external_evidence(self) -> None:
        adapter = ResearchKnowledgeSource(_Research(report=_report()))
        evidence = adapter.gather("is the sky blue?")
        assert evidence is not None
        assert evidence.source is EvidenceSource.EXTERNAL_SOURCE
        assert "Why is the sky blue?" in evidence.content
        assert "Rayleigh scattering" in evidence.content
        assert "is the sky blue?" in (evidence.context or "")
        assert evidence.weight.value > 0.0

    def test_gather_with_no_documents_is_honestly_nothing(self) -> None:
        adapter = ResearchKnowledgeSource(_Research(report=ResearchReport(query="q", summary="")))
        assert adapter.gather("q") is None

    def test_gather_never_raises_when_the_edge_fails(self) -> None:
        adapter = ResearchKnowledgeSource(_Research(fail=True))
        assert adapter.gather("q") is None

    def test_the_adapter_satisfies_the_protocol(self) -> None:
        assert isinstance(ResearchKnowledgeSource(_Research()), KnowledgeSource)
        assert ResearchKnowledgeSource(_Research()).kind == "deep research"

    def test_wired_through_jarvis_end_to_end(self) -> None:
        research = _Research(report=_report())
        jarvis = Jarvis(knowledge_source=ResearchKnowledgeSource(research))
        episode = jarvis.think("is the sky blue?")
        assert research.asked == ["is the sky blue?"]
        assert episode.consulted == "deep research"
        belief = episode.working_belief
        assert belief is not None and len(belief.evidence) == 1
        assert belief.evidence[0].source is EvidenceSource.EXTERNAL_SOURCE


class TestCompareAdapter:
    def test_gather_turns_blind_replies_into_weakest_inference_evidence(self) -> None:
        adapter = CompareKnowledgeSource(
            _Compare(runs=(ModelRun(model="m1", response="blue, mostly"),))
        )
        evidence = adapter.gather("is the sky blue?")
        assert evidence is not None
        assert evidence.source is EvidenceSource.INFERENCE
        assert "m1" in evidence.content
        assert "blue, mostly" in evidence.content
        assert "is the sky blue?" in evidence.content

    def test_gather_with_no_replies_is_honestly_nothing(self) -> None:
        adapter = CompareKnowledgeSource(_Compare(runs=()))
        assert adapter.gather("q") is None

    def test_gather_never_raises_when_a_model_fails(self) -> None:
        adapter = CompareKnowledgeSource(_Compare(fail=True))
        assert adapter.gather("q") is None

    def test_the_adapter_satisfies_the_protocol(self) -> None:
        assert isinstance(CompareKnowledgeSource(_Compare()), KnowledgeSource)
        assert CompareKnowledgeSource(_Compare()).kind == "model comparison"
        # A candidate reply must stay weaker than a real observation.
        adapter = CompareKnowledgeSource(
            _Compare(runs=(ModelRun(model="m", response="yes"),))
        )
        evidence = adapter.gather("q")
        assert evidence is not None
        assert evidence.source is EvidenceSource.INFERENCE