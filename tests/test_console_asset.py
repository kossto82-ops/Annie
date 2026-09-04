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


def test_the_sphere_stays_visible_while_chatting() -> None:
    """Tripwire: chatting must never hide the sphere/dashboard behind a swap.

    The sphere lives on a persistent stage beside the right column; home and chat
    toggle a ``hidden`` class inside that column instead of hiding the whole page.
    """
    html = _CONSOLE.read_text(encoding="utf-8")
    # The sphere canvas is a sibling of the side column, outside .home/.chatview.
    assert "<canvas id=\"sphere\">" in html
    stage = html.index("<section class=\"stage\">")
    canvas = html.index("<canvas id=\"sphere\">")
    side = html.index("<section class=\"side\">")
    assert stage < canvas < side, "the sphere stage must be a persistent sibling of the side column"
    # Home and chat switch by toggling .hidden, never by hiding the whole page.
    for marker in ('$("chatview").classList.add("hidden")', '$("home").classList.remove("hidden")'):
        assert marker in html, f"chat/home switching lost its {marker!r} toggle"
    assert "class=\"chatview hidden\"" in html, "chat must start hidden next to the sphere"


def test_the_snapshot_surfaces_the_full_capability_catalog() -> None:
    """Tripwire: the surface reports the full landscape, never a blank panel.

    Even a fresh Jarvis exposes the whole catalog of what it could grow to do,
    annotated with status (default 'available') so the Capacidades panel is never
    empty. Ready/held statuses come from live state, not hardcoded here.
    """
    from jarvis.jarvis import Jarvis
    from jarvis.interface.command_center import snapshot

    caps = snapshot(Jarvis())["capabilities"]
    assert len(caps) >= 12, "the catalog must expose every known capability"
    names = {c["name"] for c in caps}
    for expected in ("search the web", "manage calendar", "perceive speech", "manage tasks"):
        assert expected in names, f"catalog missing {expected!r}"
    for c in caps:
        assert c["description"] and c["requirement"], f"catalog entry {c['name']!r} lacks purpose/requirement"
        assert c["status"] in {"ready", "acquired", "proposed", "rejected", "available"}, c["status"]


def test_the_inline_script_has_no_broken_single_quoted_strings() -> None:
    """Tripwire against a JS syntax error that silently kills the whole page.

    A raw apostrophe inside a single-quoted JavaScript string (e.g. the reasoning
    placeholder "Jarvis's") breaks the literal and stops the entire console script
    from running. Escape those (\\u2019 or double quotes). This walks each line's
    single-quoted segments and rejects any that contain a raw apostrophe.
    """
    html = _CONSOLE.read_text(encoding="utf-8")
    match = __import__("re").search(r"<script>(.*?)</script>", html, __import__("re").S)
    script = match.group(1) if match else ""
    for lineno, line in enumerate(script.splitlines(), 1):
        # Only inspect lines that contain a single-quoted literal.
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        # A single-quoted string starts at the first ' and ends at the next unmasked '.
        i = 0
        while i < len(line):
            if line[i] == "'":
                end = i + 1
                while end < len(line):
                    if line[end] == "\\":
                        end += 2
                        continue
                    if line[end] == "'":
                        break
                    end += 1
                inner = line[i + 1:end]
                assert "'" not in inner, (
                    f"console.html line {lineno} has an unescaped apostrophe in a "
                    "single-quoted string — this breaks the whole page: "
                    f"{stripped!r}"
                )
                i = end + 1
            else:
                i += 1
