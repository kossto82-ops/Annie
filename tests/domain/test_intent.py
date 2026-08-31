"""Conversational intent classification: not every message is knowledge (Vision §5)."""

from __future__ import annotations

import pytest

from jarvis.domain.conversation.intent import (
    ConversationIntent,
    classify,
    remembered_content,
)


class TestClassify:
    @pytest.mark.parametrize(
        ("text", "intent"),
        [
            ("Hola Jarvis!", ConversationIntent.GREETING),
            ("buenas", ConversationIntent.GREETING),
            ("hi there", ConversationIntent.GREETING),
            ("¿Qué tal?", ConversationIntent.SMALLTALK),
            ("how are you?", ConversationIntent.SMALLTALK),
            ("No funcionas muy bien.", ConversationIntent.FEEDBACK),
            ("Deberías ser capaz de mantener una conversación.", ConversationIntent.FEEDBACK),
            ("estoy frustrado contigo", ConversationIntent.FEEDBACK),
            ("pues habla con la IA para estar seguro", ConversationIntent.INSTRUCTION),
            ("busca información sobre X", ConversationIntent.INSTRUCTION),
            ("Recuerda que prefiero trabajar por la noche.", ConversationIntent.REMEMBER),
            ("Estoy pensando en cambiar la arquitectura.", ConversationIntent.STATEMENT),
            ("¿Crees que debería?", ConversationIntent.STATEMENT),
            ("¿Por qué?", ConversationIntent.STATEMENT),
        ],
    )
    def test_reads_the_intent(self, text: str, intent: ConversationIntent) -> None:
        assert classify(text) == intent


class TestRememberedContent:
    def test_strips_the_leading_cue(self) -> None:
        assert (
            remembered_content("Recuerda que prefiero trabajar por la noche")
            == "prefiero trabajar por la noche"
        )

    def test_falls_back_to_the_whole_message_without_a_cue(self) -> None:
        assert remembered_content("prefiero la noche") == "prefiero la noche"
