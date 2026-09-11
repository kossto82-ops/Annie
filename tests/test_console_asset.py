"""Guard: the console page and its speech-sync wiring stay present (Vision §30).

The animation lives in JavaScript (it must run in the browser), so it can't be
unit-tested by pytest; its behaviour is verified in a real browser. This is the cheap
tripwire against silently losing the wiring — the word-boundary → pulse path and the
sphere hook — the analogue of the public-surface guard for the one browser asset.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

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
    from jarvis.interface.command_center import snapshot
    from jarvis.jarvis import Jarvis

    caps = cast(list[dict[str, str]], snapshot(Jarvis())["capabilities"])
    assert len(caps) >= 12, "the catalog must expose every known capability"
    names = {c["name"] for c in caps}
    for expected in ("search the web", "manage calendar", "perceive speech", "manage tasks"):
        assert expected in names, f"catalog missing {expected!r}"
    for c in caps:
        has_purpose = c["description"] and c["requirement"]
        assert has_purpose, f"catalog entry {c['name']!r} lacks purpose/requirement"
        status_ok = c["status"] in {
            "ready", "acquired", "proposed", "rejected", "available",
        }
        assert status_ok, c["status"]


def test_the_live_ear_recorder_path_is_wired_and_keeps_web_speech() -> None:
    """Tripwire: the console records to the server when a live STT ear is wired.

    The snapshot's ``speech`` block (``live`` flag) decides between recording the
    mic and POSTing it to ``/api/speech/transcribe`` (the Whisper-class backer) and
    the in-browser Web Speech push-to-talk -- the two must never race for the mic.
    """
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        "renderSpeech",
        "serverEar",
        "MediaRecorder",
        "navigator.mediaDevices.getUserMedia",
        "/api/speech/transcribe",
        "sendRecording",
        "SpeechRecognition",
    ):
        assert marker in html, f"live STT recorder wiring lost its {marker!r}"
    # The Web Speech hold guards on the server ear; the recorder guards on NOT server.
    assert "serverEar) return;" in html, "in-browser and server mic paths must not race"


def test_the_cognition_thresholds_are_tunable_from_the_settings_panel() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    # The thresholds card lives in the settings drawer and drives the tunables
    # action; renderTunables syncs slider + label with every snapshot.
    for marker in (
        'id="groundedKnob"',
        'id="insightKnob"',
        'id="goalKnob"',
        "grounded_confidence",
        "renderTunables",
        'api("tunables"',
    ):
        assert marker in html, f"thresholds tuning lost its {marker!r} wiring"


def test_the_inline_script_has_no_broken_single_quoted_strings() -> None:
    """Tripwire against a JS syntax error that silently kills the whole page.

    A raw apostrophe inside a single-quoted JavaScript string (e.g. the reasoning
    placeholder "Jarvis's") breaks the literal and stops the entire console script
    from running. Escape those (\u2019 or double quotes). This walks each line's
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


def test_agents_are_the_real_edge_seams_not_the_capability_catalog() -> None:
    """Tripwire: the Active Agents surface must report wired seams, honestly.

    The reported agent count and cards come from the snapshot's ``agents`` block
    (the real edges + ``can_do``), and the panel opens the dedicated Agents drawer —
    never the capability catalog dressed up as agents.
    """
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        '"panel-agents"',
        'id="agentsbody"',
        "renderAgentsPanel",
        "(s.agents || []).filter((a) => a.active).length",
        "data-nav=\"agents\"",
        "data-nav=\"mem\"",
        "openPanel(\"agents\")",
    ):
        assert marker in html, f"real edge-agent wiring lost its {marker!r}"
    assert "AGENT_MAP" not in html, "the fake capability->agent map must not return"
    assert 'openPanel("agents")' in html, "agent cards must open the real agents panel"


def test_tasks_calendar_and_memory_have_their_own_panels() -> None:
    """Tripwire: calendar/tasks widgets live in their own panes, not buried in Ajustes."""
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        '"panel-task"',
        '"panel-cal"',
        '"panel-mem"',
        '"panel-wf"',
        'id="pendingTaskBody"',
        'id="pendingCalBody"',
        'id="wfbody"',
        'id="convCount"',
        'id="taskCount"',
        "renderTasksPanel",
        "renderCalPanel",
        "renderWorkflows",
    ):
        assert marker in html, f"dedicated pane wiring lost its {marker!r}"
    # The task/calendar creation widgets are still present where they belong.
    assert 'id="taskCreate"' in html and 'id="calCreate"' in html


