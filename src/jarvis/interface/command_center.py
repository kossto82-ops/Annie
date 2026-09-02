"""The command center's brain: pure request handling over a Jarvis (Vision §30, §40).

Two layers, both pure and hermetic:

* :func:`handle` maps a command name + payload to a JSON-serializable reply by
  calling Jarvis's ordinary public methods — perceive, reflect, introspect, tune
  energy. It invents nothing; every reply traces to what Jarvis actually did or
  holds. Each result carries a fresh :func:`snapshot` so the UI stays live.
* :func:`route` maps an HTTP method + path + body to a :class:`Response` — serving
  the page, ``GET /api/state``, and ``POST /api/<command>`` — with zero sockets, so
  the whole surface is unit-testable without a network.

The socket lives in :mod:`jarvis.interface.server` and only carries these bytes.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from jarvis.domain.conversation.intent import (
    ConversationIntent,
    classify,
    remembered_content,
)
from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.action_stance import ActionStance
from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.model_compare import ModelRun
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.domain.value_objects.research_report import ResearchReport
from jarvis.domain.value_objects.retrieved_document import RetrievedDocument
from jarvis.domain.value_objects.tool_call_result import ToolCallResult
from jarvis.domain.value_objects.tool_spec import ToolSpec
from jarvis.executive.executive_controller import subject_of, working_statement
from jarvis.infrastructure import llm_config_store
from jarvis.infrastructure.env_settings import settings_from_env
from jarvis.infrastructure.language_model_registry import build_language_model
from jarvis.infrastructure.perceiver_factory import (
    available_providers,
    build_companion_perceiver,
    build_perceiver,
    build_reasoner,
    build_renderer,
    describe,
    saved_models,
)
from jarvis.infrastructure.response_renderer import uses_spanish
from jarvis.jarvis import Jarvis

_OFFLINE_PERCEIVERS = frozenset({"", "keyword", "scripted", "stub"})

# A short reply that just affirms or denies is read as confirming (or correcting) the
# last thing Jarvis said, so a provisional reasoned answer can mature (Vision §18, §20).
_AFFIRM = frozenset(
    {"sí", "si", "exacto", "correcto", "cierto", "eso", "vale", "claro", "perfecto",
     "yes", "right", "correct", "exactly", "true", "ok", "okay", "yep", "yeah"}
)
_DENY = frozenset(
    {"no", "incorrecto", "falso", "nope", "wrong", "incorrect", "false", "nah"}
)
# Light connectors/politeness allowed inside a *bare* yes/no ("no, gracias"; "sí, exacto"),
# so a real sentence that merely starts with "no" ("no funcionas bien") is NOT a correction.
_CONFIRMATION_FILLER = frozenset(
    {"y", "pero", "pues", "bueno", "gracias", "por", "favor", "totalmente",
     "the", "that", "please", "thanks", "really", "not"}
)
_MAX_CONFIRMATION_WORDS = 5
_WORD = re.compile(r"\w+")

_CONSOLE_HTML = Path(__file__).with_name("console.html")

# A reply the UI can render and (optionally) speak; some commands add extra fields.
Reply = dict[str, object]
Command = Callable[[Jarvis, Reply], Reply]


@dataclass(frozen=True, slots=True)
class Response:
    """A ready-to-send HTTP response, decided without touching a socket."""

    status: int
    content_type: str
    body: bytes


def snapshot(jarvis: Jarvis) -> Reply:
    """A JSON-ready snapshot of everything Jarvis currently holds (Vision §21, §30).

    Every field traces to real state via :meth:`Jarvis.state_summary` and the energy
    surface; a fresh Jarvis produces an all-empty snapshot with zero energy. This is
    the live model the control center renders after every turn.
    """
    summary = jarvis.state_summary()
    return {
        "episodes": summary.episode_count,
        "perceiver": {
            **describe(jarvis.perception),
            "available": list(available_providers()),
            "models": saved_models(),  # per-provider remembered model, for UI auto-fill
        },
        "energy": {
            "spent": jarvis.energy_spent(),
            "remaining": jarvis.energy_remaining(),
            "conserving": jarvis.is_conserving(),
        },
        "self": [{"statement": s, "confidence": c} for s, c in summary.self_tendencies],
        "companion": [
            {"statement": s, "confidence": c} for s, c in summary.companion_traits
        ],
        "goals": [{"goal": g, "count": n} for g, n in summary.recurring_goals],
        "actions": [
            {"description": a.description, "confidence": a.confidence, "stance": a.stance.name}
            for a in summary.learned_actions
        ],
        "capabilities": [
            {"name": name, "status": status} for name, status in summary.capabilities
        ],
        "needs": [
            {"statement": s, "confidence": c} for s, c in summary.capability_needs
        ],
        "ready": list(jarvis.usable_capabilities()),
    }


def _evidence_json(evidence: Evidence) -> Reply:
    """One piece of evidence as the panel renders it — content, provenance, weight."""
    return {
        "content": evidence.content,
        "source": evidence.source.name,
        "weight": evidence.weight.value,
    }


def _provenance(belief: Belief) -> Reply:
    """Why a belief is held: its derived confidence and the evidence for and against
    it (Vision §8, §40) — the grounds the reasoning panel shows, so the surface
    reveals *why*, not just *what*.
    """
    explanation = belief.explain()
    return {
        # The natural subject, never the internal "Working conclusion about:" label.
        "statement": subject_of(explanation.statement),
        "confidence": explanation.confidence.value,
        "supporting": [_evidence_json(e) for e in explanation.supporting],
        "contradicting": [_evidence_json(e) for e in explanation.contradicting],
    }


def _confirmation(text: str) -> bool | None:
    """Read a short reply as confirming (True), correcting (False), or neither (None).

    Only a brief affirmation/denial counts, so an ordinary sentence that merely contains
    "no" is not mistaken for a correction.
    """
    tokens = _WORD.findall(text.lower())
    if not tokens or len(tokens) > _MAX_CONFIRMATION_WORDS:
        return None
    # Only a *bare* yes/no counts: every word must be an affirmation, a denial, or light
    # filler. A sentence with real content ("no funcionas muy bien") is feedback, not a
    # correction, and must fall through to intent classification.
    allowed = _AFFIRM | _DENY | _CONFIRMATION_FILLER
    if any(token not in allowed for token in tokens):
        return None
    if any(token in _DENY for token in tokens):
        return False
    if any(token in _AFFIRM for token in tokens):
        return True
    return None


def _confirmation_reply(affirm: bool, belief: Belief) -> Reply:
    """Acknowledge that the companion confirmed or corrected the last reasoned answer."""
    confidence = belief.confidence.value
    reply = (
        "Thanks — I'll take that as confirmed and remember it. I hold it more firmly now."
        if affirm
        else "Understood — I'll correct that. I hold it less firmly now."
    )
    return {
        "reply": reply,
        "speak": True,
        "stance": "confirmation",
        "confidence": confidence,
        "provenance": _provenance(belief),
        "trace": [],
    }


def _provider_error(error: Exception) -> str:
    """A clear, actionable message for a language-model failure (Vision §37).

    Surfaces the HTTP status and what it usually means, so a provider misconfiguration
    is self-diagnosing instead of an opaque "HTTPError": 401/403 point at the key or
    an unauthorised model, 404 at a wrong model id (NVIDIA ids look like 'nvidia/…').
    """
    code = getattr(error, "code", None)
    if code == 429:
        return (
            "The language model is rate-limited right now (too many tokens this minute). "
            "Wait a minute and try again, or use a local provider like Ollama."
        )
    if code in (401, 403):
        return (
            f"The provider rejected the request ({code} — authorization failed). The API "
            "key isn't accepted for this model, or the model isn't enabled for your key. "
            "Check the key and model in Tools (get a fresh key from the model's page if "
            "needed), or switch to the keyword perceiver."
        )
    if code == 404:
        return (
            f"The provider returned {code} (not found) for that model — the model id is "
            "almost certainly wrong. Fix it in Tools; NVIDIA ids look like "
            "'nvidia/nemotron-3.5-lightning-30b-a3b', with the 'nvidia/' prefix."
        )
    detail = f"HTTP {code}" if code is not None else type(error).__name__
    return (
        f"I couldn't reach the language model ({detail}). "
        "Check the provider, model, and API key in Tools — or switch to the keyword perceiver."
    )


def _say(jarvis: Jarvis, payload: Reply) -> Reply:
    """Hear what the companion said over both channels (Vision §5, §8): learn about the
    person AND reason about the world, then reply as a companion — not a verdict engine.

    Priority is relational: if the turn taught Jarvis something about *you*, it leads with
    acknowledging that (this is how you "teach" it — it remembers, §5). Otherwise it
    narrates a grounded world-belief, or — when there is nothing to weigh — says so warmly
    and invites more, never scolding "I can't ground a view".
    """
    text = str(payload.get("text", "")).strip()
    if not text:
        return {"reply": "I'm here — tell me something, or ask.", "speak": False}
    try:
        result = _say_core(jarvis, text)
    except Exception as error:  # noqa: BLE001 - the external-provider boundary
        return {"reply": _provider_error(error), "speak": True, "provenance": None, "trace": []}
    # Voice the decided reply in the companion's language (identity offline, Vision §40).
    result["reply"] = jarvis.voice.phrase(str(result["reply"]), like=text)
    return result


def _say_core(jarvis: Jarvis, text: str) -> Reply:
    """Understand the turn, then respond — conversation first, memory only when it fits.

    The pipeline is CONVERSATION → UNDERSTAND INTENT → RESPOND → MEMORY EVALUATION
    (Vision §5, §37): not every message is knowledge. A short yes/no still matures the
    last reasoned answer (the learning loop, §20); otherwise the message's *intent*
    decides. Greetings, small talk, feedback about Jarvis and instructions are answered
    as conversation and never become beliefs; only an explicit "remember this" or a real
    statement/question reaches perception, memory and reasoning. May raise on a provider
    failure (the caller decides how to surface it).
    """
    jarvis.conversation.record("companion", text)
    # A short "yes"/"no" confirms or corrects the last thing Jarvis reasoned, maturing a
    # provisional answer into a grounded belief (the learning loop, Vision §20) — handled
    # before intent, so the confirmation lands on the previous answer.
    verdict = _confirmation(text)
    history = jarvis.episodes.history()
    if verdict is not None and history:
        belief = jarvis.confirm(history[-1].trigger, affirm=verdict)
        if belief is not None:
            return _turn(jarvis, _confirmation_reply(verdict, belief))

    intent = classify(text)
    if intent is ConversationIntent.GREETING:
        return _turn(jarvis, _greeting_reply(jarvis, text))
    if intent is ConversationIntent.SMALLTALK:
        return _turn(jarvis, _smalltalk_reply(text))
    if intent is ConversationIntent.FEEDBACK:
        return _turn(jarvis, _feedback_reply(text))
    if intent is ConversationIntent.INSTRUCTION:
        return _turn(jarvis, _instruction_reply(jarvis, text))
    if intent is ConversationIntent.REMEMBER:
        return _turn(jarvis, _remember_reply(jarvis, text))
    return _turn(jarvis, _knowledge_reply(jarvis, text))


def _turn(jarvis: Jarvis, reply: Reply) -> Reply:
    """Record Jarvis's side of the turn in short-term context and return the reply."""
    jarvis.conversation.record("jarvis", str(reply.get("reply", "")))
    return reply


