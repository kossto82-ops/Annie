"""ScriptedLanguageModel: a stub LanguageModel with no network (Vision §32).

Proves the whole LLM→perception seam end to end without a live API: it returns
canned completions chosen by matching a substring of the prompt. This is what
tests and examples use, and it is the reference for what a real provider adapter
must produce -- a JSON array of claims (see `LlmPerception`). Real providers wrap
their SDK behind the same `LanguageModel` interface; nothing else changes.
"""

from __future__ import annotations


class ScriptedLanguageModel:
    """Returns a scripted completion for a prompt, or a default (no I/O)."""

    def __init__(
        self, responses: dict[str, str] | None = None, *, default: str = "[]"
    ) -> None:
        # Maps a substring-to-look-for-in-the-prompt -> the completion to return.
        self._responses = dict(responses or {})
        self._default = default

    def complete(self, prompt: str) -> str:
        for needle, response in self._responses.items():
            if needle in prompt:
                return response
        return self._default
