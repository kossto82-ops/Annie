"""Capability/tool handlers — the growth and acting-tools surface."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.value_objects.capability import Capability
from jarvis.domain.value_objects.tool_call_result import ToolCallResult
from jarvis.domain.value_objects.tool_spec import ToolSpec
from jarvis.jarvis import Jarvis

from jarvis.interface._shared import _capability_not_ready, _ready_marker

if TYPE_CHECKING:
    pass

# A reply the UI can render and (optionally) speak; some commands add extra fields.
Reply = dict[str, object]


def _capability(jarvis: Jarvis, payload: Reply) -> Reply:
    """Give Jarvis tools to grow — scout, propose, and acquire capabilities
    (Odysseus, Vision §34, §28).

    Actions: ``scout`` (recognise a need and propose candidates for it),
    ``acquire`` (mark a proposed capability as now-available), ``reject``
    (decline a proposal so it is not re-proposed), ``notice`` (turn recurringly
    unanswered subjects into evidence-grounded needs — the self-initiated half
    of Odysseus), ``list`` (what Jarvis proposes/has), and
    ``recommend``/``stance`` (the evidence-derived stance on acquiring a named
    capability). Acquisition is deliberate and earned; the surface only ever
    *suggests* via the derived stance.
    """
    action = str(payload.get("action", "")).strip().lower()
    name = str(payload.get("name", "")).strip()
    statement = str(payload.get("statement", "")).strip()
    rationale = str(payload.get("rationale", "")).strip()

    if not action:
        capabilities = jarvis.capabilities()
        if not capabilities:
            return {
                "reply": "I have no proposed or acquired capabilities yet — tell me "
                "a capability you think I'd grow from and I'll scout for it.",
                "speak": False,
            }
        lines = [
            f"- {c.name} ({c.status.value}){_ready_marker(jarvis, c.name)}"
            for c in capabilities
        ]
        reply = "Capabilities I know of:\n" + "\n".join(lines)
        recommendations = {c.name: jarvis.capability_stance(c.name).value for c in capabilities}
        return {"reply": reply, "speak": False, "recommendations": recommendations}

    if action == "list":
        capabilities = jarvis.capabilities()
        if not capabilities:
            return {"reply": "No capabilities proposed or acquired yet.", "speak": False}
        lines = [
            f"- {c.name} ({c.status.value}){_ready_marker(jarvis, c.name)}"
            for c in capabilities
        ]
        return {
            "reply": "Capabilities I know of:\n" + "\n".join(lines),
            "speak": False,
            "recommendations": {
                c.name: jarvis.capability_stance(c.name).value for c in capabilities
            },
        }

    if action == "scout":
        if not statement:
            return {
                "reply": "Tell me the capability you'd like (e.g. 'search the web').",
                "speak": False,
            }
        candidates = jarvis.need_capability(statement, rationale or statement)
        if not candidates:
            return {
                "reply": f"I don't yet see a candidate in my toolkit for '{statement}'.",
                "speak": False,
            }
        # Persist the proposals so the companion can later acquire or reject them
        # without re-scouting (repeated needs are recognised, not re-proposed).
        for candidate in candidates:
            jarvis.remember_capability(candidate)
        proposals = [c for c in candidates if c.status is CapabilityStatus.PROPOSED]
        lines = [f"- {c.name}" for c in candidates]
        reply = (
            f"I could grow the ability to '{statement}' by:\n" + "\n".join(lines)
        )
        recommendation = (
            jarvis.capability_stance(proposals[0].name)
            if proposals
            else None
        )
        return {
            "reply": reply,
            "speak": False,
            "capabilities": [
                {"name": c.name, "status": c.status.value} for c in candidates
            ],
            "recommendation": (
                recommendation.value if recommendation is not None else None
            ),
        }

    if action == "recommend":
        if not name:
            return {"reply": "Name a capability to recommend on.", "speak": False}
        recommendation = jarvis.recommend_capability(name)
        return {
            "reply": recommendation.rationale,
            "speak": False,
            "stance": recommendation.stance.value,
            "confidence": recommendation.confidence.value,
        }

    if action == "acquire":
        if not name:
            return {"reply": "Name a capability to acquire.", "speak": False}
        acquired = jarvis.acquire_capability(name)
        if acquired is None:
            return {
                "reply": f"I haven't proposed '{name}' — scout it first.",
                "speak": False,
            }
        return {
            "reply": (
                f"Understood — I now consider '{name}' acquired as a capability."
            ),
            "speak": False,
            "capability": {"name": acquired.name, "status": acquired.status.value},
        }

    if action == "reject":
        if not name:
            return {"reply": "Name a capability to reject.", "speak": False}
        rejected = jarvis.reject_capability(name)
        if rejected is None:
            return {
                "reply": f"I haven't proposed '{name}' — scout it first.",
                "speak": False,
            }
        return {
            "reply": f"Declined — I won't re-propose '{name}'.",
            "speak": False,
            "capability": {"name": rejected.name, "status": rejected.status.value},
        }

    if action == "notice":
        # Auto-initiated growth (Odysseus, Vision §34): detect recurringly
        # unanswered subjects and turn each gap into an evidence-grounded need,
        # scouting what could help. Delegating to the same core path the
        # reflective cycle uses keeps the surface and the autonomous loop aligned.
        proposals = jarvis.auto_scout_gaps()
        if not proposals:
            return {
                "reply": (
                    "I haven't noticed any new subject I keep failing to answer about — "
                    "ask me something and I'll tell you if it becomes a recurring gap."
                ),
                "speak": False,
            }
        lines = [f"- {c.name}" for c in proposals]
        return {
            "reply": (
                "I noticed subjects I keep failing to answer about, and scouted "
                "abilities that could help:\n" + "\n".join(lines)
            ),
            "speak": False,
            "gaps": [
                {"subject": c.name, "candidates": [c.name]} for c in proposals
            ],
        }

    return {"reply": "Unknown capability action.", "speak": False}


def _tool(jarvis: Jarvis, payload: Reply) -> Reply:
    """Exercise Jarvis's acting tools — list or run one (Vision §34, 06_TOOLS_AGENCY).

    ``list`` reports the registered tools (what Jarvis *can* act through); ``run``
    executes one behind the permission gate, so external/destructive tools need an
    explicit ``approved: true`` before anything happens. Nothing here decides
    *whether* to act: the core keeps that deliberate choice; this surface only
    makes an approved act possible and observable.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {"reply": "Use tool with action 'list' or 'run'.", "speak": False}
    if action == "list":
        specs = jarvis.tool_channels()
        if not specs:
            return {"reply": "No tools are registered yet.", "speak": False}
        lines = [_tool_line(spec) for spec in specs]
        return {
            "reply": "Tools I have:\n" + "\n".join(lines),
            "speak": False,
            "count": len(specs),
        }
    if action == "run":
        name = str(payload.get("name", "")).strip()
        if not name:
            return {"reply": "Name a tool to run.", "speak": False}
        raw = payload.get("arguments")
        arguments: dict[str, str] | None = None
        if isinstance(raw, dict):
            items = cast("dict[object, object]", raw)
            arguments = {str(k): str(v) for k, v in items.items()}
        approved = payload.get("approved", False)
        if isinstance(approved, str):
            approved = approved.strip().lower() in ("true", "1", "yes")
        result = jarvis.run_tool(name, arguments, approved=bool(approved))
        return {
            "reply": _tool_run_reply(name, result),
            "speak": False,
            "ok": result.ok,
        }
    return {"reply": "Unknown tool action.", "speak": False}


def _tool_line(spec: ToolSpec) -> str:
    """A readable declaration of one tool, flagging when it needs approval."""
    mark = " (needs approval)" if spec.requires_approval else ""
    return f"- {spec.name}: {spec.description}{mark}"


def _tool_run_reply(name: str, result: ToolCallResult) -> str:
    """What a tool run produced -- its outcome, not a verdict on it (D6)."""
    if result.ok:
        return f"Tool '{name}' ran successfully:\n{result.value or '(no output)'}"
    return f"Tool '{name}' could not run: {result.error}"
