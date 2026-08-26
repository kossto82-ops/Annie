"""The reply voice: rephrase a decided reply in the companion's language (§40, §38).

Presentation only — offline it changes nothing; with a model it rephrases but never
changes the meaning, and any model failure falls back to the original reply.
"""

from __future__ import annotations

from jarvis.infrastructure.llm_response_renderer import LlmResponseRenderer
from jarvis.infrastructure.response_renderer import IdentityRenderer


class _FakeModel:
    def __init__(self, completion: str, *, raises: bool = False) -> None:
        self._completion = completion
        self._raises = raises
        self.prompt: str | None = None

    def complete(self, prompt: str) -> str:
        self.prompt = prompt
        if self._raises:
            raise RuntimeError("provider down")
        return self._completion


class TestIdentityRenderer:
    def test_it_returns_the_reply_unchanged(self) -> None:
        assert IdentityRenderer().phrase("I hold X with high confidence.", like="dime X") == (
            "I hold X with high confidence."
        )


class TestLlmResponseRenderer:
    def test_it_rephrases_via_the_model(self) -> None:
        model = _FakeModel("Mantengo X con alta confianza.")
        rendered = LlmResponseRenderer(model).phrase(
            "I hold X with high confidence.", like="dime sobre X"
        )
        assert rendered == "Mantengo X con alta confianza."
        # The user's message is passed so the model can match its language.
        assert model.prompt is not None
        assert "dime sobre X" in model.prompt

    def test_a_model_error_falls_back_to_the_original(self) -> None:
        model = _FakeModel("", raises=True)
        reply = "I don't have enough evidence yet."
        assert LlmResponseRenderer(model).phrase(reply, like="hola") == reply

    def test_empty_model_output_falls_back_to_the_original(self) -> None:
        reply = "Noted."
        assert LlmResponseRenderer(_FakeModel("   ")).phrase(reply, like="ok") == reply

    def test_an_empty_reply_is_returned_as_is(self) -> None:
        assert LlmResponseRenderer(_FakeModel("x")).phrase("", like="ok") == ""