def _plain(reply: str, stance: str) -> Reply:
    """A purely conversational reply: no belief, no memory, no internal metadata."""
    return {"reply": reply, "speak": True, "stance": stance, "provenance": None, "trace": []}


def _greeting_reply(jarvis: Jarvis, text: str) -> Reply:
    name = _companion_name(jarvis)
    if uses_spanish(text):
        opener = f"Hola, {name}" if name else "Hola"
        return _plain(f"{opener}. Me alegra verte. ¿Qué tienes en mente?", "greeting")
    opener = f"Hi {name}" if name else "Hi"
    return _plain(f"{opener} — good to see you. What's on your mind?", "greeting")


def _smalltalk_reply(text: str) -> Reply:
    if uses_spanish(text):
        return _plain("Bien, aquí estoy. ¿Qué tal tú?", "smalltalk")
    return _plain("I'm here and doing fine — how about you?", "smalltalk")


def _feedback_reply(text: str) -> Reply:
    if uses_spanish(text):
        return _plain(
            "Sí, parece que algo estoy haciendo mal. ¿Qué es lo que más te está fallando?",
            "feedback",
        )
    return _plain(
        "Sounds like I'm getting something wrong. What's failing most for you?", "feedback"
    )


def _instruction_reply(jarvis: Jarvis, text: str) -> Reply:
    """Execute an instruction through an existing capability, or decline honestly.

    A request to check with the configured language model is contextual action, not
    knowledge. The reasoner receives the preceding dialogue so references such as
    "lo" resolve against what the companion and Jarvis were just discussing.
    """
    inference = jarvis.reason(text, conversation=jarvis.conversation.before_current())
    if inference is None:
        unavailable = (
            "Entiendo la instrucción, pero con las capacidades actuales no puedo consultar "
            "otra IA."
            if uses_spanish(text)
            else "I understand the instruction, but I can't consult another AI with the "
            "capabilities currently available."
        )
        return _plain(unavailable, "instruction")
    return _plain(inference.answer, "instruction")


