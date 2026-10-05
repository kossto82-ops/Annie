"""Vocabulary depth v1 (Increment 187): the Spanish morphological fold and
the synonym channel.

Two deterministic, offline additions to the D18 bilingual meaning recall, at
the same lexical layer (``abstraction.py``) -- no LLM, no new abstractions:

- **Spanish morphological depth** -- accent folding (one stored entry covers an
  accented and an unaccented spelling: "decisión"/"decision", "decidió"/
  "decidio") plus an explicit inflected-form lexicon that resolves a conjugated
  surface to a lemma CONCEPT_MAP already carries ("entregaron" -> DELIVER). The
  Spanish side of recall therefore no longer needs every inflection hand-listed,
  and every derivation still resolves *through* CONCEPT_MAP, so the layer stays
  ontology-neutral.
- **The synonym channel** -- ``relatedness`` gains a third, same-language
  surface channel of curated clusters ("glad" meets "happy"); cross-language
  meeting stays at the concept level only (D38).

The repaired matter-preservation exclusions (create/estimate/receive/give) and
the pinned English signatures must not move, and unrelated pairs must stay
honestly silent (Vision §37).
"""
from jarvis.domain.services.abstraction import (
    concept_relevance,
    conceptual_tokens,
    episode_signature,
    relatedness,
    surface_overlap,
    synonym_overlap,
)
from jarvis.infrastructure.lexical_memory_retriever import LexicalMemoryRetriever


def _sig(text: str) -> set[str]:
    return set(episode_signature(text))


def _concepts(text: str) -> set[str]:
    return set(conceptual_tokens(text))


# ---------------------------------------------------------------------------
# Spanish morphological fold
# ---------------------------------------------------------------------------


class TestAccentFold:
    def test_accented_spellings_reach_their_lemma(self) -> None:
        expected = {
            "decidió": {"DECIDE"},
            "costó": {"COST"},
            "retrasó": {"TIME"},
            "coincidió": {"AGREE"},
            "pidió": {"REQUEST"},
            "consiguió": {"SUCCEED"},
            "creció": {"INCREASE"},
        }
        for word, want in expected.items():
            assert _sig(word) == want, f"{word!r}: got {_sig(word)}, want {want}"

    def test_accented_and_plain_spellings_meet(self) -> None:
        assert _sig("decisión") == _sig("decision") == {"DECIDE"}
        assert _sig("construí") == _sig("construi") == {"BUILD"}
        assert _sig("memoria") == _sig("memorias") == {"REMEMBER"}


class TestInflectedLexicon:
    def test_inflected_forms_resolve_to_their_lemma(self) -> None:
        expected = {
            "entregaron": {"DELIVER"},
            "aprendo": {"LEARN"},
            "viajamos": {"TRAVEL"},
            "recuerdan": {"REMEMBER"},
            "pido": {"REQUEST"},
            "consigo": {"SUCCEED"},
            "mejoro": {"INCREASE"},
            "bajaron": {"DECREASE"},
            "cuestan": {"COST"},
            "evitan": {"PREVENT"},
            "aceptas": {"AGREE"},
            "elijo": {"DECIDE"},
            "fracasó": {"FAIL"},
            "estudiar": {"LEARN"},
            "plazo": {"TIME"},
            "seguro": {"SAFE"},
            "meta": {"PURPOSE"},
            "mal": {"WRONG"},
            "pasado": {"HISTORY"},
            "eleccion": {"DECIDE"},
            "exito": {"SUCCEED"},
            "desafío": {"CHALLENGE"},
        }
        for word, want in expected.items():
            assert _sig(word) == want, f"{word!r}: got {_sig(word)}, want {want}"

    def test_everyday_family_full_consistency(self) -> None:
        families = {
            "pedir": ("pedir", "pido", "pides", "pide", "piden", "pidiendo", "pedido"),
            "entregar": ("entregar", "entrego", "entregas", "entrega", "entregan"),
            "viajar": ("viajar", "viajo", "viajas", "viajan", "viajamos", "viaje"),
            "lograr": ("lograr", "logro", "logras", "logra", "logran"),
            "evitar": ("evitar", "evito", "evitas", "evita", "evitan"),
        }
        for lemma, forms in families.items():
            expected = _sig(lemma)
            assert expected, f"{lemma!r} must carry a concept"
            for form in forms:
                assert _sig(form) == expected, (
                    f"{form!r} lost the {expected} of its lemma {lemma!r}: got {_sig(form)}"
                )

    def test_stem_changing_verbs_are_written_out_correctly(self) -> None:
        # Spanish stem changes (e->i, o->ue) are listed exactly, never guessed.
        assert _sig("pide") == _sig("piden") == {"REQUEST"}
        assert _sig("elige") == _sig("eligen") == {"DECIDE"}
        assert _sig("consigue") == _sig("consiguen") == {"SUCCEED"}
        assert _sig("cuesta") == _sig("cuestan") == {"COST"}
        assert _sig("impide") == _sig("impiden") == {"PREVENT"}

    def test_creo_is_deliberately_not_build(self) -> None:
        # "creo que ..." is "I believe", not "I build" -- a demonstrable false
        # positive for everyday recall, so the 1sg form stays unmapped while
        # the unambiguous forms of crear still resolve.
        assert _sig("creo que puedo") == set()
        assert _sig("crea un plan") == {"BUILD"}
        assert _sig("construyo") == {"BUILD"}

    def test_spanish_tokens_outside_the_everyday_lexicon_stay_silent(self) -> None:
        assert _sig("prefiero") == set()
        assert _sig("trabajar") == set()
        assert _sig("noche") == set()