def test_the_system_monitor_reports_only_measured_values() -> None:
    """Tripwire: the monitor must never estimate CPU in the browser."""
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in ("renderEnvironment", "s.environment", "monCpu", "monRam", "monDisk"):
        assert marker in html, f"honest system monitor lost its {marker!r}"
    assert "CPU est." not in html
    assert "systemMonitorTick" not in html, "the fake browser CPU estimate must not return"


def test_memory_insights_are_derived_from_real_metrics_and_episodes() -> None:
    """Tripwire: memory stats include session turns/calls and a data-derived chart."""
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        'id="memTurns"',
        'id="memCalls"',
        'id="memChart"',
        "renderMemoryChart",
        "episode_series",
    ):
        assert marker in html, f"memory insights lost its {marker!r}"
    assert "addEventListener(\"click\", () => openPanel(\"mem\"))" in html, \
        "the intelligence feed 'View All' must open the real memory panel"


def test_llm_status_counts_only_providers_with_real_calls() -> None:
    """Tripwire: 'Conectado' requires live successes; standby is never counted."""
    html = _CONSOLE.read_text(encoding="utf-8")
    assert '"En espera"' in html, "active-but-unproven providers must read 'En espera'"
    assert "Conectado" in html
    # The connected count must be incremented only on the genuinely-connected path:
    # there must be exactly one increment, inside the connected branch.
    lines = [ln for ln in html.splitlines() if "connectedCount" in ln]
    increments = [ln for ln in lines if ln.strip().endswith("connectedCount += 1;")]
    assert len(increments) == 1, "connectedCount must be incremented in exactly one path"
    assert 'data-q="task"' in html, "Quick Commands must expose a real new-task target"


def _snapshot_block(name: str) -> dict[str, object]:
    from jarvis.interface.command_center import snapshot
    from jarvis.jarvis import Jarvis

    return cast(dict[str, object], snapshot(Jarvis())[name])


def test_the_snapshot_surfaces_the_agents_block_from_real_seams() -> None:
    agents = cast(list[dict[str, object]], _snapshot_block("agents"))
    labels = {a.get("label") for a in agents}
    for expected in ("Percepción", "Web", "Razonador", "Voz", "Calendario", "Tareas"):
        assert expected in labels, f"agents block missing {expected!r}"
    for a in agents:
        assert isinstance(a.get("active"), bool), f"agent {a.get('label')!r} lacks an active flag"
        assert a.get("description"), f"agent {a.get('label')!r} lacks a description"
    # A fresh offline Jarvis runs no live edge: everything honest standby.
    assert not any(a.get("active") for a in agents), "fresh Jarvis must report no live edges"


def test_the_snapshot_surfaces_a_real_host_environment_block() -> None:
    env = _snapshot_block("environment")
    for key in ("cpu", "ram", "disk", "cores"):
        assert key in env, f"environment block missing {key!r}"
    # Values are either measured numbers or None ("n/d"), never invented zeros.
    for key in ("cpu", "ram", "disk"):
        v = env[key]
        assert v is None or isinstance(v, (int, float)), f"{key} must be a measured value or None"


def test_the_snapshot_memory_block_carries_session_turns_and_calls() -> None:
    mem = _snapshot_block("memory")
    assert "turns" in mem and isinstance(mem["turns"], int)
    assert "calls" in mem and isinstance(mem["calls"], int)
    assert isinstance(mem["episode_series"], list), "episode_series must be a list of timestamps"


def test_f1_agents_block_carries_a_derived_reason_per_edge() -> None:
    """F1: every agent edge explains its standby with a derived reason."""
    agents = cast(list[dict[str, object]], _snapshot_block("agents"))
    assert agents, "agents block must not be empty"
    for a in agents:
        reason = a.get("reason")
        assert isinstance(reason, str) and reason.strip(), (
            f"agent {a.get('label')!r} lacks a derived reason"
        )
    by_label = {a.get("label"): a for a in agents}
    assert "JARVIS_" in str(by_label["Tareas"].get("reason")) or "TASKS" in str(
        by_label["Tareas"].get("reason")
    ).upper()
    assert "JARVIS_" in str(by_label["Calendario"].get("reason")) or "CALENDAR" in str(
        by_label["Calendario"].get("reason")
    ).upper()


def test_f1_tools_snapshot_exposes_policy_and_args() -> None:
    """F1: the tools block carries permission + args so the UI can gate runs."""
    from jarvis.interface.command_center import snapshot
    from jarvis.jarvis import Jarvis

    tools = cast(list[dict[str, object]], snapshot(Jarvis())["tools"])
    for t in tools:
        assert "permission" in t, f"tool {t.get('name')!r} lacks a permission level"
        assert "args" in t, f"tool {t.get('name')!r} lacks an args schema"