def _remember_reply(jarvis: Jarvis, text: str) -> Reply:
    """The one intent that IS memory: store what the companion explicitly asked to keep."""
    fact = remembered_content(text)
    jarvis.observe_companion(
        fact,
        Evidence(
            content=fact,
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(1.0),
            context="the companion explicitly asked to remember this",
        ),
    )
    wording = f"Entendido. Recordaré que {fact}." if uses_spanish(text) else (
        f"Got it — I'll remember that: {fact}."
    )
    reply = _plain(wording, "memory")
    reply["learned"] = [fact]
    return reply


def _knowledge_reply(jarvis: Jarvis, text: str) -> Reply:
    """Answer ordinary conversation without silently converting it into memory.

    Recent dialogue is the primary context. Existing long-term memory may still help,
    but this path writes neither companion traits nor world beliefs; persistence is
    reserved for explicit remember/learn/confirmation actions.
    """
    recalled = jarvis.recall(text)
    inference = jarvis.reason(
        text,
        memory=recalled,
        conversation=jarvis.conversation.before_current(),
    )
    if inference is not None:
        return _plain(inference.answer, "conversation")
    if recalled:
        return _natural_memory_reply(recalled)
    return _engage_reply(text, None, [])


def _natural_memory_reply(recalled: tuple[RecalledMemory, ...]) -> Reply:
    """Use relevant long-term memory without exposing retrieval mechanics or scores."""
    content = recalled[0].content
    return _plain(f"I remember that {content}. How does that bear on what you mean now?", "memory")


