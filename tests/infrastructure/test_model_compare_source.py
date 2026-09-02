"""RegistryModelComparator: blind model comparison, tested fully offline (D8).

Models are injected as stub :class:`LanguageModel` implementations; no socket is
ever touched. The comparator gathers replies as ModelRuns, never ranks or verdicts
(D6), and a failing or unknown model raises honestly rather than fabricating.
"""

from __future__ import annotations

import pytest

from jarvis import Jarvis
from jarvis.domain.services.model_compare import ModelComparator, ModelRun
from jarvis.infrastructure.model_compare_source import (
    RegistryModelComparator,
    build_model_compare_source,
)
from jarvis.infrastructure.scripted_language_model import ScriptedLanguageModel


def _models() -> dict[str, ScriptedLanguageModel]:
    return {
        "alpha": ScriptedLanguageModel({"q": "alpha says yes"}, default="empty"),
        "beta": ScriptedLanguageModel({"q": "beta says no"}, default="empty"),
    }


class TestCompare:
    def test_compares_all_configured_models(self) -> None:
        comparator = RegistryModelComparator(_models())
        runs = comparator.compare("the q problem")
        assert len(runs) == 2
        by_model = {run.model: run.response for run in runs}
        assert by_model["alpha"] == "alpha says yes"
        assert by_model["beta"] == "beta says no"

    def test_can_select_a_subset_of_models(self) -> None:
        comparator = RegistryModelComparator(_models())
        runs = comparator.compare("the q problem", models=("alpha",))
        assert [run.model for run in runs] == ["alpha"]

    def test_unknown_model_raises_a_clear_error(self) -> None:
        comparator = RegistryModelComparator(_models())
        with pytest.raises(ValueError) as exc:
            comparator.compare("q", models=("nope",))
        assert "unknown comparison model" in str(exc.value)
        assert "alpha" in str(exc.value)

    def test_a_failing_model_raises_honestly(self) -> None:
        class _Broken:
            def complete(self, prompt: str) -> str:
                raise RuntimeError("provider down")

        comparator = RegistryModelComparator({
            "alpha": _Broken(),  # type: ignore[arg-type]
            "beta": ScriptedLanguageModel({"q": "ok"}),
        })
        with pytest.raises(RuntimeError) as exc:
            comparator.compare("q", models=("alpha",))
        assert "comparison model 'alpha' failed" in str(exc.value)

    def test_an_empty_reply_is_kept_as_is(self) -> None:
        comparator = RegistryModelComparator({
            "alpha": ScriptedLanguageModel({"q": ""}, default="x"),
        })
        runs = comparator.compare("other")
        assert len(runs) == 1
        assert runs[0].response == "x"

    def test_requires_at_least_one_model(self) -> None:
        with pytest.raises(ValueError):
            RegistryModelComparator({})


class TestAgainstProtocol:
    def test_adapts_to_the_model_comparator_seam(self) -> None:
        comparator = RegistryModelComparator(_models())
        assert isinstance(comparator, ModelComparator)


class TestFactory:
    def test_returns_a_source_when_models_are_configured(self) -> None:
        source = build_model_compare_source(_models())
        assert source is not None
        assert len(source.compare("q")) == 2

    def test_returns_none_without_models(self) -> None:
        assert build_model_compare_source() is None
        assert build_model_compare_source({}) is None


class TestJarvisIntegration:
    def test_jarvis_has_no_comparator_by_default(self) -> None:
        jarvis = Jarvis()
        assert jarvis.model_compare is None
        with pytest.raises(RuntimeError):
            jarvis.compare_models("anything")

    def test_jarvis_uses_the_wired_comparator(self) -> None:
        comparator = RegistryModelComparator(_models())  # type: ignore[arg-type]
        jarvis = Jarvis(model_compare=comparator)
        runs = jarvis.compare_models("the q problem")
        assert isinstance(runs[0], ModelRun)
        assert len(runs) == 2
        assert runs[0].model == "alpha"