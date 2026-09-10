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
            ("escribe un archivo que diga hola", ConversationIntent.ACT),
            ("envía un correo a los invitados", ConversationIntent.ACT),
            ("write a file with the plan", ConversationIntent.ACT),
            ("Recuerda que prefiero trabajar por la noche.", ConversationIntent.REMEMBER),
            ("Estoy pensando en cambiar la arquitectura.", ConversationIntent.STATEMENT),
            ("¿Crees que debería?", ConversationIntent.STATEMENT),
            ("¿Por qué?", ConversationIntent.STATEMENT),
        ],
    )
    def test_reads_the_intent(self, text: str, intent: ConversationIntent) -> None:
        assert classify(text) == intent


class TestActCues:
    """The ACT intent: conservative material directives, never free-form statements."""

    @pytest.mark.parametrize(
        "text",
        [
            "escríbeme un resumen en notas.md",
            "crea una nota de la reunión",
            "guarda esto en mis notas",
            "ejecuta las pruebas del proyecto",
            "lee el archivo config.json",
            "borra el archivo temporal.txt",
            "elimina la entrada duplicada",
            "create a note about the meeting",
            "save this to my notes",
            "send an email to the team",
            "run the project tests",
            "read the config file",
            "look at the latest report",
        ],
    )
    def test_a_material_directive_is_an_act(self, text: str) -> None:
        assert classify(text) is ConversationIntent.ACT

    @pytest.mark.parametrize(
        "text",
        [
            "creo que el plan es bueno",
            "voy a escribir un libro sobre esto",
            "el correo ya se envió ayer",
            "quiero que alguien revise el informe",
            "the email was already sent",
            "i believe the plan is good",
            "she looked at the report yesterday",
        ],
    )
    def test_free_form_statements_are_not_acts(self, text: str) -> None:
        assert classify(text) is ConversationIntent.STATEMENT

    @pytest.mark.parametrize(
        "text",
        ["recuerda que prefiero trabajar por la noche", "remember that i like tea"],
    )
    def test_remember_dominates_an_act(self, text: str) -> None:
        assert classify(text) is ConversationIntent.REMEMBER

    @pytest.mark.parametrize(
        "text",
        ["busca la documentacion sobre sqlite", "check with the ai first"],
    )
    def test_a_consultation_is_an_instruction_not_an_act(self, text: str) -> None:
        assert classify(text) is ConversationIntent.INSTRUCTION


class TestRememberedContent:
    def test_strips_the_leading_cue(self) -> None:
        assert (
            remembered_content("Recuerda que prefiero trabajar por la noche")
            == "prefiero trabajar por la noche"
        )

    def test_falls_back_to_the_whole_message_without_a_cue(self) -> None:
        assert remembered_content("prefiero la noche") == "prefiero la noche"
