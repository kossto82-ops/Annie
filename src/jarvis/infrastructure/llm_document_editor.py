"""LlmDocumentEditor: an LLM-backed DocumentEditor (Vision §38, D7).

Asks a `LanguageModel` for the complete revised text of a document, given the
current text and the companion's free-form instruction. It depends only on the
`LanguageModel` Protocol, so any provider (or a test stub) plugs in unchanged.

The §38 boundary holds and is the whole point: the model *proposes* the new text;
it does not decide to write anything. Applying the proposal -- and describing what
changed -- stays in the caller, which derives the note from the real diff. A
provider failure, an empty reply, or an unparseable fence yields no proposal
(honest silence, §37) rather than a fabricated rewrite.
"""

from __future__ import annotations

from jarvis.infrastructure.language_model import LanguageModel

_INSTRUCTIONS = (
    "Rewrite the DOCUMENT below to apply the requested EDIT. Keep everything you "
    "are not asked to change exactly as it is: same words, spelling, formatting, "
    "line breaks and order. Do not summarize, do not add commentary, do not invent "
    "content. Return ONLY the complete revised document, with no preamble, no "
    "explanations and no markdown code fence."
)


class LlmDocumentEditor:
    """Proposes a full rewrite of a document's text via a language model."""

    def __init__(self, model: LanguageModel) -> None:
        self._model = model

    def propose(self, source_text: str, instruction: str) -> str | None:
        text = source_text.strip()
        edit = instruction.strip()
        if not text or not edit:
            return None
        try:
            reply = self._model.complete(
                self._prompt(source_text, instruction)
            )
        except Exception:  # noqa: BLE001 - the external-provider boundary
            return None  # provider failure -> no proposal, never a crash (§37)
        proposal = _strip_fence(reply).strip()
        return proposal or None

    @staticmethod
    def _prompt(source_text: str, instruction: str) -> str:
        return "\n\n".join(
            (
                _INSTRUCTIONS,
                f"<document>\n{source_text}\n</document>",
                f"<edit>{instruction}</edit>",
            )
        )


def _strip_fence(reply: str) -> str:
    """Drop an outer triple-backtick fence, if a model wrapped its answer in one."""
    text = reply.strip()
    if text.startswith("```"):
        first = text.index("\n")
        if first == -1:
            return ""
        last = text.rstrip().rfind("```")
        if last <= first:
            return ""
        return text[first + 1 : last].strip("\n")
    return text