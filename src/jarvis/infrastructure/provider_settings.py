"""ProviderSettings: how to reach one language-model provider (Vision §32).

A plain config object -- provider name, model, endpoint, credentials -- so the
choice of LLM is data, not code. The developer's requirement: not a fixed set of
big providers, but *any* OpenAI-compatible endpoint, including local SLMs. That is
exactly what this expresses: point `base_url` at Groq, xAI/Grok, DeepSeek,
Moonshot/Kimi, OpenRouter, Together, a local Ollama or LM Studio, or anything else
that speaks the same API.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderSettings:
    """Everything needed to build a `LanguageModel` for one provider."""

    provider: str  # a registered name (e.g. "groq", "ollama", "openai-compatible")
    model: str  # the model id to request (e.g. "llama-3.3-70b", "deepseek-chat")
    base_url: str | None = None  # overrides the provider's default endpoint
    api_key: str | None = None  # bearer credential; omit for keyless local SLMs
    timeout: float = 30.0
    temperature: float = 0.0
    # A generous default output budget: reasoning models (e.g. gpt-oss) spend part of it
    # on hidden reasoning, and a small budget leaves empty content on long inputs, so this
    # is deliberately roomy rather than the provider's tiny default.
    max_tokens: int = 3072
    # Optional reasoning budget for reasoning models (e.g. gpt-oss "low"/"medium"/"high").
    # Sent only when set, so it stays provider-agnostic; "low" makes such models reliably
    # return content (not spend it all on hidden reasoning) and uses far fewer tokens.
    reasoning_effort: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SttSettings:
    """Everything needed to build the ear for one speech-to-text provider."""

    provider: str  # a registered name (e.g. "openai", "groq", "openai-compatible")
    model: str  # the transcription model id (e.g. "whisper-1", "whisper-large-v3")
    base_url: str | None = None  # overrides the provider's default endpoint
    api_key: str | None = None  # bearer credential; omit for keyless local engines
    timeout: float = 30.0


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenBotSettings:
    """Everything needed to build the OpenBot execution adapter (Increment 161).

    OpenBot is an optional external computer/browser execution environment.  The
    endpoint is the AG-UI base URL of a running OpenBot Bot (or the deployment's
    own endpoint); configuration alone never makes the capability live -- the
    adapter must actually reach the endpoint for ``can_do`` to report it usable.
    """

    endpoint: str  # e.g. "http://localhost:4600"
    agent_token: str | None = None  # the AGENT_TOOL_TOKEN the server expects
    timeout: float = 120.0
