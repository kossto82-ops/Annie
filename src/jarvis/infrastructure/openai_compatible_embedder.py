"""OpenAiCompatibleEmbedder: a TextEmbedder over the OpenAI-style embeddings API.

One adapter for the whole family that speaks ``POST {base_url}/embeddings`` -- which
includes a local ollama (bge-m3 at ``http://localhost:11434/v1``), LM Studio, and the
hosted providers. A new embedding provider is a base_url + model, never new code
(mirrors :class:`OpenAiCompatibleModel`).

The HTTP send is an injectable `Transport`, so the network stays at the edge and out
of tests. Whatever comes back is only ever *vectors* here -- ranking recalled memories
by them, and never deciding anything, is the retriever's job (Vision §38).
"""

from __future__ import annotations

import json
from typing import Any, cast

from jarvis.infrastructure.openai_compatible_model import Transport


def _urllib_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> str:
    import urllib.request

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload: bytes = response.read()
    return payload.decode("utf-8")


class OpenAiCompatibleEmbedder:
    """Embeds text via any OpenAI-compatible ``/embeddings`` endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 60.0,
        transport: Transport | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("an OpenAI-compatible embedder needs a base_url")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._transport: Transport = transport or self._default_transport

    def _default_transport(self, url: str, headers: dict[str, str], body: bytes) -> str:
        return _urllib_transport(url, headers, body, self._timeout)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "User-Agent": "Jarvis/1.0"}
        if self._api_key:  # local models (ollama) may need no key
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        body = json.dumps({"model": self._model, "input": list(texts)}).encode("utf-8")
        raw = self._transport(f"{self._base_url}/embeddings", self._headers(), body)
        vectors = _parse_embeddings(raw)
        if len(vectors) != len(texts):
            raise ValueError(
                f"embedder returned {len(vectors)} vectors for {len(texts)} inputs"
            )
        return vectors


def _parse_embeddings(raw: str) -> tuple[tuple[float, ...], ...]:
    """Pull the vectors out of an OpenAI-style embeddings response, ordered by index."""
    data: Any = json.loads(raw)  # a malformed body raises -> the caller falls back
    if not isinstance(data, dict):
        raise ValueError("embeddings response is not an object")
    items: Any = cast("dict[str, Any]", data).get("data")
    if not isinstance(items, list):
        raise ValueError("embeddings response has no data array")
    rows = cast("list[Any]", items)
    ordered = sorted(rows, key=lambda row: _index_of(row))
    return tuple(_vector_of(row) for row in ordered)


def _index_of(row: Any) -> int:
    if isinstance(row, dict):
        index = cast("dict[str, Any]", row).get("index")
        if isinstance(index, int):
            return index
    return 0


def _vector_of(row: Any) -> tuple[float, ...]:
    if not isinstance(row, dict):
        raise ValueError("embeddings row is not an object")
    vector: Any = cast("dict[str, Any]", row).get("embedding")
    if not isinstance(vector, list) or not vector:
        raise ValueError("embeddings row has no embedding")
    return tuple(float(value) for value in cast("list[Any]", vector))
