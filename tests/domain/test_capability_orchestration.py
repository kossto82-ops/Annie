"""capability_orchestration: the capability decision layer, tested offline.

The decision is deterministic and read-only: given a subject it answers
"does this need external information, and which capability?", and executing a
decision routes to a provider exactly once and returns an inspectable outcome.
Every test here runs with no socket and no provider mutation of cognition.
"""

from __future__ import annotations

from jarvis.domain.retrieval.external_source import ChannelStatus
from jarvis.domain.services.capability_orchestration import (
    decide_capability,
    execute_capability,
)
from jarvis.domain.value_objects.capability_outcome import CapabilityOutcomeStatus
from jarvis.domain.value_objects.capability_requirement import CapabilityRequirement
from jarvis.domain.value_objects.retrieved_document import RetrievedDocument


class _StaticSource:
    """A canned provider: returns one document, recounting its calls."""

    def __init__(self, content: str = "found data") -> None:
        self._content = content
        self.read_calls = 0
        self.search_calls = 0

    def read(self, url: str) -> RetrievedDocument:
        self.read_calls += 1
        return RetrievedDocument(
            content=self._content,
            source="web",
            url=url,
            metadata={"provider": "agent_reach", "backend": "jina-reader"},
        )

    def search(
        self, query: str, *, limit: int = 5
    ) -> tuple[RetrievedDocument, ...]:
        self.search_calls += 1
        return (
            RetrievedDocument(
                content=self._content,
                source="web_search",
                metadata={"provider": "agent_reach", "backend": "llm-search"},
            ),
        )

    def available_channels(self) -> tuple[ChannelStatus, ...]:
        return (ChannelStatus(name="web", status="ok", active_backend="jina-reader"),)


class _EmptySource:
    """A provider whose search honestly finds nothing."""

    def read(self, url: str) -> RetrievedDocument:
        return RetrievedDocument(content="body", source="web", url=url)

    def search(self, query: str, *, limit: int = 5) -> tuple[RetrievedDocument, ...]:
        return ()

    def available_channels(self) -> tuple[ChannelStatus, ...]:
        return (
            ChannelStatus(name="web", status="ok"),
            ChannelStatus(name="search", status="ok", active_backend="llm-search"),
        )


class _BrokenSource:
    """A provider whose every call fails."""

    def read(self, url: str) -> RetrievedDocument:
        raise RuntimeError("network down")

    def search(
        self, query: str, *, limit: int = 5
    ) -> tuple[RetrievedDocument, ...]:
        raise RuntimeError("network down")

    def available_channels(self) -> tuple[ChannelStatus, ...]:
        return ()


class _SearchOffSource:
    """A provider that honestly reports its search channel as turned off."""

    def __init__(self) -> None:
        self.search_calls = 0

    def read(self, url: str) -> RetrievedDocument:
        raise AssertionError("read must not be called by a search-off check")

    def search(self, query: str, *, limit: int = 5) -> tuple[RetrievedDocument, ...]:
        self.search_calls += 1
        return ()

    def available_channels(self) -> tuple[ChannelStatus, ...]:
        return (
            ChannelStatus(name="web", status="ok"),
            ChannelStatus(name="search", status="off"),
        )


class TestDecideCapability:
    def test_known_internal_information_needs_no_external_capability(self) -> None:
        decision = decide_capability(
            "my favourite colour is green", known_internally=True
        )
        assert decision.needed is False
        assert decision.capability is None
        assert "no external capability needed" in decision.reason

    def test_subject_without_external_cues_needs_nothing(self) -> None:
        decision = decide_capability("the sky is blue")
        assert decision.needed is False

    def test_current_external_information_requests_web_search(self) -> None:
        decision = decide_capability("what is the current weather in Madrid?")
        assert decision.needed is True
        assert decision.capability is CapabilityRequirement.SEARCH_WEB

    def test_latest_news_requests_web_search(self) -> None:
        decision = decide_capability("show me the latest news about the election")
        assert decision.capability is CapabilityRequirement.SEARCH_WEB

    def test_spanish_timely_cues_request_web_search(self) -> None:
        decision = decide_capability("¿cuál es la noticia más actual del clima?")
        assert decision.capability is CapabilityRequirement.SEARCH_WEB

    def test_a_url_in_the_subject_requests_a_read(self) -> None:
        decision = decide_capability("read https://example.com/doc page")
        assert decision.needed is True
        assert decision.capability is CapabilityRequirement.READ_URL
        assert decision.target == "https://example.com/doc"

    def test_a_url_in_source_hint_requests_a_read(self) -> None:
        decision = decide_capability(
            "read this url", source_hint="https://example.com/doc"
        )
        assert decision.capability is CapabilityRequirement.READ_URL
        assert decision.target == "https://example.com/doc"

    def test_explicit_github_source_is_not_substituted(self) -> None:
        decision = decide_capability(
            "check GitHub for the jarvis release notes", source_hint="GitHub"
        )
        assert decision.capability is CapabilityRequirement.RESEARCH_GITHUB
        assert decision.source_hint == "GitHub"

    def test_github_keyword_requests_github_research(self) -> None:
        decision = decide_capability("search the jarvis repository for its license")
        assert decision.capability is CapabilityRequirement.RESEARCH_GITHUB

    def test_explicit_youtube_source_requests_youtube_research(self) -> None:
        decision = decide_capability(
            "look at YouTube for a tutorial", source_hint="youtube"
        )
        assert decision.capability is CapabilityRequirement.RESEARCH_YOUTUBE

    def test_the_reason_is_an_inspectable_trace(self) -> None:
        decision = decide_capability(
            "latest price of Bitcoin", reason="I need current information to answer"
        )
        assert decision.reason == "I need current information to answer"
        derived = decide_capability("latest price of Bitcoin")
        assert "latest price of Bitcoin" in derived.reason


