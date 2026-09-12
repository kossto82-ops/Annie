"""Belief/cognition/tuning handlers — the inner reflective surface."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from jarvis.domain.enums.action_stance import ActionStance
from jarvis.domain.enums.deliberation_value import DeliberationValue
from jarvis.executive.executive_controller import subject_of, working_statement
from jarvis.infrastructure.env_settings import settings_from_env
from jarvis.infrastructure.language_model_registry import build_language_model
from jarvis.infrastructure.perceiver_factory import describe
from jarvis.interface._shared import _provenance
from jarvis.jarvis import Jarvis

if TYPE_CHECKING:
    pass

# A reply the UI can render and (optionally) speak; some commands add extra fields.
Reply = dict[str, object]

# How each action stance reads in the spoken reply (the raw enum value still goes
# to the cycle panel; prose gets a natural phrasing).
_ACTION_PHRASE: dict[ActionStance, str] = {
    ActionStance.SUGGEST: "And I'd suggest an action",
    ActionStance.ASK_FIRST: "And I'd ask before taking an action",
    ActionStance.WITHHOLD: "And I'd hold off on an action",
}


def _explain(jarvis: Jarvis, payload: Reply) -> Reply:
    """Explain what Jarvis believes about a topic and *why* (Vision §8) — a stateless
    'why?' over the working belief it already holds, or an honest "no view yet".
    """
    topic = str(payload.get("topic", "")).strip()
    if not topic:
        return {"reply": "Name a topic and I'll explain what I believe about it.", "speak": False}
    belief = jarvis.beliefs.get_by_statement(working_statement(topic))
    if belief is None:
        return {
            "reply": jarvis.voice.phrase(f'I don\'t hold a view on "{topic}" yet.', like=topic),
            "speak": True,
            "provenance": None,
        }
    explanation = belief.explain()
    return {
        "reply": jarvis.voice.phrase(
            explanation.narrate(subject_of(explanation.statement)), like=topic
        ),
        "speak": True,
        "confidence": belief.confidence.value,
        "provenance": _provenance(belief),
    }


def _reflect(jarvis: Jarvis, _payload: Reply) -> Reply:
    """Run the whole reflective cycle and report what it produced (Vision §31)."""
    cycle = jarvis.reflect_cycle()
    if cycle.reflection is None:
        return {
            "reply": "I looked across what I know, but nothing yet connects strongly "
            "enough to reflect on.",
            "speak": True,
            "cycle": None,
        }
    parts = [
        f"I notice that '{cycle.reflection.observation}' underlies several of my beliefs."
    ]
    if cycle.hypothesis is not None:
        parts.append(f"I wonder if {cycle.hypothesis}.")
    if cycle.learned is not None:
        parts.append(f"So I've come to believe: {cycle.learned}.")
    if cycle.action is not None:
        parts.append(f"{_ACTION_PHRASE[cycle.action.stance]} to check it still holds.")
    return {
        "reply": " ".join(parts),
        "speak": True,
        "cycle": {
            "connections": len(cycle.connections),
            "observation": cycle.reflection.observation,
            "hypothesis": cycle.hypothesis,
            "learned": cycle.learned,
            "produced_insight": cycle.produced_insight,
            "action": cycle.action.stance.value if cycle.action is not None else None,
            "reached_action": cycle.reached_action,
        },
    }


def _introspect(jarvis: Jarvis, _payload: Reply) -> Reply:
    """A plain-language account of who Jarvis is, from real state (Vision §29, §30)."""
    return {"reply": jarvis.introspect(), "speak": True}


def _wonder(jarvis: Jarvis, _payload: Reply) -> Reply:
    """Let Jarvis follow its own curiosity, if anything is pulling at it (Vision §16)."""
    impulse = jarvis.feel_curious()
    if impulse is None:
        return {"reply": "Nothing is pulling at my curiosity right now.", "speak": True}
    jarvis.pursue(impulse)
    return {"reply": f"I find myself wondering: {impulse.trigger}", "speak": True}


def _rest(jarvis: Jarvis, _payload: Reply) -> Reply:
    """Restore energy to full (Vision §15) — fatigue, not a hard cap."""
    jarvis.rest()
    return {"reply": "I've rested; my energy is restored.", "speak": False}


def _energy_budget(jarvis: Jarvis, payload: Reply) -> Reply:
    """Tune how hard Jarvis is willing to think, at runtime (Vision §15, §40)."""
    raw = payload.get("budget")
    if raw is None or raw == "":
        jarvis.set_energy_budget(None)
        return {"reply": "Energy budget cleared — I'll think freely.", "speak": False}
    budget = int(raw) if isinstance(raw, int | float | str) else 0
    jarvis.set_energy_budget(budget)
    return {"reply": f"Energy budget set to {budget}.", "speak": False}


def _deliberation(jarvis: Jarvis, payload: Reply) -> Reply:
    """Set how much a deliberation is worth by default (Vision §15, §40).

    ``value`` is ``cheap`` (answer simple problems briefly), ``normal`` (the
    default) or ``high`` (keep the full lifecycle even low on energy). With no
    value the current stance is reported. This only tunes how hard Jarvis thinks
    by default -- a per-call ``value`` still overrides it.
    """
    raw = str(payload.get("value", "")).strip().lower()
    if not raw:
        return {
            "reply": f"Deliberation value is currently '{jarvis.deliberation_value().value}'.",
            "speak": False,
        }
    try:
        value = DeliberationValue(raw)
    except ValueError:
        valid = ", ".join(v.value for v in DeliberationValue)
        message = f"unknown deliberation value '{raw}' — use one of: {valid}."
        return {"error": message, "speak": False}
    jarvis.set_deliberation_value(value)
    return {"reply": f"Deliberation value set to '{value.value}'.", "speak": False}


def _tunables(jarvis: Jarvis, payload: Reply) -> Reply:
    """Report or tune the cognition thresholds at runtime.

    With no fields it just reports the current ``grounded_confidence``,
    ``insight_confidence`` and ``max_goal_reflections``. With any of them it
    builds the updated :class:`CognitiveKnobs` (``dataclasses.replace`` keeps the
    untouched dials) and swaps it via :meth:`Jarvis.set_knobs` — one value object,
    the single source the executive and Jarvis's own gates read. An out-of-range
    value is a clear error, rejected at the value level (D7), never a crash.
    """
    current = jarvis.knobs()
    fields = {
        "grounded_confidence": current.grounded_confidence,
        "insight_confidence": current.insight_confidence,
        "max_goal_reflections": current.max_goal_reflections,
    }
    unknown = sorted(set(payload) - set(fields))
    if unknown:
        return {"error": f"unknown tune knob: {unknown[0]}", "speak": False}
    changes = {name: payload[name] for name in fields if name in payload}
    if not changes:
        return {"reply": "Cognition thresholds:", "tunables": fields, "speak": False}
    try:
        updated = replace(current, **changes)
    except ValueError as error:
        return {"error": str(error), "speak": False}
    jarvis.set_knobs(updated)
    reported = {name: getattr(updated, name) for name in fields}
    return {
        "reply": "Cognition thresholds updated.",
        "tunables": reported,
        "speak": False,
    }


def _learn(jarvis: Jarvis, payload: Reply) -> Reply:
    """Teach Jarvis about the companion from a pasted profile/notes (Vision §5, §38).

    The deliberate way to "train" Jarvis on who you are: the whole text is read through
    the relational channel in ONE pass (cheap, and it respects a provider's per-minute
    limits) into the companion model as ordinary, revisable beliefs. Needs an LLM
    perceiver — the keyword rule can't read prose into traits. A provider failure is
    surfaced, not a crash.
    """
    from jarvis.interface._shared import _provider_error

    text = str(payload.get("text", "")).strip()
    if not text:
        return {"reply": "Paste something about yourself and I'll learn it.", "speak": False}
    try:
        learned = jarvis.note_companion(text)
    except Exception as error:  # noqa: BLE001 - the external-provider boundary
        return {"reply": _provider_error(error), "speak": False}
    traits = [belief.explain().statement for belief in learned]
    if not traits:
        reply = (
            "I read that, but extracted nothing about you — make sure an LLM perceiver "
            "is active in Tools (the keyword rule can't read prose)."
        )
    else:
        reply = f"Learned {len(traits)} things about you. You can see them under Companion."
    return {"reply": reply, "speak": False, "learned": traits}


def _greeting_prompt(facts: list[str], goals: list[str]) -> str:
    """The prompt that voices a warm opening from what Jarvis remembers (memory is
    Jarvis's; the model only phrases it).
    """
    known = "; ".join(facts[:15]) if facts else "nothing yet"
    ongoing = "; ".join(goals[:5]) if goals else "none noted"
    return (
        "You are Jarvis, greeting your companion at the start of a session. "
        f"What you remember about them: {known}. Ongoing goals/projects: {ongoing}. "
        "Write ONE short, warm, natural greeting (at most two sentences). Address them "
        "by name if you know it. If a current project is evident, offer to continue it. "
        "Reply in the language the person appears to use. Output ONLY the greeting."
    )


def _greeting(jarvis: Jarvis, _payload: Reply) -> Reply:
    """A warm opening, grounded in what Jarvis remembers about the companion (Vision §5).

    When an LLM is active it phrases a personalized greeting from the companion model
    (by name, offering to resume a project); otherwise a friendly default. The memory it
    draws on lives in Jarvis, not the model — the model only voices it (§38). Never a
    crash: any failure falls back to the default greeting.
    """
    facts = [belief.explain().statement for belief in jarvis.companion.beliefs()]
    goals = [goal for goal, _ in jarvis.state_summary().recurring_goals]
    if describe(jarvis.perception).get("kind") == "llm":
        try:
            model = build_language_model(settings_from_env())
            spoken = model.complete(_greeting_prompt(facts, goals)).strip()
            if spoken:
                return {"reply": spoken, "speak": False}
        except Exception:  # noqa: BLE001 - a greeting must never break the page
            pass
    if facts:
        reply = "Good to see you again. What are we working on today?"
    else:
        reply = (
            "Hi — I'm Jarvis. Tell me what you're working on, or a bit about yourself, "
            "and I'll remember it and reason it through with you."
        )
    return {"reply": reply, "speak": False}


def _belief(jarvis: Jarvis, payload: Reply) -> Reply:
    """Explore what Jarvis holds as grounded beliefs, with their evidence (F5).

    Actions: ``list`` (every belief with its derived confidence and how many
    pieces of evidence bear for/against it) and ``get`` (``statement`` -- the
    full provenance of one belief, the same grounds the reasoning panel shows).
    Read-only: beliefs are never edited here, only inspected.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {
            "reply": "Use belief with action 'list' or 'get'.",
            "speak": False,
        }
    if action == "list":
        beliefs = sorted(
            jarvis.beliefs.all_beliefs(),
            key=lambda b: b.confidence.value,
            reverse=True,
        )
        if not beliefs:
            return {
                "reply": "I hold no grounded beliefs yet — talk to me and confirm what I reason.",
                "speak": False,
                "beliefs": [],
            }
        entries: list[Reply] = []
        for belief in beliefs:
            explanation = belief.explain()
            entries.append(
                {
                    "statement": explanation.statement,
                    "subject": subject_of(explanation.statement),
                    "confidence": explanation.confidence.value,
                    "supporting": len(explanation.supporting),
                    "contradicting": len(explanation.contradicting),
                }
            )
        lines = [
            f"- {e['subject']} ({e['confidence']:.2f}, "
            f"{e['supporting']}+{e['contradicting']}-)"
            for e in entries
        ]
        return {
            "reply": "What I hold:\n" + "\n".join(lines),
            "speak": False,
            "beliefs": entries,
        }
    if action == "get":
        statement = str(payload.get("statement", "")).strip()
        if not statement:
            return {"reply": "Name a belief statement to inspect.", "speak": False}
        belief = jarvis.beliefs.get_by_statement(statement)
        if belief is None:
            return {
                "reply": f"I hold no belief recorded as {statement!r}.",
                "speak": False,
            }
        grounds = _provenance(belief)
        grounds["statement"] = belief.explain().statement
        return {
            "reply": belief.explain().narrate(subject_of(belief.explain().statement)),
            "speak": False,
            "provenance": grounds,
        }
    return {"reply": "Unknown belief action.", "speak": False}


def _state(_jarvis: Jarvis, _payload: Reply) -> Reply:
    """Just the live snapshot (added by :func:`handle`); no side effects."""
    return {}
