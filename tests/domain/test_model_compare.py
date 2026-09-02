"""ModelCompare domain: ModelRun VO + ModelComparator Protocol (Vision §33, §38).

ModelRun is immutable and always names its producing model (provenance). The
comparator gathers candidate replies; it never ranks, verdicts, or writes (D6).
"""

from __future__ import annotations

import pytest

from jarvis.domain.services.model_compare import ModelComparator, ModelRun


class TestModelRun:
    def test_carries_model_and_response(self) -> None:
        run = ModelRun(model="llama-3.3-70b", response="yes, evidence matters")
        assert run.model == "llama-3.3-70b"
        assert run.response.startswith("yes")

    def test_rejects_blank_model(self) -> None:
        with pytest.raises(ValueError):
            ModelRun(model="  ", response="x")

    def test_is_immutable(self) -> None:
        run = ModelRun(model="m", response="r")
        with pytest.raises(AttributeError):
            run.response = "other"  # type: ignore[misc]

    def test_empty_response_stays_an_honest_empty_reply(self) -> None:
        run = ModelRun(model="m", response="")
        assert run.response == ""


class TestModelComparatorProtocol:
    def test_a_comparator_adapts_to_the_seam(self) -> None:
        class _Comparator:
            def compare(self, prompt: str, *, models=None):  # type: ignore[no-untyped-def]
                return (ModelRun(model="m", response=prompt),)

        assert isinstance(_Comparator(), ModelComparator)