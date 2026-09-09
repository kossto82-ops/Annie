"""Honest-silence guardrail tests (Vision §37)."""

from jarvis.infrastructure.guardrail import content_filtered, guard_reply, is_refusal


class TestIsRefusal:
    def test_an_empty_reply_is_not_a_refusal(self) -> None:
        assert is_refusal("") is False
        assert is_refusal("   ") is False

    def test_english_refusal_phrases_are_recognised(self) -> None:
        refusals = [
            "I can't help with that.",
            "i'm sorry, but i can't.",
            "I am unable to help you with this request.",
            "As an AI language model, I cannot comply.",
            "The content has been filtered.",
        ]
        for text in refusals:
            assert is_refusal(text) is True, text

    def test_spanish_refusal_phrases_are_recognised(self) -> None:
        refusals = [
            "No puedo ayudarte con eso.",
            "Lo siento, pero no puedo.",
            "No estoy en condiciones de hacer eso.",
            "No tengo la capacidad de responder.",
        ]
        for text in refusals:
            assert is_refusal(text) is True, text

    def test_an_ordinary_answer_is_not_silenced(self) -> None:
        plain = [
            "Here is what happened in the last quarter.",
            "Can't say for sure, but the numbers suggest growth.",
            "No puedo confirmarlo, pero fue productivo.",
            "Help is available if you ask the perception module.",
        ]
        for text in plain:
            assert is_refusal(text) is False, text


class TestContentFiltered:
    def test_the_structured_signal_is_recognised(self) -> None:
        assert content_filtered("content_filter") is True
        assert content_filtered(None) is False
        assert content_filtered("stop") is False
        assert content_filtered("") is False


class TestGuardReply:
    def test_a_content_filtered_reply_becomes_honest_silence(self) -> None:
        assert guard_reply("irrelevant", finish_reason="content_filter") == ""

    def test_a_textual_refusal_becomes_honest_silence(self) -> None:
        assert guard_reply("I'm sorry, but I can't help with that.") == ""

    def test_a_normal_reply_passes_through(self) -> None:
        assert guard_reply("Everything is fine.") == "Everything is fine."

    def test_an_empty_reply_stays_empty(self) -> None:
        assert guard_reply("") == ""