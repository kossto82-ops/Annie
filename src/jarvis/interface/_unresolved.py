"""Open-question handlers (roadmap F3): surfaces over the unresolved store.

Open questions are attention candidates -- asked, not yet answered. Today the
answer mostly *completes* itself, without a surface: once the companion's
turn grounds a belief about an open question, the conversation flow
auto-retires it (``_conversation._retire_answered_questions``). These
handlers make the same lifecycle explicitly inspectable and drivable:

- ``open-questions`` is read-only: it lists what Jarvis is still wondering
  about (the same items curiosity proposes, oldest first). Running it never
  changes anything.
- ``settle-question`` sets an answer explicitly -- ``question`` is the exact
  open question string and ``resolution`` is the answer granted. A question
  that is not currently open is refused, not invented.
"""

from __future__ import annotations

from collections.abc import Callable

from jarvis.jarvis import Jarvis

# A reply the UI can render and (optionally) speak; some commands add extra fields.
Reply = dict[str, object]


def _render(open_questions: list[str], lines: list[str]) -> Reply:
    """The frame every open-question reply carries, so the UI stays live."""
    return {
        "reply": "\n".join(lines) if lines else "No open questions.",
        "speak": False,
        "open_questions": open_questions,
    }


def _open_questions(jarvis: Jarvis, payload: Reply) -> Reply:
    """List the still-open questions, oldest first (read-only)."""
    items = jarvis.open_questions()
    lines: list[str] = []
    if items:
        lines.append("Still wondering:")
        for item in items:
            lines.append(f"- {item.question}")
    return _render([item.question for item in items], lines)


def _settle_question(jarvis: Jarvis, payload: Reply) -> Reply:
    """Explicitly answer one open question; unknown questions are refused."""
    question = str(payload.get("question", "")).strip()
    resolution = str(payload.get("resolution", "")).strip()
    if not question:
        return {"error": "settle-question needs a question", "speak": False}
    if not resolution:
        return {
            "error": f"settle-question needs a resolution: {question!r}",
            "speak": False,
        }
    try:
        jarvis.resolve_open_question(question, resolution)
    except KeyError:
        return {
            "error": f"no open question matches: {question!r}",
            "speak": False,
        }
    items = jarvis.open_questions()
    return _render(
        [item.question for item in items],
        ["Settled:", f"- {question}", f"  -> {resolution}"],
    )


Command = Callable[[Jarvis, Reply], Reply]

# The commands this module serves, composed by the command-center router.
COMMANDS: dict[str, Command] = {
    "open-questions": _open_questions,
    "settle-question": _settle_question,
}