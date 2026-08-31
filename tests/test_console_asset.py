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


def test_the_face_keeps_its_recognisable_features_and_responsive_stage() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        '"eyeL"',
        '"eyeR"',
        '"iris"',
        '"pupil"',
        '"nosePlane"',
        '"noseTip"',
        '"mouth"',
        '"cheek"',
        '"chin"',
    ):
        assert marker in html, f"point-cloud face lost its {marker!r} feature"
    for marker in (
        "addFacialPlanes(points)",
        "addEye(points",
        "addNose(points)",
        "addMouth(points)",
        "addOrganicPoint",
    ):
        assert marker in html, f"integrated particle geometry lost its {marker!r} builder"
    assert "prefers-reduced-motion: reduce" in html
    assert ".stage { display: none; }" not in html


def test_the_face_keeps_its_dynamic_eye_and_state_behaviour() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        "nextBlink",
        "blinkStarted",
        "gazeX",
        "gazeY",
        "thinking ? 265 : 174",
        "setThinking:",
        "get blink()",
        "get thinking()",
        "snapshotFeatures:",
    ):
        assert marker in html, f"dynamic face wiring lost its {marker!r} behavior"


def test_the_mouth_is_driven_by_real_speech_boundaries() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    # The utterance's word boundaries drive the mouth, gated by start/end of speech.
    for marker in ("onboundary", "pulseWord", "setSpeaking", "articulation"):
        assert marker in html, f"speech-sync wiring lost its {marker!r}"
    # The observable hook the browser check drives.
    assert "window.__face" in html


def test_the_reasoning_panel_is_wired() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    # The panel that shows the mind: provenance grounds + the step trace + the cycle.
    for marker in ("renderReasoning", "renderCycle", "Grounds for", "window.__reason"):
        assert marker in html, f"reasoning panel lost its {marker!r}"
