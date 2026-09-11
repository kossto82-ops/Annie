"""Chat/say pipeline — the conversation surface of the command center."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TYPE_CHECKING

from jarvis.domain.conversation.intent import (
    ConversationIntent,
    classify,
    remembered_content,
)
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.infrastructure.response_renderer import uses_spanish
from jarvis.jarvis import Jarvis

from jarvis.interface._shared import (
    _AFFIRM,
    _CONFIRMATION_FILLER,
    _DENY,
    _MAX_CONFIRMATION_WORDS,
    _companion_name,
    _provider_error,
    _provenance,
)

if TYPE_CHECKING:
    pass

_WORD = re.compile(r"\w+")

# A reply the UI can render and (optionally) speak; some commands add extra fields.
Reply = dict[str, object]


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


def _confirmation_reply(affirm: bool, belief: object) -> Reply:
    """Acknowledge that the companion confirmed or corrected the last reasoned answer."""
    from jarvis.domain.entities.belief import Belief

    assert isinstance(belief, Belief)
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
    as conversation and never become beliefs; a material directive (an act) is executed
    through the earned-agency executor when one is wired and declined honestly
    otherwise; only an explicit "remember this" or a real
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
    if intent is ConversationIntent.ACT:
        return _turn(jarvis, _act_reply(jarvis, text))
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
        return _plain(
            f"{opener}. Soy Jarvis, tu compañero. Me alegra verte. ¿Qué tienes en mente?",
            "greeting",
        )
    opener = f"Hi {name}" if name else "Hi"
    return _plain(
        f"{opener} — I'm Jarvis, your companion. Good to see you. What's on your mind?",
        "greeting",
    )


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


def _act_reply(jarvis: Jarvis, text: str) -> Reply:
    """Perform a *material* instruction through the earned-agency executor, or
    decline honestly when none is wired (Vision §27, §28).

    The companion's words authorize protocol-level acts only: the executor runs a
    sandboxed registry without approval, so locally reversible acts happen and
    external/destructive ones refuse through the gate. Whatever the outcome, the
    reply narrates *what actually happened* -- never a fabricated success.
    """
    if jarvis.instruction_agent is None:
        unavailable = (
            "Entiendo la instrucción, pero ahora mismo no tengo un agente de tareas "
            "configurado para ejecutarla (JARVIS_AGENT_ROOT)."
            if uses_spanish(text)
            else "I understand the instruction, but I have no task agent configured "
            "to execute it right now (JARVIS_AGENT_ROOT)."
        )
        return _plain(unavailable, "act")
    outcome = jarvis.execute(text)
    if outcome.success:
        told = (
            f"Listo — {outcome.summary}."
            if uses_spanish(text)
            else f"Done — {outcome.summary}."
        )
    else:
        told = (
            f"No pude completarlo: {outcome.summary}."
            if uses_spanish(text)
            else f"I couldn't complete it: {outcome.summary}."
        )
    return _plain(told, "act")


def _remember_reply(jarvis: Jarvis, text: str) -> Reply:
    """The one intent that IS memory: store what the companion explicitly asked to keep.

    The fact lands on the relational channel (companion trait) and is ALSO grounded as
    a full cognitive episode (world belief + episode record + trace), so an explicit
    "remember" is durable, shows up in the panel, and gives the yes/no confirmation
    loop an episode to mature (Vision §5, §8, §20).
    """
    fact = remembered_content(text)
    evidence = Evidence(
        content=fact,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(1.0),
        context="the companion explicitly asked to remember this",
    )
    jarvis.observe_companion(fact, evidence)
    jarvis.think(fact, (evidence,), conversation=jarvis.conversation.before_current())
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
    reserved for explicit remember/learn/confirmation actions. Stored documents that
    bear on the turn ride along as honest chips -- the companion sees which of its
    own files Jarvis is drawing from, never a verdict about them.
    """
    recalled = jarvis.recall(text)
    documents = _document_recall(recalled)
    memories = tuple(r for r in recalled if r.kind is not MemoryKind.DOCUMENT)
    inference = jarvis.reason(
        text,
        memory=recalled,
        conversation=jarvis.conversation.before_current(),
    )
    if inference is not None:
        reply = _plain(inference.answer, "conversation")
    elif memories:
        reply = _natural_memory_reply(memories)
    elif documents:
        reply = _document_note(documents)
    else:
        reply = _engage_reply(text, None, [])
    if documents:
        reply["documents"] = [
            {"name": _document_name_from(r), "snippet": r.content} for r in documents
        ]
    return reply


def _document_recall(recalled: tuple[RecalledMemory, ...]) -> tuple[RecalledMemory, ...]:
    """The recalled items that are stored documents, in recall order."""
    return tuple(r for r in recalled if r.kind is MemoryKind.DOCUMENT)


def _document_name_from(memory: RecalledMemory) -> str:
    """The document's name from its provenance (``document: <name>``)."""
    return memory.provenance.removeprefix("document: ") or memory.content


def _document_note(documents: tuple[RecalledMemory, ...]) -> Reply:
    """Honestly surface that Jarvis finds the answer in the companion's own file."""
    first = documents[0]
    name = _document_name_from(first)
    return _plain(
        f"I have a file that bears on that — {name}: \"{first.content}\". "
        "Want me to read it?",
        "conversation",
    )


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
    # Import here to avoid circular dependency at module level.
    from jarvis.interface.command_center import snapshot

    meta["state"] = snapshot(jarvis)
    yield ("meta", meta)
    voiced: list[str] = []
    for piece in jarvis.voice.phrase_stream(canonical, like=text):
        voiced.append(piece)
        yield ("chunk", {"text": piece})
    yield ("done", {"reply": "".join(voiced)})