def _engage_reply(text: str, provenance: Reply | None, trace: list[Reply]) -> Reply:
    """Nothing to answer yet — stay in the conversation warmly, never scolding (§37)."""
    if text.strip().endswith("?"):
        reply = "Good question — give me a bit more context and I'll think it through with you."
    else:
        reply = "I'm with you — tell me more and we'll reason it through together."
    return {
        "reply": reply,
        "speak": True,
        "stance": "conversation",
        "provenance": provenance,
        "trace": trace,
    }


def _companion_name(jarvis: Jarvis) -> str | None:
    """The companion's name if Jarvis has learned it, for a warmer greeting (best effort)."""
    for belief in jarvis.companion.beliefs():
        statement = belief.explain().statement.lower()
        for cue in ("name is ", "llama ", "nombre es ", "soy "):
            if cue in statement:
                name = belief.explain().statement.split()[-1].strip(".,!?")
                return name if name.isalpha() else None
    return None


# One streamed event: an event name and its JSON-ready data.
StreamEvent = tuple[str, Reply]


def stream_say(jarvis: Jarvis, payload: Reply) -> Iterator[StreamEvent]:
    """Stream a `say` turn as events: metadata first, then the reply token by token.

    Yields ``("meta", …)`` (provenance, trace, learned, live state) once the reasoning is
    done, then ``("chunk", {"text": …})`` as the voice renders the reply (all at once when
    the model can't stream), then ``("done", {"reply": full})``. A provider failure or
    empty input yields a single ``("done", …)`` with a clear reply — never a broken stream.
    """
    text = str(payload.get("text", "")).strip()
    if not text:
        yield ("done", {"reply": "I'm here — tell me something, or ask.", "speak": False})
        return
    try:
        result = _say_core(jarvis, text)
    except Exception as error:  # noqa: BLE001 - the external-provider boundary
        yield (
            "done",
            {"reply": _provider_error(error), "speak": True, "provenance": None, "trace": []},
        )
        return
    canonical = str(result["reply"])
    meta = {key: value for key, value in result.items() if key != "reply"}
    meta["state"] = snapshot(jarvis)
    yield ("meta", meta)
    voiced: list[str] = []
    for piece in jarvis.voice.phrase_stream(canonical, like=text):
        voiced.append(piece)
        yield ("chunk", {"text": piece})
    yield ("done", {"reply": "".join(voiced)})


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


