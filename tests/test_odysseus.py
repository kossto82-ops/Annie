"""Behavioural tests for Odysseus -- capability acquisition (Vision §34, §28).

The scout is the discovery stage: it proposes candidate capabilities for a
recognised need, ordered by how well the need's language matches a known
capability template. It only *proposes*; acquiring or rejecting is a deliberate,
separate step, and Jarvis merely remembers which it holds. Need recognition
grounds the need in evidence (a belief confidence is never asserted), and the
evaluator derives a stance (suggest / ask first / withhold) from that evidence.
"""

from __future__ import annotations

from jarvis import Jarvis
from jarvis.domain.enums.capability_stance import CapabilityStance
from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.capability_scout import scout
from jarvis.domain.value_objects.capability_need import CapabilityNeed
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _confident_need_evidence() -> list[Evidence]:
    return [
        Evidence(
            content="I need fresh outside information",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(1.0),
        )
        for _ in range(4)
    ]


def _jarvis_with_confident_web_need() -> Jarvis:
    jarvis = Jarvis()
    jarvis.recognise_need(
        "I want to search the web",
        "I need current outside information",
        evidence=_confident_need_evidence(),
    )
    return jarvis


class TestScout:
    def test_a_web_need_proposes_the_web_capability(self) -> None:
        need = CapabilityNeed(
            statement="I want to search the web for current news",
            rationale="news changes and I need fresh outside information",
        )
        candidates = scout(need)
        assert any(capability.name == "search the web" for capability in candidates)

    def test_candidates_are_proposals_not_acquisitions(self) -> None:
        candidates = scout(
            CapabilityNeed(
                statement="I want to search the web",
                rationale="I need outside information",
            )
        )
        assert candidates
        assert all(c.status is CapabilityStatus.PROPOSED for c in candidates)
        assert all(c.provenance for c in candidates)

    def test_a_need_matching_nothing_yields_an_empty_tuple(self) -> None:
        candidates = scout(
            CapabilityNeed(
                statement="I would like to compose music",
                rationale="to reflect on melodies",
            )
        )
        assert candidates == ()

    def test_candidates_are_ordered_by_matching_strength(self) -> None:
        need = CapabilityNeed(
            statement="I want to search the web and reason with an LLM",
            rationale="and read external documents",
        )
        names = [c.name for c in scout(need)]
        assert names[0] == "search the web"  # strongest cue match first


class TestJarvisOdysseus:
    def test_scouting_does_not_store_by_default(self) -> None:
        jarvis = Jarvis()
        jarvis.need_capability("search the web", "for current news")
        assert jarvis.capabilities() == ()

    def test_remembered_capability_can_be_acquired(self) -> None:
        jarvis = Jarvis()
        candidate = jarvis.need_capability("search the web", "for news")[0]
        jarvis.remember_capability(candidate)
        assert jarvis.capabilities()[0].status is CapabilityStatus.PROPOSED

        acquired = jarvis.acquire_capability("search the web")
        assert acquired is not None
        assert acquired.status is CapabilityStatus.ACQUIRED
        assert jarvis.capabilities()[0].status is CapabilityStatus.ACQUIRED

    def test_acquiring_an_unknown_name_returns_none(self) -> None:
        assert Jarvis().acquire_capability("does not exist") is None

    def test_a_rejected_capability_is_not_reacquired(self) -> None:
        jarvis = Jarvis()
        candidate = jarvis.need_capability("search the web", "for news")[0]
        jarvis.remember_capability(candidate)
        rejected = jarvis.reject_capability("search the web")
        assert rejected is not None
        assert rejected.status is CapabilityStatus.REJECTED
        assert jarvis.capabilities()[0].status is CapabilityStatus.REJECTED


