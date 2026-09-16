"""Morphology / stemming v1 (Option B) regression tests.

The suffix-stripping stemmer over-consumes e-drop and y->ies roots
("causing" -> "caus", "deliveries" -> "deliveri"). A small explicit lemma
table restores the stripped stem to a lemma already present in CONCEPT_MAP;
the concept assignment still comes from CONCEPT_MAP, so the layer stays
ontology-neutral. Families whose lemma is NOT in CONCEPT_MAP (receive, cancel,
estimate, create, stop, give) deliberately resolve to no concept.
"""
from jarvis.domain.services.abstraction import episode_signature, valence


def _sig(text: str) -> set[str]:
    return set(episode_signature(text))


# ---------------------------------------------------------------------------
# E-drop / plural core (repaired)
# ---------------------------------------------------------------------------


def test_e_drop_families_restored() -> None:
    expected = {
        "causing": {"CAUSE"},
        "securing": {"SAFE"},
        "scheduling": {"TIME"},
        "requiring": {"REQUEST"},
        "pricing": {"COST"},
        "deliveries": {"DELIVER"},
    }
    for word, want in expected.items():
        assert _sig(word) == want, f"{word!r}: got {_sig(word)}, want {want}"


def test_request_family_full_consistency() -> None:
    for form in ("require", "required", "requires", "requiring"):
        assert _sig(form) == {"REQUEST"}, f"{form!r} lost REQUEST"


def test_schedule_family_full_consistency() -> None:
    for form in ("schedule", "scheduled", "schedules", "scheduling"):
        assert _sig(form) == {"TIME"}, f"{form!r} lost TIME"


def test_price_family_full_consistency() -> None:
    for form in ("price", "priced", "prices", "pricing"):
        assert _sig(form) == {"COST"}, f"{form!r} lost COST"


def test_secure_family_full_consistency() -> None:
    for form in ("secure", "secured", "secures", "securing"):
        assert _sig(form) == {"SAFE"}, f"{form!r} lost SAFE"


def test_cause_family_full_consistency() -> None:
    for form in ("cause", "caused", "causes", "causing"):
        assert _sig(form) == {"CAUSE"}, f"{form!r} lost CAUSE"


def test_deliver_family_including_plural() -> None:
    for form in ("deliver", "delivered", "delivering", "delivery", "deliveries"):
        assert _sig(form) == {"DELIVER"}, f"{form!r} lost DELIVER"


# ---------------------------------------------------------------------------
# Ontology neutrality (lemmas without a concept stay concept-less)
# ---------------------------------------------------------------------------


def test_receive_remains_unmapped() -> None:
    assert _sig("receive") == set()
    assert _sig("receiving") == set()


def test_cancel_remains_unmapped() -> None:
    for form in ("canceling", "cancelling", "canceled", "cancelled"):
        assert _sig(form) == set(), f"{form!r} must not become CANCEL"


def test_estimate_remains_unmapped() -> None:
    for form in ("estimate", "estimated", "estimating"):
        assert _sig(form) == set(), f"{form!r} must not become TIME"


def test_create_remains_unmapped() -> None:
    for form in ("create", "created", "creating"):
        assert _sig(form) == set(), f"{form!r} must not become CAUSE"


# ---------------------------------------------------------------------------
# Previous precision repairs preserved
# ---------------------------------------------------------------------------


def test_give_forms_never_deliver() -> None:
    for form in ("give", "gave", "given", "giving"):
        assert "DELIVER" not in _sig(form), f"{form!r} must not be DELIVER"


def test_under_over_estimate_never_directional() -> None:
    assert "DECREASE" not in _sig("underestimated")
    assert "INCREASE" not in _sig("overestimated")
    assert _sig("underestimated cost") == {"COST"}
    assert _sig("overestimated cost") == {"COST"}


def test_estimated_cost_stays_cost_only() -> None:
    assert _sig("estimated cost") == {"COST"}


def test_created_never_cause() -> None:
    assert _sig("created value") == set()
    assert _sig("creating") == set()


# ---------------------------------------------------------------------------
# Polarity regression
# ---------------------------------------------------------------------------


def test_polarity_axis_unchanged() -> None:
    assert _sig("supplier delivered") == {"DELIVER"}
    assert valence("supplier delivered") == "neutral"
    assert _sig("supplier failed to deliver") == {"DELIVER", "FAIL"}
    assert valence("supplier failed to deliver") == "negative"
    assert _sig("supplier succeeded in delivering") == {"DELIVER", "SUCCEED"}
    assert valence("supplier succeeded in delivering") == "positive"
    assert _sig("supplier did not fail to deliver") == {"DELIVER", "FAIL"}
    assert valence("supplier did not fail to deliver") == "positive"


def test_cross_outcome_matter_separate() -> None:
    assert _sig("supplier failed to deliver") != _sig("supplier succeeded in delivering")


# ---------------------------------------------------------------------------
# Semantic recall: shared matter preserved across morphology
# ---------------------------------------------------------------------------


def test_causing_preserves_cause_matter_for_recall() -> None:
    assert _sig("the storm caused delays") == _sig("the storm causing delays")
    assert _sig("the storm causing delays") == {"TIME", "CAUSE"}


# ---------------------------------------------------------------------------
# Explicitly deferred families (existing behaviour pinned, no change)
# ---------------------------------------------------------------------------


def test_stopping_deferred_lexical_issue() -> None:
    # 'stop' is not a CONCEPT_MAP lemma (only 'stopped' is exact) -> deferred.
    assert _sig("stopping") == set()
    assert _sig("stopped") == {"PREVENT"}


def test_bring_family_deferred() -> None:
    # 'bring'/'bringing' have no lemma entry; 'brought' is exact -> deferred.
    assert _sig("bring") == set()
    assert _sig("bringing") == set()
    assert _sig("brought") == {"DELIVER"}


def test_lead_family_unchanged_and_undocumented() -> None:
    # Existing over-stemming ('leading' -> CAUSE) is untouched by the lemma
    # table; the repair must not acquire additional false mappings.
    assert _sig("leading") == {"CAUSE"}
    assert "RECEIVE" not in _sig("leading")
    assert _sig("leadership") == set()