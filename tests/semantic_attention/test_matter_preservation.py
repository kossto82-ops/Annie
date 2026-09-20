"""Dimension precision / matter preservation v1 regression tests.

Repairs from the DIMENSION COVERAGE / MATTER PRESERVATION v1 implementation
gate. Scope: remove demonstrable false vocabulary mappings while preserving the
existing concept model, polarity orthogonality, and topic identity.

Repaired mappings (repair, not redesign):

- DELIVER: removed overtly generic give/gave/given forms. "gave support",
  "gave a quote", "gave my word", ... no longer absorb into DELIVER.
- TIME: removed the estimate stem. "estimated cost" is {COST}, not {COST, TIME}.
- DECREASE / INCREASE: removed underestimate/overestimate (prediction error is
  not a directional quantity change). "cost decreased/increased" still map to
  the directional dimensions.
- CAUSE: removed create/created (production != causation). "caused X" remains
  {CAUSE}.

Intentionally added (not repair but deliberate, documented vocabulary):

- Everyday companion vocabulary (increment 168, semantic recall): a small
  bilingual set so a Spanish memory and an English question meet on the same
  canonical token. "wrong/equivocado" -> WRONG, "build/construir" -> BUILD,
  "learn/aprender" -> LEARN, "viaje/travel" -> TRAVEL, "contradiga/challenge"
  -> CHALLENGE, "recuerde/remember" -> REMEMBER, "compañero/companion" ->
  COMPANION, "propósito/proyecto/purpose" -> PURPOSE, plus a few everyday
  Spanish forms of the existing dimensions. English "create/created" stay
  unmapped (matter preservation); only "crear/creando" (Spanish) resolve to
  BUILD in the companion sense.

Intentionally NOT repaired (deferred):

- FAIL 'lost': ambiguous without context ("lost the key" vs "lost the contract"
  = genuine failure). Left untouched.
- SAFE synonym set (reliable/stable/secure/dependable...): verified, no
  demonstrable false positive.
"""
from jarvis.domain.services.abstraction import conceptual_tokens, episode_signature, valence


def _sig(text: str) -> set[str]:
    return set(episode_signature(text))


# ---------------------------------------------------------------------------
# Polarity regression (previous gate must remain intact)
# ---------------------------------------------------------------------------


def test_supplier_delivered_is_matter_neutral() -> None:
    assert _sig("supplier delivered") == {"DELIVER"}
    assert valence("supplier delivered") == "neutral"


def test_delivered_on_time_keeps_matter() -> None:
    assert _sig("supplier delivered on time") == {"DELIVER", "TIME"}


def test_failed_to_deliver_negative() -> None:
    assert _sig("supplier failed to deliver") == {"DELIVER", "FAIL"}
    assert valence("supplier failed to deliver") == "negative"


def test_succeeded_in_delivering_positive_preserves_matter() -> None:
    sig = _sig("supplier succeeded in delivering")
    assert sig == {"DELIVER", "SUCCEED"}
    assert valence("supplier succeeded in delivering") == "positive"
    assert sig != _sig("supplier failed to deliver"), "outcome must not merge matter"


# ---------------------------------------------------------------------------
# DELIVER contamination
# ---------------------------------------------------------------------------


def test_give_does_not_absorb_into_deliver() -> None:
    for text in ("gave support", "gave a quote", "gave my word"):
        sig = _sig(text)
        assert "DELIVER" not in sig, f"{text!r} must not be {sig}"


def test_gave_forms_are_unmapped_after_removal() -> None:
    assert _sig("gave support") == set()
    assert _sig("gave a quote") == set()
    assert _sig("gave my word") == set()


def test_deliver_lexicon_still_recognised() -> None:
    for text in (
        "supplier delivered",
        "the vendor supplied the goods",
        "they provided the report",
        "the seller sent the package",
        "we shipped the order",
    ):
        assert "DELIVER" in _sig(text), f"DELIVER missing for {text!r}"


# ---------------------------------------------------------------------------
# TIME / estimate contamination
# ---------------------------------------------------------------------------


def test_estimated_cost_stays_cost_only() -> None:
    assert _sig("estimated cost") == {"COST"}


def test_estimate_does_not_inject_time() -> None:
    assert "TIME" not in _sig("estimated cost")
    assert "TIME" not in _sig("the estimate was wrong")


def test_wrong_is_an_intentional_concept_while_estimate_stays_unmapped() -> None:
    # "wrong" joined the everyday companion vocabulary (WRONG); "estimate" is
    # deliberately absent (prediction error, not matter). Only the former changed.
    assert _sig("the estimate was wrong") == {"WRONG"}
    assert _sig("the estimate") == set()


def test_time_lexicon_still_recognised() -> None:
    for text in ("delivered on time", "the deadline passed", "the schedule slipped"):
        assert "TIME" in _sig(text), f"TIME missing for {text!r}"


# ---------------------------------------------------------------------------
# DECREASE / INCREASE contamination
# ---------------------------------------------------------------------------


def test_under_over_estimate_are_not_directional() -> None:
    assert "DECREASE" not in _sig("underestimated cost")
    assert "INCREASE" not in _sig("overestimated cost")


def test_genuine_directionals_still_map() -> None:
    assert _sig("cost decreased") == {"COST", "DECREASE"}
    assert _sig("cost increased") == {"COST", "INCREASE"}
    assert _sig("prices fell sharply") == {"COST", "DECREASE"}


# ---------------------------------------------------------------------------
# CAUSE contamination
# ---------------------------------------------------------------------------


def test_create_is_not_cause() -> None:
    assert "CAUSE" not in _sig("created value")


def test_causal_language_still_maps() -> None:
    assert _sig("caused the problem") == {"CAUSE"}
    assert "CAUSE" in _sig("the storm caused the delay")


# ---------------------------------------------------------------------------
# FAIL 'lost' — documented deferral (no change)
# ---------------------------------------------------------------------------


def test_lost_is_left_touched_and_documented() -> None:
    # Ambiguous without context: 'lost the contract' is genuine failure while
    # 'lost the key' is not. No deterministic repair without contextual
    # inference -> deferred, mapping untouched.
    assert _sig("lost the key") == {"FAIL"}
    assert _sig("they lost the contract") == {"FAIL"}
    assert valence("they lost the contract") == "negative"


# ---------------------------------------------------------------------------
# False-merge / vocabulary regression
# ---------------------------------------------------------------------------


def test_existing_dimensions_keep_their_signatures() -> None:
    expected = {
        "supplier keeps promising delivery dates that fail": {
            "DELIVER", "TIME", "FAIL", "PROMISE",
        },
        "we bought the parts and sold them": {"COST"},
        "she vowed to improve": {"PROMISE", "INCREASE"},
        "cost decreased": {"COST", "DECREASE"},
        "cost increased": {"COST", "INCREASE"},
        "caused the problem": {"CAUSE"},
        "caused a crisis": {"CAUSE"},
        "they request a refund": {"REQUEST"},
        "she decided to accept": {"DECIDE"},
        "prevent the accident": {"PREVENT"},
        "the risk is high": {"RISK"},
        "the system is safe": {"SAFE"},
    }
    for text, want in expected.items():
        assert _sig(text) == want, f"{text!r}: got {_sig(text)}, want {want}"


def test_conceptual_tokens_reflect_signature() -> None:
    assert conceptual_tokens("estimated cost") == frozenset({"COST"})
    assert conceptual_tokens("gave my word") == frozenset()
    assert conceptual_tokens("underestimated cost") == frozenset({"COST"})