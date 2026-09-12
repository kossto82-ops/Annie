"""Workflow handlers — predefined multi-step chains over edge commands."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from jarvis.jarvis import Jarvis

if TYPE_CHECKING:
    pass

# A reply the UI can render and (optionally) speak; some commands add extra fields.
Reply = dict[str, object]

# Predefined multi-step chains over the real edge commands (F4). Each step names
# a command from _COMMANDS plus its static payload; ``from_inputs`` copies named
# caller inputs into that payload. A step with ``collect`` builds its payload
# from the previous steps' replies instead (a genuine chain, not parallel calls).
_WORKFLOWS: dict[str, Reply] = {
    "brief": {
        "title": "El día de un vistazo",
        "description": "Próximos eventos del calendario + tareas pendientes, en un digest.",
        "inputs": [],
        "steps": [
            {"command": "calendar", "payload": {"action": "list", "limit": 5}},
            {"command": "tasks", "payload": {"action": "due"}},
        ],
    },
    "investigate": {
        "title": "Investigar un tema",
        "description": "Búsqueda web y después investigación en profundidad sobre el tema.",
        "inputs": [
            {"name": "query", "label": "tema", "required": True},
            {"name": "depth", "label": "profundidad", "required": False, "default": "1"},
        ],
        "steps": [
            {
                "command": "external",
                "payload": {"action": "search", "limit": 5},
                "from_inputs": ["query"],
            },
            {
                "command": "research",
                "payload": {"depth": 1},
                "from_inputs": ["query", "depth"],
            },
        ],
    },
    "dossier": {
        "title": "Armar un dossier",
        "description": "Busca, investiga y guarda el combinado como documento generado.",
        "inputs": [
            {"name": "query", "label": "tema", "required": True},
        ],
        "steps": [
            {
                "command": "external",
                "payload": {"action": "search", "limit": 5},
                "from_inputs": ["query"],
            },
            {
                "command": "research",
                "payload": {"depth": 1},
                "from_inputs": ["query"],
            },
            {"command": "documents", "collect": True},
        ],
    },
}


def _workflow_step_capability(command: str, payload: Reply) -> str | None:
    """The earned capability a workflow step needs, or None when it needs none."""
    if command == "external":
        action = str(payload.get("action", "")).strip().lower()
        if action == "search":
            return "search the web"
        if action == "read":
            return "read external documents"
        return None
    if command == "research":
        return "deep research"
    if command == "compare":
        return "compare language models"
    if command == "calendar":
        return "manage calendar"
    if command == "tasks":
        return "manage tasks"
    if command == "documents":
        return "work with files"
    return None


def _workflow_missing(jarvis: Jarvis, name: str) -> list[Reply]:
    """The inactive edges a workflow needs, each with its honest derived reason."""
    from jarvis.interface._state import _agents_block

    definition = _WORKFLOWS[name]
    reasons = {edge.get("capability"): edge.get("reason") for edge in _agents_block(jarvis)}
    missing: list[Reply] = []
    seen: set[str] = set()
    for step in cast("list[Reply]", definition["steps"]):
        command = str(step.get("command", ""))
        if bool(step.get("collect")):
            capability: str | None = "work with files"
        else:
            capability = _workflow_step_capability(command, cast("Reply", step.get("payload", {})))
        if capability is None or capability in seen:
            continue
        seen.add(capability)
        if not jarvis.can_do(capability):
            missing.append({"capability": capability, "reason": reasons.get(capability)})
    return missing


def _workflows_block(jarvis: Jarvis) -> list[Reply]:
    """Every predefined workflow with its inputs and whether its edges are live."""
    block: list[Reply] = []
    for name, definition in _WORKFLOWS.items():
        missing = _workflow_missing(jarvis, name)
        block.append(
            {
                "name": name,
                "title": definition["title"],
                "description": definition["description"],
                "inputs": definition["inputs"],
                "steps": [
                    {
                        "command": step.get("command", ""),
                        "action": cast("Reply", step.get("payload", {})).get("action", ""),
                    }
                    for step in cast("list[Reply]", definition["steps"])
                ],
                "ready": not missing,
                "missing": missing,
            }
        )
    return block


def _slug(text: str, limit: int = 40) -> str:
    """A filesystem-safe slug for a generated dossier name."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit] or "dossier"


