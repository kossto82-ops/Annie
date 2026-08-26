"""A generic OpenAI-compatible LanguageModel (Vision §32).

One adapter for the whole family of providers that speak the OpenAI chat API --
which is nearly all of them, cloud and local: OpenAI, Groq, xAI/Grok, DeepSeek,
Moonshot/Kimi, OpenRouter, Together, a local Ollama or LM Studio, and more. A new
provider is a `ProviderSettings` (a base_url + model), never new code.

The actual HTTP send is a `Transport` (a callable) so the network stays at the
edge and out of tests: the default uses the standard library (`urllib`, no
dependency); tests inject a fake transport and never touch the network. Whatever
the model returns is only ever *text* here -- turning it into evidence, and never
into a decision, is `LlmPerception`'s job (Vision §38, D33).
"""

from __future__ import annotations

import json
from typing import Any, Protocol, cast

from jarvis.infrastructure.provider_settings import ProviderSettings


class Transport(Protocol):
    """Sends an HTTP POST and returns the response body as text."""

    def __call__(self, url: str, headers: dict[str, str], body: bytes) -> str:
        ...


def _urllib_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> str:
    import urllib.request

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload: bytes = response.read()
    return payload.decode("utf-8")


class OpenAiCompatibleModel:
    """Talks to any OpenAI-compatible chat-completions endpoint."""

    def __init__(
        self, settings: ProviderSettings, transport: Transport | None = None
    ) -> None:
        if not settings.base_url:
            raise ValueError("an OpenAI-compatible provider needs a base_url")
        self._settings = settings
        self._base_url = settings.base_url
        self._transport: Transport = transport or self._default_transport

    def _default_transport(self, url: str, headers: dict[str, str], body: bytes) -> str:
        return _urllib_transport(url, headers, body, self._settings.timeout)

    def complete(self, prompt: str) -> str:
        settings = self._settings
        url = f"{self._base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if settings.api_key:  # local SLMs may need no key
            headers["Authorization"] = f"Bearer {settings.api_key}"
        body = json.dumps(
            {
                "model": settings.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": settings.temperature,
            }
        ).encode("utf-8")
        return _extract_message(self._transport(url, headers, body))


def _extract_message(raw: str) -> str:
    """Pull the assistant's text out of an OpenAI-style response, or '' if absent."""
    try:
        data: Any = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    choices: Any = cast("dict[str, Any]", data).get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first: Any = cast("list[Any]", choices)[0]
    if not isinstance(first, dict):
        return ""
    message: Any = cast("dict[str, Any]", first).get("message")
    if not isinstance(message, dict):
        return ""
    content: Any = cast("dict[str, Any]", message).get("content")
    return content if isinstance(content, str) else ""