class TestBilingualMeet:
    def test_spanish_inflection_meets_an_english_query(self) -> None:
        # "entregaron" (DELIVER) and "delivered" (DELIVER) share the concept
        # despite sharing no surface words -- the morphological fold extends
        # the existing cross-language meet.
        assert concept_relevance(
            "did they deliver the order on time", "entregaron el pedido a tiempo"
        ) > 0.0
        # And the plain-word channel stays 0: the meet is conceptual, not lexical.
        assert surface_overlap(
            "did they deliver the order on time", "entregaron el pedido a tiempo"
        ) == 0.0

    def test_spanish_query_finds_an_english_memory(self) -> None:
        assert concept_relevance("¿es seguro?", "the system is reliable") > 0.0

    def test_recall_surfaces_a_cross_language_memory_end_to_end(self) -> None:
        from jarvis.domain.aggregates.companion_model import CompanionModel
        from jarvis.domain.entities.belief import Belief
        from jarvis.domain.enums.evidence_source import EvidenceSource
        from jarvis.domain.value_objects.confidence import Confidence
        from jarvis.domain.value_objects.evidence import Evidence
        from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore
        from jarvis.infrastructure.in_memory_episode_store import InMemoryEpisodeStore

        beliefs = InMemoryBeliefStore()
        belief = Belief(statement="the order was shipped")
        belief.add_evidence(
            Evidence(
                content="the order was shipped",
                source=EvidenceSource.USER_STATEMENT,
                weight=Confidence(1.0),
                supports=True,
            )
        )
        beliefs.save(belief)
        retriever = LexicalMemoryRetriever(
            beliefs=beliefs,
            episodes=InMemoryEpisodeStore(),
            companion=CompanionModel(InMemoryBeliefStore()),
            goals=InMemoryBeliefStore(),
        )
        hits = retriever.recall("¿cuándo entregaron mi pedido?")
        assert len(hits) == 1, f"expected the shipped-order belief, got {hits}"
        assert hits[0].content == "the order was shipped"
        assert hits[0].relevance > 0.0


# ---------------------------------------------------------------------------
# The synonym channel
# ---------------------------------------------------------------------------


class TestSynonymChannel:
    def test_synonym_overlap_is_positive_within_a_cluster(self) -> None:
        assert synonym_overlap("I feel glad", "she felt happy") > 0.0
        assert synonym_overlap("estoy cansado", "él está agotado") > 0.0

    def test_synonym_overlap_is_zero_across_clusters(self) -> None:
        assert synonym_overlap("glad", "tired") == 0.0
        assert synonym_overlap("happy", "sad") == 0.0

    def test_synonym_overlap_is_zero_without_a_cluster_word(self) -> None:
        assert synonym_overlap("gardening in winter", "the deployment plan") == 0.0

    def test_synonym_channel_grounds_relatedness_without_concepts(self) -> None:
        query, text = "so glad for you", "she was delighted"
        assert concept_relevance(query, text) == 0.0
        assert surface_overlap(query, text) == 0.0
        assert relatedness(query, text) == synonym_overlap(query, text) > 0.0

    def test_unrelated_pairs_stay_honestly_silent(self) -> None:
        assert relatedness("happy birthday", "annual report") == 0.0
        assert relatedness("gardening in winter", "the deployment plan") == 0.0


# ---------------------------------------------------------------------------
# Matter preservation and English invariants (must not move)
# ---------------------------------------------------------------------------


class TestEnglishUntouched:
    def test_english_create_family_stays_unmapped(self) -> None:
        for form in ("create", "created", "creating"):
            assert _sig(form) == set(), f"{form!r} must not become a concept"

    def test_matter_preservation_exclusions_pinned(self) -> None:
        assert _sig("created value") == set()
        assert _sig("gave support") == set()
        assert _sig("estimated cost") == {"COST"}
        assert _sig("underestimated cost") == {"COST"}
        assert _sig("overestimated cost") == {"COST"}
        assert _sig("received the package") == set()

    def test_english_dimension_signatures_pinned(self) -> None:
        expected = {
            "supplier delivered": {"DELIVER"},
            "supplier failed to deliver": {"DELIVER", "FAIL"},
            "supplier succeeded in delivering": {"DELIVER", "SUCCEED"},
            "the deadline passed": {"TIME"},
            "the risk is high": {"RISK"},
            "the system is safe": {"SAFE"},
            "she decided to accept": {"DECIDE"},
            "they request a refund": {"REQUEST"},
        }
        for text, want in expected.items():
            assert _sig(text) == want, f"{text!r}: got {_sig(text)}, want {want}"

    def test_synonym_channel_never_touches_signatures(self) -> None:
        # Synonyms are a surface-score concern only; the canonical signature of
        # an emotion word stays empty (it is not an ontology concept).
        assert _sig("i was so glad") == set()
        assert _sig("she felt sad and tired") == set()

    def test_signature_empty_invariant_kept(self) -> None:
        assert episode_signature("foo bar baz") == frozenset()
        assert episode_signature("the quick brown fox") == frozenset()

    def test_conceptual_tokens_still_entity_independent(self) -> None:
        assert _concepts("el contratista entregó") == _concepts("the supplier delivered")
        assert _concepts("el contratista entregó") == {"DELIVER"}