def test_f1_console_wires_task_crud() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        'id="taskEditId"',
        'id="taskSave"',
        'id="taskCancel"',
        "editTask(",
        "toggleTask(",
        "deleteTask(",
        '"disable"',
        '"enable"',
        '"delete"',
        '"update"',
        "window.confirm(",
    ):
        assert marker in html, f"task CRUD wiring lost its {marker!r}"


def test_f1_console_wires_calendar_crud() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        'id="calEditId"',
        'id="calSave"',
        'id="calCancel"',
        "editEvent(",
        "deleteEvent(",
        'action: "update"',
        'action: "delete"',
    ):
        assert marker in html, f"calendar CRUD wiring lost its {marker!r}"


def test_f1_console_wires_docs_crud() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        "infoDocument(",
        "deleteDocument(",
        "editDocument(",
        'action: "info"',
        'action: "remove"',
        'action: "edit"',
    ):
        assert marker in html, f"documents CRUD wiring lost its {marker!r}"


def test_f1_console_wires_tool_run_with_approval() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        "runTool(",
        "requires_approval",
        "approved",
        'action: "run"',
        "window.confirm(",
        "spec.permission",
    ):
        assert marker in html, f"tool run/approval wiring lost its {marker!r}"


def test_f2_capability_catalog_carries_a_derived_stance() -> None:
    """F2: every catalog entry carries its evidence-derived stance."""
    from jarvis.interface.command_center import snapshot
    from jarvis.jarvis import Jarvis

    caps = cast(list[dict[str, str]], snapshot(Jarvis())["capabilities"])
    assert caps, "capabilities must not be empty"
    for c in caps:
        assert c.get("stance") in {
            "suggest",
            "ask_first",
            "withhold",
        }, f"capability {c.get('name')!r} lacks a derived stance"


def test_f2_console_wires_odysseus_actions() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        'id="capScoutInput"',
        'id="capScoutBtn"',
        'id="noticeBtn"',
        "scoutCapability(",
        "acquireCapability(",
        "rejectCapability(",
        "noticeGaps(",
        'action: "scout"',
        'action: "acquire"',
        'action: "reject"',
        'action: "notice"',
        "STANCE_TEXT",
    ):
        assert marker in html, f"odysseus panel wiring lost its {marker!r}"


def test_f2_console_lists_real_skills_and_counts_them() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        "skillsOf(",
        "Skills — capacidades ganadas",
        "specs.length + skills.length",
    ):
        assert marker in html, f"skills section lost its {marker!r}"


def test_f3_console_wires_provider_management() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        'id="deliberation"',
        'id="providerStats"',
        'id="providerReset"',
        'id="probeprovider"',
        'id="provOut"',
        'id="offlineBanner"',
        'id="reasonerProvider"',
        'id="reasonerModel"',
        'id="applyreasoner"',
        'id="reasonerOut"',
        'id="reasonerState"',
        'id="modelList"',
        "applyDeliberation(",
        "probeProvider(",
        "applyReasoner(",
        "resetProviderStats(",
        "renderProviderStats(",
        "renderProviderBanner(",
        "renderReasonerState(",
        'api("deliberation"',
        'api("provider_health"',
        'api("reasoner"',
        'api("provider_reset"',
    ):
        assert marker in html, f"provider management lost its {marker!r}"


def test_f3_snapshot_stats_carry_averages() -> None:
    stats = cast(dict[str, object], _snapshot_block("provider"))
    assert "avg_seconds" in stats and "slowest_seconds" in stats


def test_f4_console_wires_workflow_orchestration() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        "renderWorkflows(",
        "runWorkflow(",
        "renderWorkflowSteps(",
        'api("workflow"',
        "WF_STATE_TEXT",
        "ejecutando pasos sobre los bordes",
    ):
        assert marker in html, f"workflow orchestration lost its {marker!r}"
    assert "WORKFLOW_EDGES" not in html, "the static edge list must not return"


def test_f4_snapshot_carries_workflows_with_readiness() -> None:
    flows = cast(list[dict[str, object]], _snapshot_block("workflows"))
    assert {f["name"] for f in flows} == {"brief", "investigate", "dossier"}
    for flow in flows:
        assert flow["title"] and isinstance(flow["inputs"], list)
        assert isinstance(flow["ready"], bool) and isinstance(flow["missing"], list)
    # Fresh offline Jarvis: every workflow honestly blocked.
    assert not any(f["ready"] for f in flows)


def test_f5_console_wires_memory_depth() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        'id="beliefbody"',
        'id="memRecallInput"',
        'id="memRecallBtn"',
        'id="recallbody"',
        'id="convbody"',
        "loadMemoryPanel(",
        "renderBeliefs(",
        "openBelief(",
        "searchMemories(",
        "renderConversations(",
        "resumeSession(",
        'api("belief"',
        'api("recall"',
        'api("conversations"',
    ):
        assert marker in html, f"memory depth lost its {marker!r}"


