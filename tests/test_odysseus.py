"""Behavioural tests for Odysseus -- capability acquisition (Vision §34, §28).

The scout is the discovery stage: it proposes candidate capabilities for a
recognised need, ordered by how well the need's language matches a known
capability template. It only *proposes*; acquiring or rejecting is a deliberate,
separate step, and Jarvis merely remembers which it holds.
"""

from __future__ import annotations

from jarvis import Jarvis
from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.services.capability_scout import scout
from jarvis.domain.value_objects.capability_need import CapabilityNeed


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
