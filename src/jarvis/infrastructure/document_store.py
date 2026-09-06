"""LocalDocumentStore: a file-backed DocumentStore at the edge (project files).

The files store for classified documents: a bounded directory where each document
is kept under its own name — any extension is allowed, so the companion can hand
Jarvis logs, configs, exports, code or manuals. Disk access goes through an
injectable ``io`` driver over raw bytes so offline tests run deterministically
without touching the filesystem (D8). The store only keeps and returns bytes; it
never reasons about them (D6) and never escapes its sandbox (flat names only).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from jarvis.domain.value_objects.document_hit import DocumentHit

DocumentIO = Callable[[str, str, bytes], bytes]
_SEPARATORS = ("/", "\\")

# Tokens shorter than this carry too little signal to rank on (mirrors the lexical
# memory retriever's language-agnostic floor).
_MIN_TOKEN_LEN = 2
_WORD = re.compile(r"\w+")
_SNIPPET_EXPAND_RIGHT = 140
_SNIPPET_LEAD = 60
_ELLIPSIS = "…"


def _tokens(text: str) -> set[str]:
    """The set of scoreable tokens in ``text`` -- lowercased, short ones dropped."""
    return {word for word in _WORD.findall(text.lower()) if len(word) >= _MIN_TOKEN_LEN}


def _relevance(query_tokens: set[str], surface: str) -> float:
    """Fraction of the query's tokens the document's surface shares -- 0.0 when disjoint."""
    if not query_tokens:
        return 0.0
    shared = query_tokens & _tokens(surface)
    return len(shared) / len(query_tokens)


class LocalDocumentStore:
    """A bounded, file-backed store of documents, one file per document."""

    def __init__(
        self,
        root: str | Path,
        io: DocumentIO | None = None,
    ) -> None:
        """Bind the store to a sandbox ``root`` with an injectable ``io`` driver.

        ``io(operation, path, payload)`` mirrors the filesystem protocol over
        bytes: ``read`` returns the file's bytes, ``write`` writes ``payload`` and
        returns ``b""``, ``delete`` removes the file and returns ``b""``, and
        ``list`` returns the sorted document names newline-joined (utf-8).
        Defaults to real disk access through :func:`pathlib`; injecting a fake
        keeps tests offline (D8).
        """
        self._root = Path(root).resolve()
        self._io = io or self._default_io

    # -- filesystem driver ----------------------------------------------------

    def _default_io(self, operation: str, path: str, payload: bytes) -> bytes:
        if operation == "list":
            names = sorted(
                child.name for child in self._root.iterdir() if child.is_file()
            )
            return "\n".join(names).encode("utf-8")
        resolved = (self._root / path).resolve()
        if not resolved.is_relative_to(self._root):
            raise ValueError("path escapes the documents sandbox")
        if operation == "read":
            return resolved.read_bytes()
        if operation == "delete":
            if resolved.exists():
                resolved.unlink()
            return b""
        self._root.mkdir(parents=True, exist_ok=True)
        resolved.write_bytes(payload)
        return b""

    # -- DocumentStore --------------------------------------------------------

    def list_documents(self) -> tuple[str, ...]:
        raw = self._io("list", "", b"")
        if not raw:
            return ()
        return tuple(part for part in raw.decode("utf-8").split("\n") if part)

    def read_document(self, name: str) -> bytes:
        self._require_name(name)
        return self._io("read", name, b"")

    def write_document(self, name: str, content: bytes) -> None:
        self._require_name(name)
        self._io("write", name, content)

    def remove_document(self, name: str) -> None:
        self._require_name(name)
        self._io("delete", name, b"")

    def search_documents(self, query: str, *, limit: int = 5) -> tuple[DocumentHit, ...]:
        """Documents whose name or readable text matches ``query``, best first.

        Ranking and snippets mirror lexical recall (Vision §3): relevance is the
        fraction of the query's tokens the document shares (name plus text when the
        file decodes as utf-8 text); a binary file is still findable by its name, and
        its snippet is the name alone. Candidates only -- the core never reaches for
        raw bytes here (D6).
        """
        query_tokens = _tokens(query)
        if not query_tokens:
            return ()
        hits: list[DocumentHit] = []
        for name in self.list_documents():
            surface = name
            text = self._decoded_text(name)
            if text is not None:
                surface = f"{name} {text}"
            relevance = _relevance(query_tokens, surface)
            if relevance <= 0.0:
                continue
            snippet = self._snippet(name, text, query_tokens)
            hits.append(
                DocumentHit(name=name, snippet=snippet, relevance=relevance)
            )
        hits.sort(key=lambda hit: (-hit.relevance, hit.name))
        return tuple(hits[: max(0, limit)])

    # -- search helpers -------------------------------------------------------

    def _decoded_text(self, name: str) -> str | None:
        """The document's utf-8 text, or ``None`` when it is not readable text.

        Bytes that fail to decode are honest binaries -- searchable by name, but not
        quoted as if their content were legible (D37).
        """
        try:
            return self._io("read", name, b"").decode("utf-8")
        except UnicodeDecodeError:
            return None

    def _snippet(
        self, name: str, text: str | None, query_tokens: set[str]
    ) -> str:
        """A bounded excerpt around the first match, or the name alone if binary."""
        if text is None:
            return name
        matches = [
            word for word in _WORD.findall(text) if word.lower() in query_tokens
        ]
        position = text.lower().find(matches[0].lower()) if matches else -1
        if position < 0:
            return name
        start = max(0, position - _SNIPPET_LEAD)
        end = min(len(text), position + _SNIPPET_EXPAND_RIGHT)
        snippet = " ".join(text[start:end].split())
        prefix = _ELLIPSIS if start > 0 else ""
        suffix = _ELLIPSIS if end < len(text) else ""
        return f"{prefix}{snippet}{suffix}"

    # -- sandbox --------------------------------------------------------------

    @classmethod
    def _valid_name(cls, name: str) -> bool:
        if not name or name in {".", ".."}:
            return False
        return not any(separator in name for separator in _SEPARATORS)

    def _require_name(self, name: str) -> None:
        if not self._valid_name(name):
            raise ValueError(
                f"invalid document name {name!r}"
            )


def build_document_store(root: str | Path | None) -> LocalDocumentStore | None:
    """The default document store under ``root``, or ``None`` when no root is set.

    ``None`` keeps a Jarvis built from this factory entirely offline (D7/D8): no
    documents to accept means no document capability to advertise.
    """
    if not root:
        return None
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    return LocalDocumentStore(path)