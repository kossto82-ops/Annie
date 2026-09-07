"""The document-edit seam, tested fully offline (Vision §38, D8).

An editor only *proposes* the revised text of a document; deciding, applying and
diffing stay in the caller. These tests pin the honest boundaries: the offline
editor declines everything, the LLM-backed editor declines on provider failure or
an empty/fenceless reply, strips a markdown fence, and never invents a change note.
"""

from __future__ import annotations

from jarvis.domain.retrieval.document_editor import DocumentEditor
from jarvis.infrastructure.llm_document_editor import LlmDocumentEditor
from jarvis.infrastructure.perceiver_factory import build_document_editor
from jarvis.infrastructure.scripted_language_model import ScriptedLanguageModel
from jarvis.infrastructure.silent_document_editor import SilentDocumentEditor


class _FailingModel:
    def complete(self, prompt: str) -> str:
        raise RuntimeError("provider unavailable")


class _RecordingModel:
    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._reply


class TestDocumentEditorSeam:
    def test_silent_editor_declines_every_rewrite(self) -> None:
        editor = SilentDocumentEditor()
        assert editor.propose("hello", "make it friendlier") is None
        assert isinstance(editor, DocumentEditor)

    def test_llm_editor_is_a_document_editor(self) -> None:
        assert isinstance(LlmDocumentEditor(ScriptedLanguageModel()), DocumentEditor)
        assert isinstance(SilentDocumentEditor(), DocumentEditor)

    def test_llm_editor_proposes_the_model_reply_as_full_text(self) -> None:
        editor = LlmDocumentEditor(ScriptedLanguageModel(default="Revised document."))
        assert editor.propose("Original.", "revise") == "Revised document."

    def test_llm_editor_strips_an_outer_fence(self) -> None:
        editor = LlmDocumentEditor(
            ScriptedLanguageModel(default="```text\nfenced reply\n```")
        )
        assert editor.propose("a", "change it") == "fenced reply"

    def test_llm_editor_declines_an_empty_or_blank_reply(self) -> None:
        for junk in ("", "   ", "\n\n"):
            editor = LlmDocumentEditor(ScriptedLanguageModel(default=junk))
            assert editor.propose("a", "change it") is None

    def test_llm_editor_declines_on_provider_failure(self) -> None:
        editor = LlmDocumentEditor(_FailingModel())
        assert editor.propose("a", "change it") is None

    def test_llm_editor_declines_without_content_to_change(self) -> None:
        editor = LlmDocumentEditor(ScriptedLanguageModel(default="yes"))
        assert editor.propose("   ", "change") is None
        assert editor.propose("text", "   ") is None

    def test_the_prompt_carries_the_document_and_instruction(self) -> None:
        model = _RecordingModel(reply="done")
        editor = LlmDocumentEditor(model)
        editor.propose("the doc", "add a title")
        assert len(model.prompts) == 1
        prompt = model.prompts[0]
        assert "<document>\nthe doc\n</document>" in prompt
        assert "<edit>add a title</edit>" in prompt

    def test_build_document_editor_offline_is_silent(self) -> None:
        assert isinstance(build_document_editor("keyword"), SilentDocumentEditor)
        assert isinstance(build_document_editor("scripted"), SilentDocumentEditor)

    def test_build_document_editor_real_provider_is_llm_backed(self) -> None:
        editor = build_document_editor("ollama", "llama3")
        assert isinstance(editor, LlmDocumentEditor)