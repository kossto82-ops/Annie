"""KnowledgeSource adapters over the Odysseus edges (Vision §38; D6, D7).

These wrap an existing edge -- deep research, blind model comparison -- behind
the domain's deliberate-consult Protocol, so the *core* can choose to consult
them the same way it chooses to recall or reason, without knowing the provider.
They gather only: each returns one piece of candidate evidence (or ``None`` when
the edge has nothing honest to offer) and never writes to memory (D6).

Both are opt-in, offline-testable, and provider-swappable (D8, D11): a bare
Jarvis wires neither, so the offline core is unchanged.
"""

from __future__ import annotations

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.retrieval.research_source import ResearchSource
from jarvis.domain.services.model_compare import ModelComparator
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _snip(text: str, limit: int = 220) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


class ResearchKnowledgeSource:
    """Turns one deep-research run into candidate evidence about the question.

    A report that found nothing is *not* support for anything, and a failed run
    is an honest empty consult -- both return ``None``, never a claim (D6, D8).
    """

    def __init__(self, research: ResearchSource) -> None:
        self._research = research

    @property
    def kind(self) -> str:
        return "deep research"

    def gather(self, question: str) -> Evidence | None:
        try:
            report = self._research.deep_research(question, depth=1)
        except Exception:
            return None  # the edge failed -- an empty consult, never a claim
        if not report.documents:
            return None  # nothing was found; nothing is not evidence
        sources = "; ".join(
            doc.title for doc in report.documents[:3] if doc.title and doc.title.strip()
        )
        content = (
            f"Found {len(report.documents)} cited source(s)"
            f"{(f' (incl. {_snip(sources, 140)})' if sources else '')}"
        )
        if report.summary and report.summary.strip():
            content = f"{content} -- {_snip(report.summary)}"
        return Evidence(
            content=content,
            # Web-derived by an edge provider, unverified by Jarvis's own senses.
            source=EvidenceSource.EXTERNAL_SOURCE,
            weight=Confidence(0.4),
            context=f"gathered deliberately (deep research) about: {question}",
        )


class CompareKnowledgeSource:
    """Turns blind model comparison into the *weakest* candidate evidence.

    Models' replies are candidate text and nothing more: they are tagged
    INFERENCE so a reply can never outweigh a real observation, and blind
    provenance (which model said what) is kept so the core can attribute it
    (Vision §33, D6).
    """

    def __init__(self, comparator: ModelComparator) -> None:
        self._comparator = comparator

    @property
    def kind(self) -> str:
        return "model comparison"

    def gather(self, question: str) -> Evidence | None:
        try:
            runs = self._comparator.compare(question)
        except Exception:
            return None
        if not runs:
            return None
        replies = "; ".join(f"{run.model}: {_snip(run.response)}" for run in runs)
        return Evidence(
            content=f"Blind replies to '{_snip(question, 80)}': {replies}",
            source=EvidenceSource.INFERENCE,
            weight=Confidence(0.5),
            context="gathered deliberately (model comparison) as candidate text",
        )