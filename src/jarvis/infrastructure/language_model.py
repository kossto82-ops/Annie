"""LanguageModel: the swappable seam to any LLM provider (Vision §32, §38).

This is the single, minimal interface every provider implements -- "prompt in,
text out". An OpenAI client, an Anthropic client, a local Ollama model, or a test
stub are all just `LanguageModel`s. Nothing above this line knows which one it is,
so switching provider or model is a composition-root / config change, never a
change to perception or the cognitive core.

Deliberately tiny: richer capabilities (streaming, tools, JSON mode) are provider
details that live *inside* an implementation, behind this same one method. The
boundary of Vision §38 is upheld one level up, in `LlmPerception`: whatever text a
model returns becomes *candidate evidence*, never a decision.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LanguageModel(Protocol):
    """Any language model: it turns a prompt into text."""

    def complete(self, prompt: str) -> str:
        """Return the model's text completion of ``prompt``."""
        ...
