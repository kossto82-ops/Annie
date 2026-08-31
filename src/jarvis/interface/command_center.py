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
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.events.belief_events import (
    BeliefStrengthened,
    BeliefWeakened,
    ContradictionDetected,
)
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.events.episode_events import EpisodeCompleted, EpisodeStarted
from jarvis.domain.events.evidence_events import EvidenceAdded
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.executive.executive_controller import (
    STRONG_RECALL_RELEVANCE,
    remembered_inference,
    subject_of,
    working_statement,
)
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


def _recalled_json(memory: RecalledMemory) -> Reply:
    """One recalled memory as the panel renders it — content, kind, source, match."""
    return {
        "content": memory.content,
        "kind": memory.kind.name,
        "provenance": memory.provenance,
        "relevance": memory.relevance,
    }


def _memory_reply(
    recalled: tuple[RecalledMemory, ...], provenance: Reply | None, trace: list[Reply]
) -> Reply:
    """Answer from what Jarvis remembers when it holds no grounded view (Vision §3).

    A distinct cognitive stance from belief and from ignorance: it reports remembered
    context, clearly as memory (never asserted as a fresh conclusion, §22). A strong
    match answers directly; a weak one offers the related memory but stays honest that
    it may not settle the question (§37).
    """
    contents = "; ".join(memory.content for memory in recalled[:3])
    if recalled[0].relevance >= STRONG_RECALL_RELEVANCE:
        reply = f"Yes — I remember {contents}."
        stance = "memory"
    else:
        reply = (
            "I don't hold a firm view on that, but I remember something related — "
            f"{contents}. I don't find that we settled it, though."
        )
        stance = "partial_memory"
    return {
        "reply": reply,
        "speak": True,
        "stance": stance,
        "recalled": [_recalled_json(memory) for memory in recalled],
        "provenance": provenance,
        "trace": trace,
    }


def _inference_reply(
    answer: str,
    recalled: tuple[RecalledMemory, ...],
    provenance: Reply | None,
    trace: list[Reply],
) -> Reply:
    """Answer by reasoning when belief and memory have nothing (Vision §37).

    A distinct stance, honestly framed as provisional: Jarvis says it does not recall
    settling this and is reasoning from understanding, so the reader never mistakes an
    inference for a remembered fact or a grounded conclusion (Vision §38). It invites a
    yes/no so the answer can be confirmed and remembered (the learning loop, Vision §20).
    """
    reply = (
        "I don't recall us settling this, but reasoning from what I understand: "
        f"{answer} — is that right? Tell me and I'll remember it."
    )
    result: Reply = {
        "reply": reply,
        "speak": True,
        "stance": "inference",
        "inference": {"answer": answer},
        "provenance": provenance,
        "trace": trace,
    }
    if recalled:
        result["recalled"] = [_recalled_json(memory) for memory in recalled]
    return result


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


def _trace_steps(events: tuple[CognitiveEvent, ...]) -> list[Reply]:
    """An episode's cognitive events as ordered, human-readable steps (Vision §26) —
    the chain the panel draws so you can watch the reasoning, not just read the reply.
    """
    steps: list[Reply] = []
    for event in events:
        if isinstance(event, EpisodeStarted):
            steps.append({"step": "started", "detail": event.trigger})
        elif isinstance(event, EvidenceAdded):
            steps.append(
                {"step": "weighed evidence", "detail": "for" if event.supports else "against"}
            )
        elif isinstance(event, BeliefStrengthened):
            steps.append({"step": "belief strengthened", "detail": f"{event.confidence.value:.2f}"})
        elif isinstance(event, BeliefWeakened):
            steps.append({"step": "belief weakened", "detail": f"{event.confidence.value:.2f}"})
        elif isinstance(event, ContradictionDetected):
            steps.append({"step": "contradiction noted", "detail": "a held belief was opposed"})
        elif isinstance(event, EpisodeCompleted):
            steps.append({"step": "concluded", "detail": event.result})
        else:
            steps.append({"step": type(event).__name__, "detail": ""})
    return steps


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
        return _turn(jarvis, _greeting_reply(jarvis))
    if intent is ConversationIntent.SMALLTALK:
        return _turn(jarvis, _smalltalk_reply())
    if intent is ConversationIntent.FEEDBACK:
        return _turn(jarvis, _feedback_reply())
    if intent is ConversationIntent.INSTRUCTION:
        return _turn(jarvis, _instruction_reply())
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


def _greeting_reply(jarvis: Jarvis) -> Reply:
    name = _companion_name(jarvis)
    opener = f"Hi {name}" if name else "Hi"
    return _plain(f"{opener} — good to see you. What's on your mind?", "greeting")


def _smalltalk_reply() -> Reply:
    return _plain("I'm here and doing fine — how about you?", "smalltalk")


def _feedback_reply() -> Reply:
    # Feedback about Jarvis is heard as conversation, never stored as a belief.
    return _plain(
        "Sounds like I'm getting something wrong. What's failing most for you?", "feedback"
    )


def _instruction_reply() -> Reply:
    # An instruction is interpreted, not remembered — and Jarvis is honest about what it
    # can actually do (no fabricated "I checked with the AI"). Real tool execution is
    # earned agency (Vision §28), not yet wired.
    return _plain(
        "Got it — I'll treat that as an instruction, not something to remember. I can't "
        "consult another AI on my own yet, so tell me exactly what to do with what I know "
        "and I'll take it from there.",
        "instruction",
    )


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
    reply = _plain(f"Got it — I'll remember that: {fact}.", "memory")
    reply["learned"] = [fact]
    return reply


def _knowledge_reply(jarvis: Jarvis, text: str) -> Reply:
    """A real statement/question: perceive, recall and reason — but reply like a person.

    This is the only conversational path that touches perception and memory. The
    relational channel still learns stable facts about the person here (a genuine
    self-disclosure, not a greeting or a complaint — those never reach this path). The
    reply never exposes internal state (confidence, evidence, sources); a grounded belief
    still forms and can be inspected with `explain`/`why`, it just isn't narrated back.
    """
    episode = jarvis.perceive(text, trigger=text)
    learned = jarvis.note_companion(text)  # the relational channel (Vision §5)
    trace = _trace_steps(jarvis.trace_of(episode))
    belief = episode.working_belief
    remembered = remembered_inference(belief) if belief is not None else None
    inferred = (
        episode.inference.answer
        if episode.inference is not None
        else (remembered.content if remembered is not None else None)
    )
    provenance = _provenance(belief) if belief is not None else None
    recalled = episode.recalled_memories
    strong_memory = bool(recalled) and recalled[0].relevance >= STRONG_RECALL_RELEVANCE
    if learned:
        # A genuine self-disclosure taught Jarvis something about you — acknowledge it
        # naturally (this is how you "teach" it, §5), without exposing internal state.
        traits = [b.explain().statement for b in learned]
        summary = "Got it — I'll remember that about you: " + "; ".join(traits) + "."
        reply = _plain(summary, "memory")
        reply["learned"] = traits
        reply["provenance"] = provenance
        reply["trace"] = trace
        return reply
    if inferred is not None:
        # A reasoned answer (fresh or remembered): give it, honestly provisional (§37).
        return _inference_reply(inferred, recalled, provenance, trace)
    if strong_memory or recalled:
        # A memory bears on this: use it naturally, as memory (§22) — never a verdict.
        return _memory_reply(recalled, provenance, trace)
    return _engage_reply(text, provenance, trace)


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
