"""Inc C: recall wired into the episode lets Jarvis answer from memory (Vision §3).

Recall is *response context*, not belief-evidence (Vision §22): it never changes a
belief's derived confidence, only what the surface can say when it holds no grounded
view. Recall is opt-in (``enable_recall``), so the offline core is unchanged by default.
"""

from __future__ import annotations

import pytest

from jarvis import Jarvis
from jarvis.domain.aggregates.cognitive_episode import (
    CognitiveEpisode,
    InvalidStateTransition,
)
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.interface.command_center import handle


def _knows_name(jarvis: Jarvis) -> None:
    """Teach Jarvis the companion's name the way the LLM companion channel would:
    a trait grounded in the person's own words.
    """
    jarvis.observe_companion(
        "is named Raúl",
        Evidence(
            content="me llamo Raúl",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(0.9),
        ),
    )

_PRIOR = "we are building Jarvis as a companion"
_QUESTION = "what are we building with Jarvis"


def _memory(content: str) -> RecalledMemory:
    return RecalledMemory(
        content=content, kind=MemoryKind.EPISODE, provenance="episode", relevance=1.0
    )


class TestEpisodeRecall:
    def test_recalled_memories_default_to_empty(self) -> None:
        assert CognitiveEpisode(trigger="x").recalled_memories == ()

    def test_recall_attaches_memories(self) -> None:
        episode = CognitiveEpisode(trigger="x")
        episode.recall((_memory("a"), _memory("b")))
        assert [memory.content for memory in episode.recalled_memories] == ["a", "b"]

    def test_recalling_into_a_completed_episode_is_rejected(self) -> None:
        episode = CognitiveEpisode(trigger="x")
        episode.begin_reasoning()
        episode.begin_reflecting()
        episode.begin_deciding()
        episode.complete("done")
        with pytest.raises(InvalidStateTransition):
            episode.recall((_memory("a"),))


class TestJarvisRecallWiring:
    def test_recall_is_off_by_default(self) -> None:
        jarvis = Jarvis()
        jarvis.perceive(_PRIOR)
        episode = jarvis.perceive(_QUESTION)
        assert episode.recalled_memories == ()

    def test_a_prior_topic_is_surfaced_when_recall_is_on(self) -> None:
        jarvis = Jarvis(enable_recall=True)
        jarvis.perceive(_PRIOR)
        episode = jarvis.perceive(_QUESTION)
        assert _PRIOR in [memory.content for memory in episode.recalled_memories]

    def test_recall_does_not_echo_the_current_topic_belief(self) -> None:
        jarvis = Jarvis(enable_recall=True)
        trigger = "quantum tunneling is definitely real"
        jarvis.perceive(trigger)  # a cue grounds a world belief for this exact trigger
        episode = jarvis.perceive(trigger)  # asked again
        assert all(
            not (memory.kind is MemoryKind.WORLD_BELIEF and memory.content == trigger)
            for memory in episode.recalled_memories
        )

    def test_a_single_trivial_word_overlap_is_not_surfaced(self) -> None:
        # Sharing one common word is not a relevant memory (below the floor).
        jarvis = Jarvis(enable_recall=True)
        jarvis.perceive("alpha beta gamma delta epsilon")
        episode = jarvis.perceive("epsilon zulu yankee xray whiskey victor")
        assert episode.recalled_memories == ()

    def test_recall_deduplicates_identical_content(self) -> None:
        # An ungrounded turn leaves the same text both as a world belief and an
        # episode; a related query must surface that content once, not twice.
        jarvis = Jarvis(enable_recall=True)
        jarvis.perceive("orchid cultivation requires humidity")
        episode = jarvis.perceive("tell me about orchid cultivation")
        contents = [memory.content for memory in episode.recalled_memories]
        assert contents.count("orchid cultivation requires humidity") == 1

    def test_recall_does_not_inflate_belief_confidence(self) -> None:
        # Memory is not truth (Vision §22): recalling a related topic must not make the
        # working belief about a new, unevidenced question any more confident.
        jarvis = Jarvis(enable_recall=True)
        jarvis.perceive(_PRIOR)
        episode = jarvis.perceive(_QUESTION)
        assert episode.working_belief is not None
        assert episode.working_belief.confidence.value == 0.0


class TestSelfQuestionsConsultTheCompanion:
    def test_self_questions_surface_the_companion_trait_regardless_of_wording(self) -> None:
        jarvis = Jarvis(enable_recall=True)
        _knows_name(jarvis)
        for question in ("sabes mi nombre?", "quien soy?", "cual es mi nombre?"):
            episode = jarvis.perceive(question, trigger=question)
            contents = [memory.content for memory in episode.recalled_memories]
            assert "is named Raúl" in contents, question

    def test_say_answers_a_self_question_from_the_companion_model(self) -> None:
        jarvis = Jarvis(enable_recall=True)
        _knows_name(jarvis)
        result = handle(jarvis, "say", {"text": "sabes mi nombre?"})
        assert result.get("stance") in {"memory", "partial_memory"}
        assert "Raúl" in str(result["reply"])

    def test_a_world_question_does_not_dump_companion_traits(self) -> None:
        jarvis = Jarvis(enable_recall=True)
        _knows_name(jarvis)
        episode = jarvis.perceive(
            "what is the capital of France?", trigger="what is the capital of France?"
        )
        assert episode.recalled_memories == ()


class TestSayAnswersFromMemory:
    def test_it_answers_from_memory_instead_of_a_blank_no_view(self) -> None:
        jarvis = Jarvis(enable_recall=True)
        handle(jarvis, "say", {"text": _PRIOR})
        result = handle(jarvis, "say", {"text": _QUESTION})
        assert result["stance"] == "memory"
        assert _PRIOR in str(result["reply"])
        recalled = result["recalled"]
        assert isinstance(recalled, list) and recalled

    def test_without_recall_the_same_question_stays_at_the_honest_no_view(self) -> None:
        jarvis = Jarvis()  # recall off — behaviour unchanged
        handle(jarvis, "say", {"text": _PRIOR})
        result = handle(jarvis, "say", {"text": _QUESTION})
        assert "stance" not in result
        assert "enough to form a view" in str(result["reply"])
