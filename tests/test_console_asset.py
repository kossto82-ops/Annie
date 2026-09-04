"""Guard: the console page and its speech-sync wiring stay present (Vision §30).

The animation lives in JavaScript (it must run in the browser), so it can't be
unit-tested by pytest; its behaviour is verified in a real browser. This is the cheap
tripwire against silently losing the wiring — the word-boundary → pulse path and the
sphere hook — the analogue of the public-surface guard for the one browser asset.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.interface import command_center

_CONSOLE = Path(command_center.__file__).with_name("console.html")


def test_the_console_asset_is_shipped() -> None:
    assert _CONSOLE.is_file()
    html = _CONSOLE.read_text(encoding="utf-8").lower()
    assert "<canvas id=\"sphere\">" in html
    assert "command center" in html


def test_the_sphere_keeps_its_recognisable_features_and_responsive_stage() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        '"shell"',
        '"core"',
        "GOLDEN_ANGLE",
        "buildSphere",
        "breathe",
        "rim",
        "requestAnimationFrame",
    ):
        assert marker in html, f"point-cloud sphere lost its {marker!r} feature"
    assert "prefers-reduced-motion: reduce" in html


def test_the_sphere_keeps_its_dynamic_state_behaviour() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        "thinking ? 265 : 174",
        "setThinking:",
        "get thinking()",
        "get blink()",
        "snapshotFeatures:",
        "mouthEnv",
        "pulseWord",
    ):
        # pulseWord is shared reactive machinery for the visual state.
        assert marker in html, f"dynamic sphere wiring lost its {marker!r} behavior"


def test_the_mouth_is_driven_by_real_speech_boundaries() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    # The utterance's word boundaries drive the pulse, gated by start/end of speech.
    for marker in ("onboundary", "pulseWord", "setSpeaking", "articulation"):
        assert marker in html, f"speech-sync wiring lost its {marker!r}"
    # The observable hook the browser check drives.
    assert "window.__face" in html


def test_the_reasoning_panel_is_wired() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    # The panel that shows the mind: provenance grounds + the step trace + the cycle.
    for marker in ("renderReasoning", "renderCycle", "Grounds for", "window.__reason"):
        assert marker in html, f"reasoning panel lost its {marker!r}"


def test_capabilities_and_tools_are_wired_as_separate_panels() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    # Capacidades and Herramientas are distinct panels with their own drawer bodies.
    for marker in (
        '"panel-cap"',
        '"panel-tool"',
        '"panel-set"',
        'id="capCount"',
        'id="toolCount"',
        'renderCapabilityPanels',
        'renderTools(',
        'renderNeeds',
    ):
        assert marker in html, f"capabilities/tools panels lost their {marker!r} wiring"


def test_calendar_and_tasks_panels_are_wired() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    # The settings panel exposes calendar/tasks (Odysseus #6/#7) to the browser.
    for marker in (
        "id=\"calList\"",
        "id=\"calCreate\"",
        "id=\"taskList\"",
        "id=\"taskDue\"",
        "id=\"taskCreate\"",
        "runToolPanel",
    ):
        assert marker in html, f"calendar/tasks panels lost their {marker!r} wiring"