# How each action stance reads in the spoken reply (the raw enum value still goes
# to the cycle panel; prose gets a natural phrasing).
_ACTION_PHRASE: dict[ActionStance, str] = {
    ActionStance.SUGGEST: "And I'd suggest an action",
    ActionStance.ASK_FIRST: "And I'd ask before taking an action",
    ActionStance.WITHHOLD: "And I'd hold off on an action",
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


def _perceiver(jarvis: Jarvis, payload: Reply) -> Reply:
    """Report or switch the live perceiver at runtime (Vision §32, §38; Track B).

    With no ``provider`` it just reports (the live perceiver rides in every snapshot).
    With one, it swaps the evidence *producer* -- the keyword rule, or an LLM provider
    from the open registry -- without rebuilding Jarvis.

    An optional ``api_key`` lets the developer hand over a real credential to start
    testing: it is applied to the live process and saved to ``.env`` (so a restart
    resumes), but it is write-only -- never echoed back in the reply or any snapshot.
    Without a key, the factory reads whatever ``JARVIS_LLM_API_KEY`` already holds. A
    misconfigured provider (e.g. real provider, no model) is a clear error, not a crash.
    """
    provider = str(payload.get("provider", "")).strip()
    if not provider:
        return {"reply": "Name a provider to switch the perceiver.", "speak": False}
    # If no model is typed, recall the one this provider used last (per-provider memory),
    # so switching back to a provider doesn't require retyping its model.
    model = str(payload.get("model", "")).strip() or llm_config_store.resolve_model(
        provider.lower(), os.environ
    )
    base_url = str(payload.get("base_url", "")).strip() or None
    # The API key is write-only from the page: it is applied to the live process and
    # saved to .env, but never echoed back in any reply or snapshot.
    api_key = str(payload.get("api_key", "")).strip()
    is_real = provider.lower() not in _OFFLINE_PERCEIVERS
    if is_real and not model:
        # A real provider needs a model — reject before staging/persisting anything.
        return {"error": f"a model id is required for provider {provider!r} (e.g. llama-3.3-70b)"}
    # Apply the choice to the live process and build from it. The key is only-from-env:
    # `stage` sets any provided key (write-only) plus the non-secret provider/model so a
    # bare model fix (no key) also takes effect immediately.
    staged = llm_config_store.stage(provider, model, base_url, api_key)
    try:
        source = build_perceiver(provider, model, base_url)
    except ValueError as error:
        return {"error": str(error)}
    jarvis.set_perception(source)
    # Switch the relational perceiver to the same provider, so talking to Jarvis both
    # reasons about the world and learns about you through one model (Vision §5).
    jarvis.set_companion_perception(build_companion_perceiver(provider, model, base_url))
    # And voice replies in the companion's language through the same model (Vision §40).
    jarvis.set_voice(build_renderer(provider, model, base_url))
    # And reason provisional answers through the same model, so a novel question gets
    # a hedged answer instead of a refusal when a provider is active (Vision §37).
    jarvis.set_reasoner(build_reasoner(provider, model, base_url))
    # Persist on every switch so the choice (and model fixes) survive a restart; the key
    # line is only written when a key was provided, and is never read back into a reply.
    llm_config_store.persist(staged)
    described = describe(jarvis.perception)
    saved = " Key saved to .env." if api_key else ""
    if described.get("kind") == "keyword":
        return {
            "reply": f"Perceiver set to the keyword rule (no LLM in judgment).{saved}",
            "speak": False,
            "saved": bool(api_key),
        }
    named = described.get("model") or described.get("provider")
    return {
        "reply": f"Perceiver set to {described.get('provider')} ({named}).{saved}",
        "speak": False,
        "saved": bool(api_key),
    }


def _learn(jarvis: Jarvis, payload: Reply) -> Reply:
    """Teach Jarvis about the companion from a pasted profile/notes (Vision §5, §38).

    The deliberate way to "train" Jarvis on who you are: the whole text is read through
    the relational channel in ONE pass (cheap, and it respects a provider's per-minute
    limits) into the companion model as ordinary, revisable beliefs. Needs an LLM
    perceiver — the keyword rule can't read prose into traits. A provider failure is
    surfaced, not a crash.
    """
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


def _state(_jarvis: Jarvis, _payload: Reply) -> Reply:
    """Just the live snapshot (added by :func:`handle`); no side effects."""
    return {}


# The Internet command (read/search) requires the matching Odysseus capability to
# be *acquired and backed by a provider* -- using it is earned, not automatic.
_EXTERNAL_CAPABILITIES = {
    "read": "read external documents",
    "search": "search the web",
}

_RESEARCH_CAPABILITY = "deep research"
_COMPARE_CAPABILITY = "compare language models"


def _capability_not_ready(jarvis: Jarvis, capability: str) -> Reply:
    """An honest decline when a wired capability is not yet *earned*.

    A capability that is proposed but not acquired reads as "considered but not
    grown" (use `capability acquire`); a capability the scout has not even
    proposed reads as "could gain it" (scout → acquire). Both point forward
    instead of pretending -- acquisition is deliberate and earned (Vision §28).
    """
    known = [c.name for c in jarvis.capabilities()]
    if capability in known:
        prompt = (
            f"I've considered '{capability}' but haven't grown it yet — "
            "use `capability acquire` to accept it."
        )
    else:
        prompt = (
            f"I could gain the '{capability}' capability to do that, but I haven't "
            "proposed or earned it yet — use the `capability` command (scout → acquire)."
        )
    return {"reply": prompt, "speak": False}


def _external_not_ready(jarvis: Jarvis, capability: str) -> Reply:
    """An honest decline when the Internet capability is not usable right now.

    Distinguishes *not wired* (no provider at all -- Jarvis is simply offline)
    from *not earned* (a provider exists but the capability is not yet acquired,
    so using it is a growth the companion has not accepted). Both point forward
    instead of pretending.
    """
    if jarvis.external_source is None:
        return {
            "reply": "No Internet capability is wired up right now — I can still think "
            "and remember, I just can't fetch from the web (agent-reach isn't set up).",
            "speak": False,
        }
    return _capability_not_ready(jarvis, capability)


def _external(jarvis: Jarvis, payload: Reply) -> Reply:
    """Use the Internet capability: read, search, or report channels (Vision §38).

    Jarvis never reaches the Internet on its own for every message -- this command is
    the *deliberate* gate a surface (or an explicit outer decision layer) uses when
    updated/outside information is actually needed. Results carry provenance back to
    Jarvis; it does not write them to memory here. Offline/absent capability or a
    fetch failure is a clear message, never a crash.
    """
    action = str(payload.get("action", "")).strip().lower()
    if not action:
        return {"reply": "Use external with action 'read', 'search' or 'channels'.", "speak": False}
    if action in ("read", "search") and not jarvis.can_do(_EXTERNAL_CAPABILITIES[action]):
        return _external_not_ready(jarvis, _EXTERNAL_CAPABILITIES[action])
    try:
        if action == "channels":
            channels = jarvis.internet_channels()
            if not channels:
                return {
                    "reply": "No Internet capability is wired up right now.",
                    "speak": False,
                }
            lines = [
                f"{c.name}: {c.status}"
                + (f" ({c.active_backend})" if c.active_backend else "")
                for c in channels
            ]
            return {"reply": "External channels:\n" + "\n".join(lines), "speak": False}
        if action == "read":
            url = str(payload.get("url", "")).strip()
            if not url:
                return {"reply": "Provide a url to read.", "speak": False}
            doc = jarvis.read_external(url)
            return {
                "reply": _external_reply(doc),
                "speak": False,
                "source": doc.source,
                "url": doc.url,
            }
        if action == "search":
            query = str(payload.get("query", "")).strip()
            if not query:
                return {"reply": "Provide a query to search.", "speak": False}
            limit_raw = payload.get("limit", 5)
            try:
                limit = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 5
            docs = jarvis.search_external(query, limit=limit)
            return {
                "reply": _external_search_reply(docs),
                "speak": False,
                "count": len(docs),
            }
    except Exception as error:  # noqa: BLE001 - the external-provider boundary
        return {"reply": _external_error(error), "speak": False}
    return {"reply": "Unknown external action.", "speak": False}


def _research(jarvis: Jarvis, payload: Reply) -> Reply:
    """Investigate a question in depth through the research capability (Vision §38).

    Like ``external``, this is a *deliberate* gate: a surface asks for in-depth
    research when outside knowledge is actually needed. The reply is the source's
    plain-language summary plus each cited document's provenance, so the surface
    (and Jarvis) can reason over *what was found* rather than a verdict.
    """
    query = str(payload.get("query", "")).strip()
    if not query:
        return {"reply": "Provide a query to research.", "speak": False}
    if jarvis.research_source is None:
        return {
            "reply": "No research capability is wired up right now — I can still "
            "think and remember, I just can't go look in depth anywhere "
            "(SEARXNG_INSTANCE isn't configured).",
            "speak": False,
        }
    if not jarvis.can_do(_RESEARCH_CAPABILITY):
        return _capability_not_ready(jarvis, _RESEARCH_CAPABILITY)
    try:
        depth_raw = payload.get("depth", 1)
        try:
            depth = int(depth_raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            depth = 1
        report = jarvis.deep_research(query, depth=depth)
        return {
            "reply": _research_reply(report),
            "speak": False,
            "count": len(report.documents),
        }
    except Exception as error:  # noqa: BLE001 - the research-provider boundary
        return {"reply": _research_error(error), "speak": False}


def _research_reply(report: ResearchReport) -> str:
    """A readable summary of a research report, keeping the documents' provenance."""
    lines = [report.summary]
    for i, doc in enumerate(report.documents, 1):
        head = doc.content.strip().replace("\n", " ")
        if len(head) > 200:
            head = head[:200].rstrip() + "…"
        title = f" — {doc.title}" if doc.title else ""
        lines.append(f"{i}. [{doc.source}]{title}\n   {doc.url or '(no url)'}\n   {head}")
    return "\n".join(lines)


def _research_error(error: Exception) -> str:
    """A clear message for a research-capability failure (never a crash)."""
    detail = type(error).__name__
    return (
        f"I couldn't complete that research ({detail}). "
        "It might be a network issue or an unreachable SearXNG instance. "
        "My reasoning and memory are unaffected."
    )


def _compare(jarvis: Jarvis, payload: Reply) -> Reply:
    """Ask several language models the same question and gather their replies blind.

    Like ``external`` and ``research``, this is a *deliberate* gate: a surface calls
    it when it actually wants a model cross-check (Vision §33). The reply names each
    model and shows its text verbatim -- it is candidate evidence for the surface to
    reason over, never a verdict the adapter picked.
    """
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        return {"reply": "Provide a prompt to compare.", "speak": False}
    if jarvis.model_compare is None:
        return {
            "reply": "No model comparison is wired up right now — I can't ask "
            "several models the same question (no comparator configured).",
            "speak": False,
        }
    if not jarvis.can_do(_COMPARE_CAPABILITY):
        return _capability_not_ready(jarvis, _COMPARE_CAPABILITY)
    try:
        selected = payload.get("models")
        models = None
        if isinstance(selected, list):
            raw = cast("list[object]", selected)
            clean = [str(m).strip() for m in raw if str(m).strip()]
            models = clean or None
        runs = jarvis.compare_models(prompt, models=models)
        return {
            "reply": _compare_reply(runs),
            "speak": False,
            "count": len(runs),
        }
    except Exception as error:  # noqa: BLE001 - the model-provider boundary
        return {"reply": _compare_error(error), "speak": False}


def _compare_reply(runs: tuple[ModelRun, ...]) -> str:
    """Each model's reply, labelled by model -- raw candidate evidence, no verdict."""
    if not runs:
        return "No models to compare."
    lines: list[str] = []
    for run in runs:
        text = run.response.strip() or "(empty reply)"
        lines.append(f"{run.model}:\n{text}")
    return "\n\n".join(lines)


def _compare_error(error: Exception) -> str:
    """A clear message for a model-comparison failure (never a crash)."""
    detail = type(error).__name__
    return (
        f"I couldn't complete that comparison ({detail}). "
        "One of the models may be unreachable or misconfigured. "
        "My reasoning and memory are unaffected."
    )


def _external_error(error: Exception) -> str:
    """A clear message for an Internet-capability failure (never a crash).

    Kept apart from the LLM failure phrasing: an external fetch/search can fail
    because no capability is wired, no search provider is configured, a URL is
    unreachable/blocked, or the network is down -- and none of those should read as
    a broken *language model*.
    """
    code = getattr(error, "code", None)
    detail = f"HTTP {code}" if code is not None else type(error).__name__
    return (
        f"I couldn't fetch that from the Internet ({detail}). "
        "It might be a network issue, an unreachable site, or a missing "
        "search/read configuration. My reasoning and memory are unaffected."
    )


def _external_reply(doc: RetrievedDocument) -> str:
    """A short readable summary of one fetched document (provenance plus head)."""
    head = doc.content.strip()
    if len(head) > 400:
        head = head[:400].rstrip() + "…"
    out = f"Source: {doc.source}\nURL: {doc.url or '(n/a)'}"
    if doc.title:
        out += f"\nTitle: {doc.title}"
    return out + f"\n\n{head}"


def _external_search_reply(docs: tuple[RetrievedDocument, ...]) -> str:
    """A readable summary of search results, keeping their provenance."""
    if not docs:
        return "Nothing found for that search."
    parts: list[str] = []
    for i, doc in enumerate(docs, 1):
        head = doc.content.strip().replace("\n", " ")
        if len(head) > 200:
            head = head[:200].rstrip() + "…"
        parts.append(f"{i}. ({doc.source}) {head}")
    return "Search results:\n" + "\n".join(parts)


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
        subjects = jarvis.unanswered_subjects()
        if not subjects:
            return {
                "reply": (
                    "I haven't noticed any subject I keep failing to answer about — "
                    "ask me something and I'll tell you if it becomes a recurring gap."
                ),
                "speak": False,
            }
        # Auto-initiated growth (Odysseus, Vision §34): I record the gap as an
        # evidence-grounded need to be able to answer about it, then scout what
        # could help. The request is loaded with M/2 evidence -- one for each
        # way I failed -- so the need's confidence is derived, never asserted.
        half = len(subjects) // 2 or 1

        notices: list[dict[str, str | list[str]]] = []
        for subject in subjects[:half]:
            candidates = jarvis.recognise_need(
                f"answer questions about {subject}",
                rationale=(
                    f"I keep failing to conclude about {subject} in my own "
                    "episode history"
                ),
                evidence=[
                    Evidence(
                        content=(
                            f"I completed an episode about {subject} without a "
                            "grounded conclusion"
                        ),
                        source=EvidenceSource.USER_STATEMENT,
                        weight=Confidence(0.5),
                    )
                ],
            )
            notices.append(
                {
                    "subject": subject,
                    "candidates": [c.name for c in candidates],
                }
            )
        lines = [
            f"- {notice['subject']}: "
            + (", ".join(notice["candidates"]) if notice["candidates"] else "no candidate yet")
            for notice in notices
        ]
        return {
            "reply": (
                "I noticed subjects I keep failing to answer about, and recorded a "
                "need to be able to answer them:\n" + "\n".join(lines)
            ),
            "speak": False,
            "gaps": notices,
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


def _ready_marker(jarvis: Jarvis, capability: str) -> str:
    """A concise "(ready)" taste when an acquired capability is live-backed."""
    return " (ready)" if jarvis.can_do(capability) else ""


_COMMANDS: dict[str, Command] = {
    "say": _say,
    "explain": _explain,
    "reflect": _reflect,
    "introspect": _introspect,
    "wonder": _wonder,
    "rest": _rest,
    "energy_budget": _energy_budget,
    "perceiver": _perceiver,
    "learn": _learn,
    "greeting": _greeting,
    "state": _state,
    "external": _external,
    "research": _research,
    "compare": _compare,
    "capability": _capability,
    "tool": _tool,
}


def handle(jarvis: Jarvis, command: str, payload: Reply) -> Reply:
    """Run one command against ``jarvis`` and return a JSON-ready reply + live state.

    An unknown command is a clear error, never a silent no-op. Every reply carries a
    fresh :func:`snapshot`, so a single round-trip updates the whole control center.
    """
    run = _COMMANDS.get(command)
    if run is None:
        return {"error": f"unknown command: {command}", "state": snapshot(jarvis)}
    result = run(jarvis, payload)
    result["state"] = snapshot(jarvis)
    return result


def _parse(body: bytes) -> Reply:
    """Best-effort JSON object from a request body; anything else is an empty payload."""
    if not body:
        return {}
    try:
        loaded: object = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Malformed or non-UTF-8 body -> empty payload, never a 500.
        return {}
    return cast("Reply", loaded) if isinstance(loaded, dict) else {}


def parse_body(body: bytes) -> Reply:
    """Public wrapper over the request-body parser, for the streaming server path."""
    return _parse(body)


def _json(payload: Reply) -> bytes:
    return json.dumps(payload).encode("utf-8")


def route(jarvis: Jarvis, method: str, path: str, body: bytes) -> Response:
    """Decide the response for one HTTP request — pure, no socket (Vision §30).

    Serves the console page at ``/``, the live snapshot at ``GET /api/state``, and a
    command at ``POST /api/<command>``. This is the whole HTTP contract, testable
    without binding a port; :mod:`jarvis.interface.server` only moves the bytes.
    """
    clean = path.split("?", 1)[0]
    if method == "GET" and clean in ("/", "/index.html"):
        return Response(200, "text/html; charset=utf-8", _CONSOLE_HTML.read_bytes())
    if clean.startswith("/api/"):
        command = clean[len("/api/") :].strip("/") or "state"
        payload = _parse(body) if method == "POST" else {}
        result = handle(jarvis, command, payload)
        status = 400 if "error" in result else 200
        return Response(status, "application/json; charset=utf-8", _json(result))
    return Response(404, "application/json; charset=utf-8", _json({"error": f"not found: {clean}"}))
