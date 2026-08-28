"""atomic_write_text: a completed write replaces the file; a failed one leaves it intact."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.infrastructure import atomic_write
from jarvis.infrastructure.atomic_write import atomic_write_text


class TestAtomicWriteText:
    def test_writes_content_and_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "memory.json"
        atomic_write_text(target, '{"ok": true}')
        assert target.read_text(encoding="utf-8") == '{"ok": true}'

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "memory.json"
        atomic_write_text(target, "first")
        atomic_write_text(target, "second")
        assert target.read_text(encoding="utf-8") == "second"

    def test_leaves_no_temp_file_behind(self, tmp_path: Path) -> None:
        target = tmp_path / "memory.json"
        atomic_write_text(target, "content")
        assert list(tmp_path.iterdir()) == [target]

    def test_a_crash_mid_replace_leaves_the_original_intact(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "memory.json"
        atomic_write_text(target, "the good, complete file")

        def _boom(_src: object, _dst: object) -> None:
            raise OSError("simulated crash during rename")

        monkeypatch.setattr(atomic_write.os, "replace", _boom)
        with pytest.raises(OSError):
            atomic_write_text(target, "a half-written truncated file")

        # The original is untouched — no torn write reached it.
        assert target.read_text(encoding="utf-8") == "the good, complete file"
