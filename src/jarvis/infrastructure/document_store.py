"""LocalDocumentStore: a file-backed DocumentStore at the edge (project files).

The files store for classified documents: a bounded directory where each document
is kept under its own name — any extension is allowed, so the companion can hand
Jarvis logs, configs, exports, code or manuals. Disk access goes through an
injectable ``io`` driver over raw bytes so offline tests run deterministically
without touching the filesystem (D8). The store only keeps and returns bytes; it
never reasons about them (D6) and never escapes its sandbox (flat names only).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

DocumentIO = Callable[[str, str, bytes], bytes]
_SEPARATORS = ("/", "\\")


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