"""Behavioural tests for Odysseus -- capability acquisition (Vision §34, §28).

The scout is the discovery stage: it proposes candidate capabilities for a
recognised need, ordered by how well the need's language matches a known
capability template. It only *proposes*; acquiring or rejecting is a deliberate,
separate step, and Jarvis merely remembers which it holds. Need recognition
grounds the need in evidence (a belief confidence is never asserted), and the
evaluator derives a stance (suggest / ask first / withhold) from that evidence.
"""

from __future__ import annotations

import pytest

from jarvis import Jarvis
from jarvis.domain.enums.capability_stance import CapabilityStance
from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.capability_scout import catalog, scout
from jarvis.domain.value_objects.capability_need import CapabilityNeed
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.capability_registry import (
    ExternalSourceCapability,
    StaticCapabilityRegistry,
    build_default_registry,
)


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
    def test_catalog_lists_every_known_capability_with_purpose_and_requirement(self) -> None:
        entries = catalog()
        assert entries, "the catalog must never be empty"
        names = {c.name for c in entries}
        for expected in (
            "search the web", "read external documents", "deep research",
            "recall by meaning", "reason with a language model", "perceive speech",
            "send and read email", "manage notes", "manage calendar",
            "manage tasks", "delegate to an agent", "compare language models",
        ):
            assert expected in names, f"catalog missing {expected!r}"
        for entry in entries:
            assert entry.description and entry.requirement, f"{entry.name!r} lacks purpose/requirement"

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

    def test_email_need_proposes_send_and_read_email(self) -> None:
        candidates = scout(
            CapabilityNeed(
                statement="I want to read my inbox",
                rationale="I need to check my email",
            )
        )
        assert any(c.name == "send and read email" for c in candidates)

    def test_notes_need_proposes_manage_notes(self) -> None:
        candidates = scout(
            CapabilityNeed(
                statement="keep a note and remind me later",
                rationale="a todo I must not forget",
            )
        )
        assert any(c.name == "manage notes" for c in candidates)

    def test_calendar_need_proposes_manage_calendar(self) -> None:
        candidates = scout(
            CapabilityNeed(
                statement="schedule a meeting on my calendar",
                rationale="I need to manage my agenda",
            )
        )
        assert any(c.name == "manage calendar" for c in candidates)

    def test_scheduled_task_need_proposes_manage_tasks(self) -> None:
        candidates = scout(
            CapabilityNeed(
                statement="do this every morning automatically",
                rationale="a recurring task I want on a schedule",
            )
        )
        assert any(c.name == "manage tasks" for c in candidates)

    def test_agent_delegation_need_proposes_delegate_to_an_agent(self) -> None:
        candidates = scout(
            CapabilityNeed(
                statement="delegate this to an agent",
                rationale="hand a concrete task to an executor",
            )
        )
        assert any(c.name == "delegate to an agent" for c in candidates)

    def test_new_shortcuts_do_not_break_unknown_needs(self) -> None:
        candidates = scout(
            CapabilityNeed(
                statement="I would like to paint a mural",
                rationale="to decorate the studio",
            )
        )
        assert candidates == ()


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


class _OfflineSource:
    """A stub ExternalSource (no network) for provider tests."""

    def read(self, url: str) -> object:
        return None

    def search(self, query: str, *, limit: int = 5) -> tuple[object, ...]:
        return ()

    def available_channels(self) -> tuple[object, ...]:
        return ()


class _StubProvider:
    """A ready CapabilityProvider serving a single named capability (offline)."""

    def __init__(self, capability: str, available: bool = True) -> None:
        self._capability = capability
        self._available = available

    @property
    def capability(self) -> str:
        return self._capability

    def is_available(self) -> bool:
        return self._available


def _acquire(jarvis: Jarvis, name: str) -> None:
    jarvis.remember_capability(jarvis.need_capability(name, "for growth")[0])
    jarvis.acquire_capability(name)


