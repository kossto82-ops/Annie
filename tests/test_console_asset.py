"""Guard: the console page and its speech-sync wiring stay present (Vision §30).

The mouth animation lives in JavaScript (it must run in the browser), so it can't be
unit-tested by pytest; its behaviour is verified in a real browser. This is the cheap
tripwire against silently losing the wiring — the word-boundary → mouth path and the
face hook — the analogue of the public-surface guard for the one browser asset.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.interface import command_center

_CONSOLE = Path(command_center.__file__).with_name("console.html")


def test_the_console_asset_is_shipped() -> None:
    assert _CONSOLE.is_file()
    html = _CONSOLE.read_text(encoding="utf-8").lower()
    assert "<canvas id=\"face\">" in html
    assert "command center" in html


def test_the_mouth_is_driven_by_real_speech_boundaries() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    # The utterance's word boundaries drive the mouth, gated by start/end of speech.
    for marker in ("onboundary", "pulseWord", "setSpeaking", "articulation"):
        assert marker in html, f"speech-sync wiring lost its {marker!r}"
    # The observable hook the browser check drives.
    assert "window.__face" in html