def test_f6_console_wires_task_runs_and_calendar_depth() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        "runTaskNow(",
        'action: "run"',
        "calDay",
        "calDayBody",
        "loadCalDay(",
        "shiftCalDay(",
        "calGoogleState",
        "calGoogleConnect",
        "calGoogleDisconnect",
        "calGoogleCode",
        "calGoogleComplete",
        "googleConnect(",
        "googleComplete(",
        "googleDisconnect(",
        "loadGoogleStatus(",
        'api("google_calendar"',
        'action: "range"',
        'action: "complete"',
        'action: "disconnect"',
        'id="calGoogleId"',
        'id="calGoogleSecret"',
        'id="calGoogleRedirect"',
        "client_secret",
        'id="googleConnectLink"',
        "openGoogleConnect(",
        "renderGoogleLink(",
    ):
        assert marker in html, f"F6 wiring lost its {marker!r}"


def test_f6_snapshot_carries_calendar_source_and_task_runs() -> None:
    cal = cast(dict[str, object], _snapshot_block("calendar"))
    assert cal == {"source": "none", "connected": False}


def test_f7_console_wires_the_setup_guide() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        'id="guidebody"',
        "GUIDE_ROWS",
        "renderGuide(",
        "JARVIS_AGENT_ROOT",
        "JARVIS_STT_*",
        "JARVIS_TASKS_ROOT",
        "JARVIS_PROJECT_ROOTS",
        "SEARXNG_INSTANCE",
    ):
        assert marker in html, f"setup guide lost its {marker!r}"


def test_f7_console_wires_goals_actions_operator_and_monitor() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        'id="goalsDrop"',
        'id="goalwrap"',
        "renderGoalsDrop(",
        "renderOperator(",
        "companion_name",
        'id="monHost"',
        'id="monSpark"',
        "renderCpuSpark(",
        "cpuSamples",
    ):
        assert marker in html, f"F7 polish lost its {marker!r}"


def test_f7_snapshot_carries_platform_and_companion_name() -> None:
    from jarvis.interface.command_center import snapshot
    from jarvis.jarvis import Jarvis

    state = snapshot(Jarvis())
    assert state["environment"]["platform"] == __import__("os").name
    assert state["companion_name"] is None


def test_f8_console_wires_notes_and_mail_panels() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        '"panel-notes"',
        '"panel-mail"',
        'id="notesbody"',
        'id="mailbody"',
        'id="notesCount"',
        'id="mailCount"',
        'data-nav="notes"',
        'data-nav="mail"',
        "loadNotes(",
        "renderNotesList(",
        "openNote(",
        "editNote(",
        "deleteNote(",
        "searchNotes(",
        "loadMails(",
        "sendMailFlow(",
        'api("notes"',
        'api("mail"',
        'action: "send"',
        "approved:true",
    ):
        assert marker in html, f"notes/mail panels lost their {marker!r}"


def test_f8_snapshot_carries_notes_and_mail_blocks() -> None:
    assert _snapshot_block("notes") == {"total": 0, "recent": []}
    assert _snapshot_block("mail") == {"configured": False}


def test_f9_console_wires_config_edges() -> None:
    html = _CONSOLE.read_text(encoding="utf-8")
    for marker in (
        "renderToolOrigins(",
        "MCP — bordes externos",
        "Proyectos — carpetas compartidas",
        'id="recallState"',
        'id="recallReload"',
        'id="recallOut"',
        'id="sttState"',
        'id="sttReload"',
        'id="sttOut"',
        "renderRecallState(",
        "renderSttState(",
        "reloadEmbeddings(",
        "reloadEar(",
        'api("embeddings"',
        'api("speech"',
    ):
        assert marker in html, f"config edges lost their {marker!r}"


def test_f9_snapshot_carries_recall_mode_and_tool_origins() -> None:
    from jarvis.interface.command_center import snapshot
    from jarvis.jarvis import Jarvis

    state = snapshot(Jarvis())
    assert state["recall"] == {"mode": "lexical"}


def test_openpanel_really_shows_the_pane() -> None:
    """Tripwire: the drawer pane must become visible, not fall back to CSS-hidden.

    ``.pane`` is ``display: none`` by stylesheet, so clearing the inline style
    (``""``) keeps it invisible and every drawer opens blank. The target pane
    must be set to ``block`` explicitly.
    """
    html = _CONSOLE.read_text(encoding="utf-8")
    assert 'pane.style.display = "block"' in html
    assert 'pane.style.display = ""' not in html