class TestCapabilityProviders:
    def test_an_acquired_capability_without_a_provider_is_not_doable(self) -> None:
        jarvis = Jarvis()
        _acquire(jarvis, "search the web")
        assert not jarvis.can_do("search the web")
        assert jarvis.usable_capabilities() == ()

    def test_an_acquired_backed_capability_is_doable(self) -> None:
        source = _OfflineSource()
        jarvis = Jarvis(
            external_source=source,  # type: ignore[arg-type]
            capability_providers=build_default_registry(source),  # type: ignore[arg-type]
        )
        _acquire(jarvis, "search the web")
        assert jarvis.can_do("search the web")
        assert jarvis.usable_capabilities() == ("search the web",)

    def test_an_unacquired_capability_is_never_doable(self) -> None:
        source = _OfflineSource()
        jarvis = Jarvis(
            external_source=source,  # type: ignore[arg-type]
            capability_providers=build_default_registry(source),  # type: ignore[arg-type]
        )
        assert not jarvis.can_do("search the web")
        assert jarvis.usable_capabilities() == ()

    def test_an_unavailable_provider_is_not_doable(self) -> None:
        registry = StaticCapabilityRegistry(
            _by_name={"search the web": _StubProvider("search the web", available=False)}
        )
        jarvis = Jarvis(capability_providers=registry)
        _acquire(jarvis, "search the web")
        assert not jarvis.can_do("search the web")
        assert jarvis.usable_capabilities() == ()

    def test_a_wired_source_auto_backs_the_web_capabilities(self) -> None:
        source = _OfflineSource()
        jarvis = Jarvis(external_source=source)  # type: ignore[arg-type]
        _acquire(jarvis, "read external documents")
        assert jarvis.can_do("read external documents")

    def test_setting_a_source_at_runtime_rewires_the_default_registry(self) -> None:
        jarvis = Jarvis()
        _acquire(jarvis, "search the web")
        assert not jarvis.can_do("search the web")
        jarvis.set_external_source(_OfflineSource())  # type: ignore[arg-type]
        assert jarvis.can_do("search the web")
        jarvis.set_external_source(None)
        assert not jarvis.can_do("search the web")

    def test_an_explicit_registry_survives_set_external_source(self) -> None:
        registry = StaticCapabilityRegistry(
            _by_name={"search the web": _StubProvider("search the web")}
        )
        jarvis = Jarvis(capability_providers=registry)
        _acquire(jarvis, "search the web")
        jarvis.set_external_source(_OfflineSource())  # type: ignore[arg-type]
        assert jarvis.can_do("search the web")  # custom registry untouched

    def test_build_default_registry_without_a_source_is_empty(self) -> None:
        registry = build_default_registry(None)
        assert registry.provider_for("search the web") is None

    def test_default_registry_can_back_reasoner_and_recall_seams(self) -> None:
        from jarvis.infrastructure.capability_registry import (
            ReasonerCapability,
            SemanticRecallCapability,
        )

        reason = ReasonerCapability()
        recall = SemanticRecallCapability()
        registry = build_default_registry(
            None, reasoner=reason, recall=recall
        )
        assert registry.provider_for("reason with a language model") is reason
        assert registry.provider_for("recall by meaning") is recall
        # With a source, the web capabilities are backed alongside them.
        web_registry = build_default_registry(
            _OfflineSource(),  # type: ignore[arg-type]
            reasoner=reason,
            recall=recall,
        )
        assert web_registry.provider_for("search the web") is not None
        assert web_registry.provider_for("reason with a language model") is reason

    def test_external_source_capability_reports_service_and_availability(self) -> None:
        provider = ExternalSourceCapability(_OfflineSource(), "read external documents")  # type: ignore[arg-type]
        assert provider.capability == "read external documents"
        assert provider.is_available()

    def test_reasoner_capability_is_a_mutable_edge_seam(self) -> None:
        from jarvis.infrastructure.capability_registry import ReasonerCapability

        provider = ReasonerCapability()
        assert provider.capability == "reason with a language model"
        assert not provider.is_available()  # offline/silent by default
        provider.set_live(True)
        assert provider.is_available()
        provider.set_live(False)
        assert not provider.is_available()

    def test_semantic_recall_capability_is_a_mutable_edge_seam(self) -> None:
        from jarvis.infrastructure.capability_registry import SemanticRecallCapability

        provider = SemanticRecallCapability()
        assert provider.capability == "recall by meaning"
        assert not provider.is_available()
        provider.set_live(True)
        assert provider.is_available()

    def test_a_silent_reasoner_does_not_back_the_reason_capability(self) -> None:
        from jarvis.infrastructure.silent_reasoner import SilentReasoner

        jarvis = Jarvis()
        _acquire(jarvis, "reason with a language model")
        jarvis.set_reasoner(SilentReasoner())
        # An offline reasoner proposes nothing -> not a usable reasoning capability.
        assert not jarvis.can_do("reason with a language model")

    def test_a_live_reasoner_backs_the_reason_capability(self) -> None:
        from jarvis.domain.conversation.conversation_context import Turn
        from jarvis.domain.value_objects.inference import Inference
        from jarvis.domain.value_objects.recalled_memory import RecalledMemory

        class _LiveReasoner:
            def infer(
                self,
                query: str,
                memory: tuple[RecalledMemory, ...] = (),
                conversation: tuple[Turn, ...] = (),
            ) -> Inference | None:
                return None

        jarvis = Jarvis()
        _acquire(jarvis, "reason with a language model")
        jarvis.set_reasoner(_LiveReasoner())
        assert jarvis.can_do("reason with a language model")
        assert "reason with a language model" in jarvis.usable_capabilities()

    def test_enabling_embedding_recall_backs_the_recall_capability(self) -> None:
        class _StubEmbedder:
            def embed(self, texts: tuple[str, ...]) -> list[tuple[float, ...]]:
                return [(0.0,) for _ in texts]

        jarvis = Jarvis()
        _acquire(jarvis, "recall by meaning")
        assert not jarvis.can_do("recall by meaning")
        jarvis.enable_embedding_recall(_StubEmbedder())  # type: ignore[arg-type]
        assert jarvis.can_do("recall by meaning")
        assert "recall by meaning" in jarvis.usable_capabilities()

    def test_the_ear_backs_the_perceive_speech_capability(self) -> None:
        from jarvis.infrastructure.speech_perception import EchoSpeechPerception

        jarvis = Jarvis()
        _acquire(jarvis, "perceive speech")
        assert not jarvis.can_do("perceive speech")
        assert jarvis.speech_perception is None
        jarvis.set_speech_perception(EchoSpeechPerception())
        assert jarvis.can_do("perceive speech")
        assert "perceive speech" in jarvis.usable_capabilities()
        # The default ear (browser Web Speech) passes the transcribed text through.
        assert jarvis.perceive_speech("hello") == "hello"

    def test_disabling_the_ear_clears_the_perceive_speech_capability(self) -> None:
        from jarvis.infrastructure.speech_perception import EchoSpeechPerception

        jarvis = Jarvis()
        _acquire(jarvis, "perceive speech")
        jarvis.set_speech_perception(EchoSpeechPerception())
        assert jarvis.can_do("perceive speech")
        jarvis.set_speech_perception(None)
        assert not jarvis.can_do("perceive speech")
        with pytest.raises(RuntimeError):
            jarvis.perceive_speech("hello")