def _workflow(jarvis: Jarvis, payload: Reply) -> Reply:
    """Run a predefined multi-step chain over the real edge commands (F4).

    Actions: ``list`` (definitions with inputs and which edges are live) and
    ``run`` (``name`` plus ``inputs``). A workflow runs only when every edge
    it needs is active (acquired + live-backed); otherwise it refuses honestly
    with each step marked blocked and the derived reason -- nothing half-runs.
    Steps run in order and stop on the first error (later steps read as
    omitted); the final reply joins every step's real outcome under headers.
    """
    from jarvis.interface.command_center import _COMMANDS

    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use workflow with action 'list' or 'run'.",
            "speak": False,
        }
    if action == "list":
        block = _workflows_block(jarvis)
        lines = [
            f"- {entry['name']}: {entry['title']}"
            + (" (ready)" if entry["ready"] else " (blocked)")
            for entry in block
        ]
        return {
            "reply": "Workflows:\n" + "\n".join(lines),
            "speak": False,
            "workflows": block,
        }
    if action == "run":
        name = str(payload.get("name", "")).strip()
        if name not in _WORKFLOWS:
            return {"error": f"unknown workflow: {name or '(none)'}", "speak": False}
        definition = _WORKFLOWS[name]
        raw_inputs = payload.get("inputs", {})
        inputs: dict[str, str] = {}
        if isinstance(raw_inputs, dict):
            items = cast("dict[object, object]", raw_inputs)
            inputs = {str(k): str(v) for k, v in items.items()}
        for schema in cast("list[Reply]", definition["inputs"]):
            key = str(schema.get("name", ""))
            if bool(schema.get("required")) and not inputs.get(key, "").strip():
                return {
                    "error": f"workflow '{name}' needs input '{key}'.",
                    "speak": False,
                }
            if key not in inputs and schema.get("default") is not None:
                inputs[key] = str(schema["default"])
        missing = _workflow_missing(jarvis, name)
        steps = cast("list[Reply]", definition["steps"])
        if missing:
            wanted = ", ".join(str(m.get("capability")) for m in missing)
            return {
                "ok": False,
                "reply": (
                    f"No puedo ejecutar '{name}': faltan bordes activos ({wanted}). "
                    "Mira la pestaña Agentes para el porqué de cada uno."
                ),
                "speak": False,
                "steps": [
                    {
                        "command": step.get("command", ""),
                        "action": cast("Reply", step.get("payload", {})).get("action", ""),
                        "state": "bloqueado",
                        "reason": next(
                            (
                                str(m.get("reason"))
                                for m in missing
                                if m.get("capability")
                                == (
                                    "work with files"
                                    if step.get("collect")
                                    else _workflow_step_capability(
                                        str(step.get("command", "")),
                                        cast("Reply", step.get("payload", {})),
                                    )
                                )
                            ),
                            None,
                        ),
                    }
                    for step in steps
                ],
            }
        ran: list[Reply] = []
        collected: list[tuple[str, str]] = []
        halted = False
        for step in steps:
            command = str(step.get("command", ""))
            if halted:
                ran.append({"command": command, "state": "omitido"})
                continue
            if bool(step.get("collect")):
                query = inputs.get("query", "tema")
                body = "\n\n".join(
                    f"# {title}\n\n{text}" for title, text in collected
                ) or "(sin resultados previos)"
                step_payload: Reply = {
                    "action": "save",
                    "name": f"dossier-{_slug(query)}.md",
                    "content": f"# Dossier: {query}\n\n{body}\n",
                    "owner": "jarvis",
                }
            else:
                step_payload = dict(cast("Reply", step.get("payload", {})))
                for key in cast("list[str]", step.get("from_inputs", [])):
                    if key in inputs:
                        step_payload[key] = inputs[key]
            run = _COMMANDS.get(command)
            if run is None:
                ran.append(
                    {"command": command, "state": "error", "reply": "unknown step command."}
                )
                halted = True
                continue
            outcome = run(jarvis, step_payload)
            outcome.pop("state", None)
            text = str(outcome.get("reply") or outcome.get("error") or "(sin salida)")
            if "error" in outcome:
                ran.append({"command": command, "state": "error", "reply": text})
                halted = True
                continue
            label = (
                f"{command} {step_payload.get('action', '')}".strip()
                if not step.get("collect")
                else "documents save"
            )
            collected.append((label, text))
            ran.append({"command": command, "state": "ok", "reply": text})
        digest = "\n\n---\n\n".join(
            f"## {title}\n\n{text}" for title, text in collected
        ) or "(sin resultados)"
        all_ok = all(entry.get("state") == "ok" for entry in ran)
        title = str(definition.get("title", name))
        done = sum(1 for entry in ran if entry.get("state") == "ok")
        return {
            "ok": all_ok,
            "reply": f"Workflow '{title}' ({done}/{len(ran)} pasos ok):\n\n{digest}",
            "speak": False,
            "steps": ran,
        }
    return {"reply": "Unknown workflow action.", "speak": False}
