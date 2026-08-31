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

    def test_prompt_leak_falls_back_to_the_decided_reply(self) -> None:
        source = "Hi — good to see you. What's on your mind?"
        leaked = (
            'The user message is "Hola Jarvis" which is Spanish for "Hello Jarvis". '
            f'The assistant reply is "{source}". Hola — ¿qué tal?'
        )
        assert LlmResponseRenderer(_FakeModel(leaked)).phrase(source, like="Hola Jarvis") == source

    def test_duplicated_rendering_falls_back_to_the_decided_reply(self) -> None:
        source = "Tell me what is happening and I will help."
        duplicated = "Cuéntame qué ocurre y te ayudaré. Cuéntame qué ocurre y te ayudaré."
        assert LlmResponseRenderer(_FakeModel(duplicated)).phrase(source, like="Hola") == source

    def test_the_exact_reported_renderer_leak_falls_back(self) -> None:
        source = "Hi — good to see you. What's on your mind?"
        leaked = (
            'The user message is "Hola Jarvis!" which is Spanish for "Hello Jarvis!"\n'
            'The user message is "Hola Jarvis!" which is Spanish for "Hello Jarvis!"\n'
            "Hola — me alegra verte. ¿Qué tienes en mente?"
            "Hola — me alegra verte. ¿Qué tienes en mente?"
        )
        assert LlmResponseRenderer(_FakeModel(leaked)).phrase(source, like="Hola Jarvis!") == source


class _StreamingModel:
    """A model that streams fixed deltas (and can complete for the fallback)."""

    def __init__(self, deltas: list[str]) -> None:
        self._deltas = deltas

    def complete(self, prompt: str) -> str:
        return "".join(self._deltas)

    def stream(self, prompt: str):  # type: ignore[no-untyped-def]
        yield from self._deltas


class TestPhraseStream:
    def test_identity_streams_the_reply_once(self) -> None:
        assert list(IdentityRenderer().phrase_stream("Noted.", like="ok")) == ["Noted."]

    def test_llm_streams_model_deltas(self) -> None:
        model = _StreamingModel(["Man", "tengo", " X"])
        pieces = list(LlmResponseRenderer(model).phrase_stream("I hold X.", like="dime"))
        assert "".join(pieces) == "Mantengo X"

    def test_llm_falls_back_to_one_phrasing_without_streaming(self) -> None:
        # _FakeModel has no .stream -> a single phrased chunk.
        pieces = list(LlmResponseRenderer(_FakeModel("Hola")).phrase_stream("Hi", like="es"))
        assert pieces == ["Hola"]

    def test_streamed_prompt_leak_is_never_yielded(self) -> None:
        source = "Hi — good to see you."
        leaked = [
            "The user's message is in Spanish. ",
            "The assistant's reply is in English. Hola — qué bueno verte.",
        ]
        pieces = list(LlmResponseRenderer(_StreamingModel(leaked)).phrase_stream(source, "Hola"))
        assert pieces == [source]

    def test_streamed_duplicate_is_never_yielded(self) -> None:
        source = "Tell me more."
        repeated = ["Cuéntame más. ", "Cuéntame más."]
        pieces = list(LlmResponseRenderer(_StreamingModel(repeated)).phrase_stream(source, "Hola"))
        assert pieces == [source]
