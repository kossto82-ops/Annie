"""Offline tests for the decided-script format and the charitable compiler (F6c).

Covers the domain decided-script value object (parse/validate the
``tool key="value"`` grammar without executing) and the deterministic charitable
compiler that turns the small, unambiguous instruction envelopes into a
decided-script so the *offline* executor can run scripted acts with no free-text
LLM. Compilation never emits destructive/external steps.
"""

from __future__ import annotations

import pytest

from jarvis.domain.services.charitable_instruction import compile_charitable_instruction
from jarvis.domain.value_objects.decided_script import DecidedScript


class TestDecidedScript:
    def test_parses_a_multi_line_script_in_order(self) -> None:
        script = DecidedScript.parse(
            'filesystem operation=write path="notas.txt" content="hola"\n'
            'echo text="listo con espacios"'
        )
        assert script.errors == ()
        assert [step.tool for step in script.steps] == ["filesystem", "echo"]
        first = script.steps[0]
        assert first.as_call() == {
            "operation": "write",
            "path": "notas.txt",
            "content": "hola",
        }

    def test_quote_aware_values_round_trip(self) -> None:
        script = DecidedScript.parse(
            'filesystem operation=write path="a b.txt" content="dijo \\"hola\\""'
        )
        assert script.errors == ()
        assert script.steps[0].as_call() == {
            "operation": "write",
            "path": "a b.txt",
            'content': 'dijo "hola"',
        }

    def test_malformed_lines_are_reported_honestly_and_skipped(self) -> None:
        script = DecidedScript.parse(
            'filesystem operation=write path="a.txt" content="ok"\n'
            'not-a-tool-call\n'
            'echo bareword'
        )
        # An arg-less single word parses (a call to a then-unknown tool); the
        # bare value after a tool name is malformed, so that line is skipped and
        # honestly reported.
        assert [step.tool for step in script.steps] == [
            "filesystem",
            "not-a-tool-call",
        ]
        assert script.errors
        assert any("malformed" in error for error in script.errors)

    def test_blank_and_comment_lines_are_skipped(self) -> None:
        script = DecidedScript.parse("# plan\n\necho text=done\n")
        assert script.errors == ()
        assert len(script.steps) == 1

    def test_empty_input_yields_an_empty_script(self) -> None:
        script = DecidedScript.parse("   \n\n")
        assert script.is_empty
        assert script.errors == ()

    def test_unknown_tools_are_listed_honestly(self) -> None:
        script = DecidedScript.parse("filesystem operation=read path=a\nexternal x=1")
        assert script.unknown_tools(("filesystem", "echo")) == ("external",)


class TestCharitableCompiler:
    def test_es_write_with_content_compiles(self) -> None:
        script = compile_charitable_instruction(
            "escribe un archivo notas.txt con Hola mundo"
        )
        assert script == 'filesystem operation=write path="notas.txt" content="Hola mundo"'

    def test_es_write_without_content_compiles_empty(self) -> None:
        assert compile_charitable_instruction("crea un archivo vacio.txt") == (
            'filesystem operation=write path="vacio.txt" content=""'
        )

    def test_es_write_with_detailed_separator_compiles(self) -> None:
        assert compile_charitable_instruction(
            "escribe un archivo plan.md con el contenido Revisión completa"
        ) == 'filesystem operation=write path="plan.md" content="Revisión completa"'

    def test_en_write_compiles(self) -> None:
        assert compile_charitable_instruction(
            "write a file notes.txt with the plan"
        ) == 'filesystem operation=write path="notes.txt" content="the plan"'
        assert compile_charitable_instruction(
            "create file draft.txt containing ver. 2"
        ) == 'filesystem operation=write path="draft.txt" content="ver. 2"'

    def test_read_envelope_compiles(self) -> None:
        assert compile_charitable_instruction("lee el archivo notas.txt") == (
            'filesystem operation=read path="notas.txt"'
        )
        assert compile_charitable_instruction("read the file plan.md") == (
            'filesystem operation=read path="plan.md"'
        )

    def test_echo_envelope_compiles(self) -> None:
        assert compile_charitable_instruction("dime listo con todo") == (
            'echo text="listo con todo"'
        )

    def test_compiled_script_round_trips_through_the_grammar(self) -> None:
        script = compile_charitable_instruction(
            'escribe un archivo a.txt con dijo "hola"'
        )
        assert script is not None
        parsed = DecidedScript.parse(script)
        assert parsed.errors == ()
        assert parsed.steps[0].as_call() == {
            "operation": "write",
            "path": "a.txt",
            "content": 'dijo "hola"',
        }

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "escribe un archivo que diga hola",  # no filename-like path
            "escribe un archivo con contenido X",  # still no filename
            "podrías ir a la tienda por favor",  # ambiguous material request
            "¿puedes escribir un correo?",  # a question, not a decided envelope
            "quita el archivo notas.txt",  # destructive — never compiled
            "envía un correo a alguien",  # external — never compiled
        ],
    )
    def test_unambiguous_requests_compile_to_none(self, text: str) -> None:
        assert compile_charitable_instruction(text) is None