"""Inc H: semantic recall — memory found by meaning, not surface words (D11).

Offline and deterministic: a fake embedder maps text to vectors by a simple cluster
so ranking is controlled without a network. The real embedder (ollama bge-m3) is a
drop-in behind the same TextEmbedder Protocol and is exercised only when configured.
"""

from __future__ import annotations

import json

from jarvis import Jarvis
from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.executive.executive_controller import working_statement
from jarvis.infrastructure.embedding_memory_retriever import EmbeddingMemoryRetriever
from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore
from jarvis.infrastructure.in_memory_episode_store import InMemoryEpisodeStore
from jarvis.infrastructure.lexical_memory_retriever import LexicalMemoryRetriever
from jarvis.infrastructure.openai_compatible_embedder import OpenAiCompatibleEmbedder
from jarvis.infrastructure.perceiver_factory import build_embedder
from jarvis.infrastructure.text_embedder import TextEmbedder

# Words that mean "identity" — the fake embedder puts anything containing one of these
# on the same axis, so "quien soy" and "is named Raúl / me llamo Raúl" cluster together
# even though they share no surface tokens (what real embeddings do for meaning).
_IDENTITY = ("raul", "raúl", "nombre", "llamo", "soy", "quien", "yo")


class ClusterEmbedder:
    """A deterministic fake: identity-ish text -> one axis, everything else -> another."""

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if self._fail:
            raise RuntimeError("embedder unreachable")
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            low = text.lower()
            identity = any(word in low for word in _IDENTITY)
            vectors.append((1.0, 0.0) if identity else (0.0, 1.0))
        return tuple(vectors)


def _companion_named() -> CompanionModel:
    companion = CompanionModel(InMemoryBeliefStore())
    companion.observe(
        "is named Raúl",
        Evidence(
            content="me llamo Raúl",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(0.9),
        ),
    )
    return companion


def _retriever(
    *,
    beliefs: InMemoryBeliefStore | None = None,
    companion: CompanionModel | None = None,
    embedder: TextEmbedder | None = None,
    fallback: LexicalMemoryRetriever | None = None,
) -> EmbeddingMemoryRetriever:
    b = beliefs or InMemoryBeliefStore()
    e = InMemoryEpisodeStore()
    c = companion or CompanionModel(InMemoryBeliefStore())
    g = InMemoryBeliefStore()
    return EmbeddingMemoryRetriever(b, e, c, g, embedder or ClusterEmbedder(), fallback=fallback)


class TestOpenAiCompatibleEmbedder:
    def test_it_satisfies_the_text_embedder_protocol(self) -> None:
        assert isinstance(
            OpenAiCompatibleEmbedder(base_url="http://x/v1", model="bge-m3"), TextEmbedder
        )

    def test_it_parses_vectors_and_sends_model_and_input(self) -> None:
        seen: dict[str, object] = {}

        def transport(url: str, headers: dict[str, str], body: bytes) -> str:
            seen["url"] = url
            seen["body"] = json.loads(body)
            return json.dumps(
                {"data": [{"index": 1, "embedding": [0.3, 0.4]},
                          {"index": 0, "embedding": [0.1, 0.2]}]}
            )

        embedder = OpenAiCompatibleEmbedder(
            base_url="http://localhost:11434/v1", model="bge-m3", transport=transport
        )
        vectors = embedder.embed(("a", "b"))
        assert vectors == ((0.1, 0.2), (0.3, 0.4))  # reordered by index
        assert seen["url"] == "http://localhost:11434/v1/embeddings"
        assert seen["body"] == {"model": "bge-m3", "input": ["a", "b"]}

    def test_a_count_mismatch_is_an_error(self) -> None:
        def transport(url: str, headers: dict[str, str], body: bytes) -> str:
            return json.dumps({"data": [{"index": 0, "embedding": [0.1]}]})

        embedder = OpenAiCompatibleEmbedder(
            base_url="http://x/v1", model="bge-m3", transport=transport
        )
        try:
            embedder.embed(("a", "b"))
        except ValueError:
            return
        raise AssertionError("expected a ValueError on a vector/input count mismatch")


class TestEmbeddingRecall:
    def test_it_recalls_by_meaning_across_a_wording_gap(self) -> None:
        # "quien soy" shares NO tokens with "is named Raúl" — lexical recall can't
        # bridge it, but meaning can.
        beliefs = InMemoryBeliefStore()
        b = Belief(statement=working_statement("the deployment plan"))
        b.add_evidence(
            Evidence(content="the deployment plan", source=EvidenceSource.USER_STATEMENT,
                     weight=Confidence(1.0))
        )
        beliefs.save(b)
        hits = _retriever(beliefs=beliefs, companion=_companion_named()).recall("quien soy")
        assert [h.kind for h in hits] == [MemoryKind.COMPANION_TRAIT]
        assert hits[0].content == "is named Raúl"

    def test_a_meaning_distant_memory_is_not_surfaced(self) -> None:
        # A query that clusters away from the only (identity) memory recalls nothing.
        assert _retriever(companion=_companion_named()).recall("the weather today") == ()

    def test_it_falls_back_when_the_embedder_is_unreachable(self) -> None:
        # Embedder down -> degrade to the wrapped lexical retriever, not to nothing.
        companion = _companion_named()
        lexical = LexicalMemoryRetriever(
            InMemoryBeliefStore(), InMemoryEpisodeStore(), companion, InMemoryBeliefStore()
        )
        retriever = _retriever(
            companion=companion, embedder=ClusterEmbedder(fail=True), fallback=lexical
        )
        # A lexical-matchable query still works via the fallback.
        hits = retriever.recall("named Raúl")
        assert any(h.content == "is named Raúl" for h in hits)

    def test_without_a_fallback_a_failure_is_honest_silence(self) -> None:
        retriever = _retriever(companion=_companion_named(), embedder=ClusterEmbedder(fail=True))
        assert retriever.recall("quien soy") == ()


class TestBuildEmbedder:
    def test_no_model_configured_means_no_embedder(self) -> None:
        assert build_embedder({}) is None

    def test_a_configured_model_builds_an_embedder(self) -> None:
        embedder = build_embedder({"JARVIS_EMBED_MODEL": "bge-m3"})
        assert isinstance(embedder, OpenAiCompatibleEmbedder)


class TestEmbeddingRecallWiring:
    def test_enable_embedding_recall_finds_a_trait_by_meaning(self) -> None:
        jarvis = Jarvis(enable_recall=True)
        jarvis.observe_companion(
            "is named Raúl",
            Evidence(content="me llamo Raúl", source=EvidenceSource.USER_STATEMENT,
                     weight=Confidence(0.9)),
        )
        jarvis.enable_embedding_recall(ClusterEmbedder())
        # "el nombre" is NOT a self-question (no self-reference), so the trait can only
        # surface via meaning-based recall — isolating the embedding path from Inc 105's
        # self-question companion routing.
        episode = jarvis.perceive("el nombre", trigger="el nombre")
        assert "is named Raúl" in [m.content for m in episode.recalled_memories]
