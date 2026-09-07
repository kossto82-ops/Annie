"""LocalDocumentStore: a file-backed DocumentStore at the edge (project files).

The files store for classified documents: a bounded directory where each document
is kept under a sandbox-safe relative path — any extension is allowed, so the
companion can hand Jarvis logs, configs, exports, code or manuals, filed as flat
or nested names (``runbook.md`` or ``docs/api.md``). Disk access goes through an
injectable ``io`` driver over raw bytes so offline tests run deterministically
without touching the filesystem (D8). The store only keeps and returns bytes; it
never reasons about them (D6) and never escapes its sandbox (names are relative,
never absolute, never ``.``/``..``).

Alongside each document the store keeps a *provenance index* (a single reserved
``_jarvis-meta.json`` at the root): who the document belongs to (Vision §26) and
when it was stored/updated. The index is recorded metadata, never content; it is
hidden from ``list``/``search`` so the files the companion sees are exactly the
files it gave Jarvis.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jarvis.domain.enums.document_owner import DocumentOwner
from jarvis.domain.value_objects.document_hit import DocumentHit
from jarvis.domain.value_objects.document_meta import DocumentMeta

DocumentIO = Callable[[str, str, bytes], bytes]
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_META_NAME = "_jarvis-meta.json"

# Tokens shorter than this carry too little signal to rank on (mirrors the lexical
# memory retriever's language-agnostic floor).
_MIN_TOKEN_LEN = 2
_WORD = re.compile(r"\w+")
_SNIPPET_EXPAND_RIGHT = 140
_SNIPPET_LEAD = 60
_ELLIPSIS = "…"


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True, frozen=True)
class _MetaEntry:
    """One provenance record held in the index."""

    owner: DocumentOwner
    stored_at: datetime
    updated_at: datetime
    size_bytes: int


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
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Bind the store to a sandbox ``root`` with an injectable ``io`` driver.

        ``io(operation, path, payload)`` mirrors the filesystem protocol over
        bytes: ``read`` returns the file's bytes, ``write`` writes ``payload`` and
        returns ``b""``, ``delete`` removes the file and returns ``b""``, and
        ``list`` returns the sorted document names newline-joined (utf-8).
        Defaults to real disk access through :func:`pathlib`; injecting a fake
        keeps tests offline (D8). ``clock`` supplies the timestamps recorded in
        the provenance index (UTC by default; inject for deterministic tests).
        """
        self._root = Path(root).resolve()
        self._io = io or self._default_io
        self._clock = clock or _utc_now

    # -- filesystem driver ----------------------------------------------------

    def _default_io(self, operation: str, path: str, payload: bytes) -> bytes:
        if operation == "list":
            names = sorted(
                child.relative_to(self._root).as_posix()
                for child in self._root.rglob("*")
                if child.is_file()
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
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_bytes(payload)
        return b""

    # -- DocumentStore --------------------------------------------------------

    def list_documents(self) -> tuple[str, ...]:
        """Every kept document -- the reserved provenance index is never surfaced.

        The companion's files are exactly what ``list`` shows: the meta index is a
        private record, not a document.
        """
        raw = self._io("list", "", b"")
        if not raw:
            return ()
        return tuple(
            part for part in raw.decode("utf-8").split("\n") if part and part != _META_NAME
        )

    def read_document(self, name: str) -> bytes:
        key = self._require_name(name)
        return self._io("read", key, b"")

    def write_document(
        self, name: str, content: bytes, *, owner: DocumentOwner = DocumentOwner.COMPANION
    ) -> None:
        """Store (or replace) ``content`` under ``name`` and record its provenance.

        ``owner`` attributes the document -- who gave Jarvis this artifact
        (Vision §26). The companion is the default; a generated report is marked
        ``DocumentOwner.JARVIS`` by the surface that materialised it. Replacing a
        document keeps its original ``stored_at`` and refreshes ``updated_at``.
        """
        key = self._require_name(name)
        now = self._clock()
        index = self._load_meta()
        previous = index.get(key)
        index[key] = _MetaEntry(
            owner=DocumentOwner(owner),
            stored_at=previous.stored_at if previous is not None else now,
            updated_at=now,
            size_bytes=len(content),
        )
        self._io("write", key, content)
        self._save_meta(index)

    def remove_document(self, name: str) -> None:
        key = self._require_name(name)
        index = self._load_meta()
        index.pop(key, None)
        self._save_meta(index)
        self._io("delete", key, b"")

    def document_meta(self, name: str) -> DocumentMeta | None:
        """The recorded provenance of ``name``, or None when none was recorded.

        A file on disk with no meta entry -- e.g. one that predates provenance
        tracking -- honestly reads ``None`` rather than being guessed at (D11).
        """
        key = self._require_name(name)
        entry = self._load_meta().get(key)
        if entry is None:
            return None
        return DocumentMeta(
            name=key,
            owner=entry.owner,
            size_bytes=entry.size_bytes,
            stored_at=entry.stored_at,
            updated_at=entry.updated_at,
        )

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

    # -- provenance index -----------------------------------------------------

    def _load_meta(self) -> dict[str, _MetaEntry]:
        """The provenance index entries by document name (empty when none yet).

        Missing or unreadable index reads as empty -- provenance is a best-effort
        record, never a blocker for keeping or reading files (D8, D11).
        """
        try:
            raw = self._io("read", _META_NAME, b"").decode("utf-8")
        except (FileNotFoundError, KeyError):  # no index yet (real disk / fake io)
            return {}
        try:
            stored = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return {}
        index: dict[str, _MetaEntry] = {}
        for name, entry in stored.items():
            try:
                index[name] = _MetaEntry(
                    owner=DocumentOwner(entry["owner"]),
                    stored_at=datetime.fromisoformat(entry["stored_at"]),
                    updated_at=datetime.fromisoformat(entry["updated_at"]),
                    size_bytes=int(entry["size_bytes"]),
                )
            except (KeyError, TypeError, ValueError):
                continue  # a corrupt entry is skipped, the rest survive
        return index

    def _save_meta(self, index: dict[str, _MetaEntry]) -> None:
        stored = {
            name: {
                "owner": entry.owner.value,
                "stored_at": entry.stored_at.isoformat(),
                "updated_at": entry.updated_at.isoformat(),
                "size_bytes": entry.size_bytes,
            }
            for name, entry in index.items()
        }
        self._io("write", _META_NAME, json.dumps(stored).encode("utf-8"))

    # -- sandbox --------------------------------------------------------------

    @classmethod
    def _valid_name(cls, name: str) -> bool:
        if not name:
            return False
        normalized = name.replace("\\", "/")
        if normalized.startswith("/") or _WINDOWS_DRIVE.match(normalized):
            return False
        return not any(part in ("", ".", "..") for part in normalized.split("/"))

    def _require_name(self, name: str) -> str:
        """Validate ``name`` and return its canonical sandbox-safe relative form."""
        if not self._valid_name(name):
            raise ValueError(
                f"invalid document name {name!r}"
            )
        return name.replace("\\", "/")


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