class TestRecogniseNeed:
    def test_recognising_a_need_records_an_evidence_grounded_belief(self) -> None:
        jarvis = Jarvis()
        jarvis.recognise_need(
            "search the web for current news",
            "news changes and I need fresh outside information",
            evidence=_confident_need_evidence(),
        )
        needs = jarvis.capability_needs()
        assert len(needs) == 1
        statement, confidence = needs[0]
        assert statement == (
            "I need the ability to: search the web for current news"
        )
        assert confidence.value >= 0.5  # derived from evidence, never asserted

    def test_recognising_a_need_persists_proposals(self) -> None:
        jarvis = Jarvis()
        candidates = jarvis.recognise_need(
            "search the web for news",
            "for current information",
            evidence=_confident_need_evidence(),
        )
        assert candidates
        assert any(c.name == "search the web" for c in jarvis.capabilities())

    def test_a_repeated_need_is_recognised_not_reproposed(self) -> None:
        jarvis = Jarvis()
        first = jarvis.recognise_need(
            "search the web for news",
            "for current information",
            evidence=_confident_need_evidence(),
        )
        second = jarvis.recognise_need(
            "search the web for news",
            "for current information",
            evidence=_confident_need_evidence(),
        )
        assert set(c.name for c in first) == set(c.name for c in second)
        assert len(jarvis.capability_needs()) == 1

    def test_a_weak_need_records_but_never_asserts_confidence(self) -> None:
        jarvis = Jarvis()
        jarvis.recognise_need(
            "compose music",
            "to reflect on melodies",
            evidence=[
                Evidence(
                    content="maybe music matters",
                    source=EvidenceSource.USER_STATEMENT,
                    weight=Confidence(0.2),
                )
            ],
        )
        needs = jarvis.capability_needs()
        assert len(needs) == 1
        assert needs[0][1].value < 0.5  # honest: weakly grounded


class TestCapabilityStance:
    def test_no_need_means_ask_first(self) -> None:
        assert Jarvis().capability_stance("search the web") is CapabilityStance.ASK_FIRST

    def test_a_confident_unmet_need_suggests_acquisition(self) -> None:
        jarvis = _jarvis_with_confident_web_need()
        recommendation = jarvis.recommend_capability("search the web")
        assert recommendation.stance is CapabilityStance.SUGGEST
        assert recommendation.confidence.value >= 0.5
        assert recommendation.rationale
        assert jarvis.capability_stance("search the web") is CapabilityStance.SUGGEST

    def test_an_acquired_capability_is_ask_first(self) -> None:
        jarvis = _jarvis_with_confident_web_need()
        jarvis.acquire_capability("search the web")
        assert jarvis.capability_stance("search the web") is CapabilityStance.ASK_FIRST

    def test_a_contradicted_need_withholds(self) -> None:
        jarvis = Jarvis()
        jarvis.recognise_need(
            "search the web",
            "for fresh information",
            evidence=[
                Evidence(
                    content="outside information would help",
                    source=EvidenceSource.USER_STATEMENT,
                    weight=Confidence(0.9),
                    supports=False,
                ),
            ],
        )
        assert jarvis.capability_stance("search the web") is CapabilityStance.WITHHOLD


class TestCuriosityAcquires:
    def test_a_confident_unmet_need_raises_an_acquisition_impulse(self) -> None:
        jarvis = _jarvis_with_confident_web_need()
        impulse = jarvis.feel_curious()
        assert impulse is not None
        assert impulse.capability_to_acquire == "search the web"
        assert "Acquire" in impulse.trigger

    def test_pursuing_the_impulse_acquires_the_capability(self) -> None:
        jarvis = _jarvis_with_confident_web_need()
        impulse = jarvis.feel_curious()
        assert impulse is not None
        episode = jarvis.pursue(impulse)
        assert episode.state.value == "completed"
        assert jarvis.capabilities()[0].status is CapabilityStatus.ACQUIRED


class TestCapabilitiesInState:
    def test_state_summary_exposes_capabilities_and_needs(self) -> None:
        jarvis = _jarvis_with_confident_web_need()
        jarvis.acquire_capability("search the web")
        summary = jarvis.state_summary()
        assert ("search the web", "acquired") in summary.capabilities
        assert any("search the web" in statement for statement, _ in summary.capability_needs)
