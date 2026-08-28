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
from collections.abc import Iterator
from typing import Any, Protocol, cast

from jarvis.infrastructure.provider_settings import ProviderSettings


class Transport(Protocol):
    """Sends an HTTP POST and returns the response body as text."""

    def __call__(self, url: str, headers: dict[str, str], body: bytes) -> str:
        ...


class StreamTransport(Protocol):
    """Sends an HTTP POST and yields the response body's lines as they arrive."""

    def __call__(self, url: str, headers: dict[str, str], body: bytes) -> Iterator[bytes]:
        ...


def _urllib_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> str:
    import urllib.request

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload: bytes = response.read()
    return payload.decode("utf-8")


def _urllib_stream_transport(
    url: str, headers: dict[str, str], body: bytes, timeout: float
) -> Iterator[bytes]:
    import urllib.request

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        yield from response  # the file-like response yields one line at a time


class OpenAiCompatibleModel:
    """Talks to any OpenAI-compatible chat-completions endpoint."""

    def __init__(
        self,
        settings: ProviderSettings,
        transport: Transport | None = None,
        stream_transport: StreamTransport | None = None,
    ) -> None:
        if not settings.base_url:
            raise ValueError("an OpenAI-compatible provider needs a base_url")
        self._settings = settings
        self._base_url = settings.base_url
        self._transport: Transport = transport or self._default_transport
        self._stream_transport: StreamTransport = (
            stream_transport or self._default_stream_transport
        )

    def _default_transport(self, url: str, headers: dict[str, str], body: bytes) -> str:
        return _urllib_transport(url, headers, body, self._settings.timeout)

    def _default_stream_transport(
        self, url: str, headers: dict[str, str], body: bytes
    ) -> Iterator[bytes]:
        return _urllib_stream_transport(url, headers, body, self._settings.timeout)

    def _url(self) -> str:
        return f"{self._base_url.rstrip('/')}/chat/completions"

    def _headers(self) -> dict[str, str]:
        # A real User-Agent is required: some providers front their API with Cloudflare,
        # which blocks the default `Python-urllib` signature with a 403 (error 1010).
        headers = {"Content-Type": "application/json", "User-Agent": "Jarvis/1.0"}
        if self._settings.api_key:  # local SLMs may need no key
            headers["Authorization"] = f"Bearer {self._settings.api_key}"
        return headers

    def _request_body(self, prompt: str, *, stream: bool) -> bytes:
        settings = self._settings
        request_body: dict[str, Any] = {
            "model": settings.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": settings.temperature,
            "max_tokens": settings.max_tokens,
        }
        if settings.reasoning_effort:  # only for reasoning models, when configured
            request_body["reasoning_effort"] = settings.reasoning_effort
        # Always send `stream` explicitly. Omitting it is not safe: some gateways (e.g. an
        # OmniRoute route fronting a streaming provider) default to an SSE body when the flag
        # is absent, which the non-streaming `complete` path cannot json.loads -> empty reply.
        request_body["stream"] = stream
        return json.dumps(request_body).encode("utf-8")

    def complete(self, prompt: str) -> str:
        body = self._request_body(prompt, stream=False)
        return _extract_message(self._transport(self._url(), self._headers(), body))

    def stream(self, prompt: str) -> Iterator[str]:
        """Yield the assistant's reply as content deltas arrive (SSE).

        Parses OpenAI-style ``data:`` lines and yields each ``choices[0].delta.content``.
        Malformed lines are skipped; ``[DONE]`` ends the stream — so a partial or messy
        stream degrades to whatever content did arrive, never an exception mid-reply.
        """
        lines = self._stream_transport(
            self._url(), self._headers(), self._request_body(prompt, stream=True)
        )
        for raw_line in lines:
            piece = _delta_from_sse_line(raw_line)
            if piece:
                yield piece


def _delta_from_sse_line(raw_line: bytes) -> str:
    """The content delta in one SSE line, or '' for keep-alives / non-content lines."""
    try:
        line = raw_line.decode("utf-8").strip()
    except (UnicodeDecodeError, AttributeError):
        return ""
    if not line.startswith("data:"):
        return ""
    data = line[len("data:") :].strip()
    if not data or data == "[DONE]":
        return ""
    try:
        parsed: Any = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(parsed, dict):
        return ""
    choices: Any = cast("dict[str, Any]", parsed).get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first: Any = cast("list[Any]", choices)[0]
    if not isinstance(first, dict):
        return ""
    delta: Any = cast("dict[str, Any]", first).get("delta")
    if not isinstance(delta, dict):
        return ""
    content: Any = cast("dict[str, Any]", delta).get("content")
    return content if isinstance(content, str) else ""


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