class TestExecuteCapability:
    def test_no_need_executes_nothing(self) -> None:
        source = _StaticSource()
        outcome = execute_capability(decide_capability("the sky is blue"), source)
        assert outcome.status is CapabilityOutcomeStatus.NO_NEED
        assert outcome.attempts == 0
        assert source.read_calls == 0
        assert source.search_calls == 0
        assert outcome.documents == ()

    def test_search_success_returns_documents(self) -> None:
        source = _StaticSource()
        outcome = execute_capability(
            decide_capability("latest news about climate"), source
        )
        assert outcome.status is CapabilityOutcomeStatus.SUCCESS
        assert outcome.obtained is True
        assert len(outcome.documents) == 1
        assert source.search_calls == 1
        assert source.read_calls == 0
        assert outcome.attempts == 1

    def test_read_success_returns_a_document_with_provenance(self) -> None:
        source = _StaticSource()
        outcome = execute_capability(
            decide_capability("read https://example.com/climate"), source
        )
        assert outcome.status is CapabilityOutcomeStatus.SUCCESS
        doc = outcome.documents[0]
        assert doc.url == "https://example.com/climate"
        assert doc.metadata["provider"] == "agent_reach"
        assert outcome.provider_backends == (("agent_reach", "jina-reader"),)
        assert source.read_calls == 1

    def test_source_preference_rides_the_request_trace(self) -> None:
        source = _StaticSource()
        outcome = execute_capability(
            decide_capability("latest release", source_hint="GitHub"), source
        )
        assert outcome.status is CapabilityOutcomeStatus.SUCCESS
        assert outcome.request.source_preference == "GitHub"
        assert outcome.request.capability is CapabilityRequirement.RESEARCH_GITHUB

    def test_unavailable_when_no_provider_is_wired(self) -> None:
        outcome = execute_capability(decide_capability("latest news"), None)
        assert outcome.status is CapabilityOutcomeStatus.UNAVAILABLE
        assert outcome.attempts == 0
        # Unavailable is not "the information does not exist" -- and never evidence.
        assert outcome.documents == ()

    def test_unavailable_when_search_channel_reports_off(self) -> None:
        source = _SearchOffSource()
        outcome = execute_capability(
            decide_capability("latest news about climate"), source
        )
        assert outcome.status is CapabilityOutcomeStatus.UNAVAILABLE
        assert source.search_calls == 0
        assert outcome.attempts == 0

    def test_empty_result_is_an_honest_nothing(self) -> None:
        outcome = execute_capability(
            decide_capability("latest news about climate"), _EmptySource()
        )
        assert outcome.status is CapabilityOutcomeStatus.EMPTY
        assert outcome.attempts == 1
        assert outcome.documents == ()
        # Nothing found is not negative evidence -- no documents, no claim.

    def test_failure_returns_failed_state(self) -> None:
        outcome = execute_capability(
            decide_capability("latest news about climate"), _BrokenSource()
        )
        assert outcome.status is CapabilityOutcomeStatus.FAILED
        assert "failed" in outcome.message
        assert outcome.attempts == 1

    def test_read_without_a_url_fails_honestly(self) -> None:
        from dataclasses import replace

        decision = replace(
            decide_capability("latest news about climate"),
            capability=CapabilityRequirement.READ_URL,
        )
        outcome = execute_capability(decision, _StaticSource())
        assert outcome.status is CapabilityOutcomeStatus.FAILED
        assert "no URL" in outcome.message

    def test_failure_is_bounded_to_one_attempt(self) -> None:
        source = _BrokenSource()
        for _ in range(3):
            outcome = execute_capability(
                decide_capability("latest news about climate"), source
            )
            assert outcome.status is CapabilityOutcomeStatus.FAILED
            assert outcome.attempts == 1
            # Each execution is exactly one bounded attempt -- no accumulating loop
            # and no automatic "search again" on uncertainty.


class TestOutcomeTrace:
    def test_outcome_echoes_the_request_and_reason(self) -> None:
        outcome = execute_capability(
            decide_capability(
                "latest price of Bitcoin", reason="needed current information"
            ),
            _StaticSource(),  # type: ignore[arg-type]
        )
        assert outcome.request.reason == "needed current information"
        assert outcome.request.subject == "latest price of Bitcoin"