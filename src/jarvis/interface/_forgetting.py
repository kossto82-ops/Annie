"""Forgetting / memory-health handlers (roadmap F2, Vision §10, §22).

Memory health is a *report*; forgetting is a *decision*. The ``forgetting``
command is hard-gated in that order:

- ``health`` / ``dry-run`` are read-only: they list what may fade and why, plus
  what the honesty gates protect. Running them again and again never deletes
  anything (read-only surfaces stay honest).
- ``apply`` is the only track that touches the store, and it forgets exactly the
  statements the caller explicitly names (or ``all: true`` as an explicit
  apply-all). The gates are re-checked at apply time: a statement the caller
  names but the gates now protect is refused, not deleted.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from jarvis.jarvis import Jarvis

# A reply the UI can render and (optionally) speak; some commands add extra fields.
Reply = dict[str, object]


def _string_list(raw: object) -> list[str]:
    """Every non-empty string in an unknown-typed payload value, JSON-clean."""
    if not isinstance(raw, list):
        return []
    items = cast("list[object]", raw)
    result: list[str] = []
    for item in items:
        text = item if isinstance(item, str) else str(item)
        if text.strip():
            result.append(text.strip())
    return result


def _candidates(jarvis: Jarvis) -> list[Reply]:
    """The may-fade candidates from the live health report, as reply items."""
    raw = jarvis.memory_health().get("candidates", [])
    if not isinstance(raw, list):
        return []
    items = cast("list[object]", raw)
    return [cast(Reply, item) for item in items if isinstance(item, dict)]


def _render_health(jarvis: Jarvis, lines: list[str]) -> Reply:
    """The health frame every forgetting reply carries, so the UI stays live."""
    return {
        "reply": "\n".join(lines) if lines else "Memory health: nothing to report.",
        "speak": False,
        "forgetting": jarvis.memory_health(),
    }


def _forgetting(jarvis: Jarvis, payload: Reply) -> Reply:
    """Report memory health, dry-run candidates, or explicitly forget named memories."""
    action = str(payload.get("action", "")).strip().lower()
    if action in ("", "health"):
        return _render_health(
            jarvis,
            [
                "Forgetting is a decision, never a habit: run the dry-run to "
                "see what may fade, then apply it explicitly.",
            ],
        )
    if action == "dry-run":
        health = jarvis.memory_health()
        candidates = _candidates(jarvis)
        protected = _string_list(health.get("protected", []))
        reaffirmed = _string_list(health.get("reaffirmed", []))
        disabled = not health.get("decay_wired", False)
        lines: list[str] = []
        if candidates:
            lines.append("May fade:")
            for entry in candidates:
                statement = str(entry.get("statement", ""))
                confidence = cast("float | int", entry.get("effective_confidence", 0.0) or 0.0)
                effective = float(confidence)
                reason = str(entry.get("reason", ""))
                lines.append(
                    f"- {statement} (effective {effective:.2f}; {reason})"
                )
            lines.append("")
        else:
            lines = ["Nothing is faded enough to forget right now."]
        if protected:
            lines.append(
                "Protected (grounded companion trait): " + ", ".join(protected)
            )
        if reaffirmed:
            lines.append(
                "Recently renewed (anti-nagging): " + ", ".join(reaffirmed)
            )
        if disabled:
            lines.append(
                "Recency decay: not wired -- time does not fade memories yet "
                "(pass a DecayingWeightingPolicy to enable it)."
            )
        else:
            lines.append("Recency decay: wired (recall and confidence agree).")
        return _render_health(jarvis, lines)
    if action == "apply":
        statements = _string_list(payload.get("statements", []))
        if payload.get("all") is True and not statements:
            statements = [str(e.get("statement", "")) for e in _candidates(jarvis)]
            statements = [s for s in statements if s]
        if not statements:
            return _render_health(
                jarvis, ["Name the memories to forget, or apply with all:true."]
            )
        result = jarvis.forget(statements)
        lines = []
        if result.forgotten:
            lines.append("Forgotten: " + "; ".join(result.forgotten))
        if result.refused:
            lines.append(
                "Refused (still protected by an honesty gate): "
                + "; ".join(result.refused)
            )
        if result.missing:
            lines.append("Not found: " + "; ".join(result.missing))
        return _render_health(
            jarvis, lines if lines else ["Nothing to forget."]
        )
    return {
        "error": f"unknown forgetting action: {action} (expected health, dry-run, apply)",
        "speak": False,
    }


Command = Callable[[Jarvis, Reply], Reply]

# The commands this module serves, composed by the command-center router.
COMMANDS: dict[str, Command] = {
    "forgetting": _forgetting,
}