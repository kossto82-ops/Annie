"""Chat/say pipeline — the conversation surface of the command center."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

from jarvis.domain.conversation.intent import (
    ConversationIntent,
    classify,
    remembered_content,
)
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.services.abstraction import relatedness
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.infrastructure.response_renderer import uses_spanish
from jarvis.interface._external import (
    EXTERNAL_CAPABILITIES,
    external_not_ready,
)
from jarvis.interface._shared import (
    companion_name,
    provenance,
    provider_error,
)
from jarvis.jarvis import Jarvis

if TYPE_CHECKING:
    pass

_WORD = re.compile(r"\w+")

# How many words a turn needs before Jarvis keeps it as a statement. A bare "no",
# "sí", "vale" that fell through the confirmation read is a fragment, not knowledge.
_MIN_STATEMENT_WORDS = 3

# A turn that ends with "?" or opens with an interrogative is a question: Jarvis
# answers it (from memory and reasoning), it is never itself stored. "cuando/when"
# openers are deliberately excluded -- "cuando yo digo X quiero decir Y" is a
# definitional statement, not a question.
_QUESTION_OPENERS = frozenset(
    {
        "qué", "cual", "cuál", "quien", "quién", "quiénes", "quienes",
        "como", "cómo", "donde", "dónde", "cuanto", "cuánto", "cuanta", "cuánta",
        "what", "which", "who", "whom", "whose", "where", "why", "how",
        "is", "are", "was", "were", "do", "does", "did", "can", "could",
        "would", "should", "will", "may", "might", "am",
    }
)

# First-person markers (bilingual): when the companion speaks about themselves, the
# fact lands on the relational channel too, so a later self-question ("what am I
# building?") finds it regardless of wording -- surface-token recall cannot bridge it.
_FIRST_PERSON = frozenset(
    {
        "i", "my", "me", "mine", "myself", "we", "our", "ours", "us",
        "yo", "mi", "mis", "mí", "mío", "mía", "míos", "mías",
        "nuestro", "nuestra", "nuestros", "nuestras",
        "soy", "estoy", "quiero", "prefiero", "necesito", "me gusto", "me gusta",
        "voy", "tengo", "llamo", "puedo", "creo", "considero", "deseo",
    }
)

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
        "provenance": provenance(belief),
        "trace": [],
    }


def _is_question(text: str) -> bool:
    """A turn is a question -- answered, never stored -- when it ends with ``?``
    or opens with an interrogative word."""
    stripped = text.strip()
    if stripped.endswith("?"):
        return True
    first = _WORD.findall(stripped.lower().lstrip("¿¡"))
    return bool(first and first[0] in _QUESTION_OPENERS)


def _has_first_person(text: str) -> bool:
    """True when the companion is speaking about themselves (relational channel)."""
    tokens = set(_WORD.findall(text.lower()))
    return bool(tokens & _FIRST_PERSON)


# Explicit "I changed my mind" markers. These are *decision-change* signals, not
# generic continuity: a sentence that opens with one revises an earlier stance
# instead of accumulating a second, parallel one (temporal/decision resolution,
# Vision §18 -- the change is first-class, never a silent merge).
_REVISION_CUES = (
    "he cambiado de opinión",
    "cambié de opinión",
    "cambié de parecer",
    "he cambiado de idea",
    "me retracto",
    "i changed my mind",
    "i've changed my mind",
    "i have changed my mind",
    "on second thought",
    "i changed my position",
)

# Mid-sentence reversal phrases: they announce the same decision-change even when
# they do not open the sentence ("ya no quiero X" replaces the old X).
_REVISION_PHRASES = ("ya no quiero", "i no longer want")


def _is_revision(text: str) -> bool:
    """True when the companion explicitly marks the turn as a decision change."""
    lowered = text.strip().lower()
    return any(lowered.startswith(cue) for cue in _REVISION_CUES) or any(
        cue in lowered for cue in _REVISION_PHRASES
    )


def _revision_residue(text: str) -> str:
    """The new stance itself, with a leading change-of-mind marker stripped.

    "He cambiado de opinión. Quiero que Jarvis pueda usar muchas herramientas."
    keeps the clean current stance ("Quiero que Jarvis ..."). Mid-sentence
    reversals keep the whole sentence (a negation frame is itself the stance).
    """
    stripped = text.strip()
    lowered = stripped.lower()
    for cue in _REVISION_CUES:
        if lowered.startswith(cue):
            # lstrip (not strip) the marker's trailing separators: the residue
            # keeps its own trailing punctuation, so it can still equal the
            # exact current stance when the companion merely re-affirms it.
            rest = stripped[len(cue) :].lstrip(" .,;:!?¿¡-").strip()
            if not rest:
                return stripped
            return rest[0].upper() + rest[1:]
    return stripped


def _resolve_revision_target(jarvis: Jarvis, residue: str) -> str | None:
    """The existing companion trait the new stance supersedes, if any.

    Re-stating the *current* stance confirms it (returns it directly). Otherwise
    the trait whose words or meaning best match the residue is the one being
    revised -- a changed mind addresses the nearest prior stance (deterministic,
    best-overlap; ties fall to the first held). None when nothing matches: the
    marker with no prior stance is an ordinary new observation.
    """
    lowered = residue.strip().lower()
    for belief in jarvis.companion.beliefs():
        if belief.statement.strip().lower() == lowered:
            return belief.statement
    best: tuple[float, str] | None = None
    for belief in jarvis.companion.beliefs():
        strength = relatedness(residue, belief.statement)
        if strength <= 0.0:
            continue
        if best is None or strength > best[0]:
            best = (strength, belief.statement)
    return best[1] if best is not None else None


def _remember_statement(jarvis: Jarvis, text: str) -> None:
    """Keep a real statement so it is still there tomorrow (Vision §5, §8).

    The everyday thing Jarvis was told -- "my boat is called Seabird", a decision,
    a preference -- is stored the same way an explicit "remember" is. First-person
    statements also land on the relational channel, so a later self-question
    ("what am I building?") bridges to what was said regardless of wording.
    An explicit change-of-mind (``_is_revision``) resolves the decision instead of
    stacking a second parallel stance: the newest text becomes the current trait
    and the superseded one stays archived as its precedent. Questions never reach
    this path.
    """
    evidence = Evidence(
        content=text,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(1.0),
        context="stated in conversation",
    )
    current_stance = text
    if _has_first_person(text) and _is_revision(text):
        residue = _revision_residue(text)
        replaces = _resolve_revision_target(jarvis, residue)
        if replaces is not None:
            jarvis.revise_companion(residue, evidence, replaces=replaces)
            current_stance = residue
        else:
            jarvis.observe_companion(text, evidence)
    elif _has_first_person(text):
        jarvis.observe_companion(text, evidence)
    jarvis.think(current_stance, (evidence,), conversation=jarvis.conversation.before_current())


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
        return {"reply": provider_error(error), "speak": True, "provenance": None, "trace": []}
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
    otherwise. A real statement is the everyday way to teach Jarvis -- it is stored
    so it is still there tomorrow; a question is answered from memory and reasoning
    and is itself never stored. May raise on a provider failure (the caller decides
    how to surface it).
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
            # A confirmation grounds the confirmed conclusion: if it was an open
            # question's echo, the question is now answered (F3 auto-retire).
            _retire_answered_questions(jarvis, history[-1].trigger)
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
    # A real statement is the everyday way to teach Jarvis: it is stored (the
    # "no se acuerda de mí" failure was that nothing was ever written here). A
    # question is answered from memory and reasoning and is itself not stored.
    if len(_WORD.findall(text)) >= _MIN_STATEMENT_WORDS and not _is_question(text):
        _remember_statement(jarvis, text)
    answer = _knowledge_reply(jarvis, text)
    _retire_answered_questions(jarvis, text)
    return _turn(jarvis, answer)


def _retire_answered_questions(jarvis: Jarvis, text: str) -> None:
    """Settle every open question this turn grounded (roadmap F3 auto-retire).

    An open question stops competing for attention once the companion's turn
    *re-triggers* it (it bears on the question at the recall relevance floor)
    and Jarvis now holds a grounded belief about it (confidence >= the grounded
    knob). Matching alone never retires — an ungrounded "I still wonder …"
    stays open (the grace rule); only :meth:`Jarvis.resolve_open_question`
    writes, resolving the item with the grounded evidence as the answer. This
    path is the conversation surface only: CURIOSITY echoes raised by
    ``feel_curious``/``pursue`` are episodes, not turns, and never reach it, and
    the writer's exact-string dedup (Inc 170) is untouched.
    """
    settled: set[str] = set()
    for item, answer in jarvis.retirable_open_questions(text):
        if item.question in settled:
            continue
        jarvis.resolve_open_question(item.question, answer)
        settled.add(item.question)


def _turn(jarvis: Jarvis, reply: Reply) -> Reply:
    """Record Jarvis's side of the turn in short-term context and return the reply."""
    jarvis.conversation.record("jarvis", str(reply.get("reply", "")))
    return reply


def _plain(reply: str, stance: str) -> Reply:
    """A purely conversational reply: no belief, no memory, no internal metadata."""
    return {"reply": reply, "speak": True, "stance": stance, "provenance": None, "trace": []}


def _greeting_reply(jarvis: Jarvis, text: str) -> Reply:
    name = companion_name(jarvis)
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


# Web search cues (Spanish + English)
_SEARCH_CUES = (
    "busca", "búscame", "busca en", "buscar en", "buscar",
    "search", "look up", "find out", "google", "search for",
)

def try_external_search(jarvis: Jarvis, text: str) -> Reply | None:
    """Route a web search request to the real external source, or decline honestly.

    Only the search cue itself is enough to decide there *is* a search request. What
    the companion asked for (INSTRUCTION vs a bare conversational turn already happened
    upstream): here we just check whether a real web-search backend is actually wired.
    When it is, we run it (search_external) and narrate the real results. When the
    request is clearly a web search but no backend is wired, we say so plainly with the
    exact missing prerequisite -- never slip into a fake chatbot answer, never invent
    results (Vision §25, 06_TOOLS_AGENCY).
    """
    text_lower = text.lower().strip()
    is_search = any(cue in text_lower for cue in _SEARCH_CUES)
    if not is_search:
        return None
    if not jarvis.can_do("search the web"):
        return external_not_ready(jarvis, EXTERNAL_CAPABILITIES["search"])
    # Extract the query (strip the search cue prefix)
    query = text
    for cue in ("búscame", "busca en", "buscar en", "buscar", "busca",
                "search for", "look up", "find out", "google", "search"):
        if text_lower.startswith(cue):
            query = text[len(cue):].strip().strip(":").strip()
            break
    if not query:
        return None
    try:
        results = jarvis.search_external(query, limit=3)
        if not results:
            no_results = (
                f"No encontré resultados para \"{query}\" en la web."
                if uses_spanish(text)
                else f"No results found for \"{query}\" on the web."
            )
            return _plain(no_results, "instruction")
        lines: list[str] = []
        for i, doc in enumerate(results, 1):
            title = doc.title or doc.url
            snippet = doc.content[:200]
            lines.append(f"{i}. **{title}**\n   {snippet}\n   {doc.url}")
        results_text = "\n\n".join(lines)
        prefix = (
            f"Encontré esto para \"{query}\":"
            if uses_spanish(text)
            else f"Here's what I found for \"{query}\":"
        )
        return _plain(f"{prefix}\n\n{results_text}", "instruction")
    except Exception:
        error = (
            "No pude buscar en la web ahora mismo — el servicio puede estar caído."
            if uses_spanish(text)
            else "Web search is unavailable right now — the service may be down."
        )
        return _plain(error, "instruction")


def _instruction_reply(jarvis: Jarvis, text: str) -> Reply:
    """Execute an instruction through an existing capability, or decline honestly.

    A request to check with the configured language model is contextual action, not
    knowledge. The reasoner receives the preceding dialogue so references such as
    "lo" resolve against what the companion and Jarvis were just discussing.
    """
    # Check if this is a web search request and route to external source directly
    search_result = try_external_search(jarvis, text)
    if search_result is not None:
        return search_result

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
    """Answer from memory and reasoning, keeping the reply plain and conversational.

    Statements were stored before this was called and are acknowledged
    conversationally -- reciting them back as "memory" would replay the
    conversation into itself. A question may be answered from memory: after the
    recent dialogue (the primary context) and reasoning, long-term memory may
    still settle it -- this is why a fact told yesterday surfaces today -- while
    the conversation's own recent echoes are never recited as the answer. This
    path never leaks internal metadata into the reply. Stored documents that
    bear on the turn ride along as honest chips -- the companion sees which of
    its own files Jarvis is drawing from, never a verdict about them.
    """
    recalled = jarvis.recall(text)
    documents = _document_recall(recalled)
    inference = jarvis.reason(
        text,
        memory=recalled,
        conversation=jarvis.conversation.before_current(),
    )
    if inference is not None:
        reply = _plain(inference.answer, "conversation")
    elif _is_question(text):
        answer = _answer_candidates(recalled)
        if answer:
            reply = _natural_memory_reply(answer)
        elif documents:
            reply = _document_note(documents)
        else:
            reply = _engage_reply(text, None, [])
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


def _answer_candidates(recalled: tuple[RecalledMemory, ...]) -> tuple[RecalledMemory, ...]:
    """Recalled items Jarvis can honestly *answer from*.

    Long-term knowledge (beliefs, episodes, goals, companion traits) may settle
    a question. The conversation's own recent turns and stored documents are
    excluded: echoing a recent turn back as "I remember that..." would replay
    the conversation into itself, and documents ride along as chips instead.
    """
    return tuple(
        r
        for r in recalled
        if r.kind not in (MemoryKind.DOCUMENT, MemoryKind.CONVERSATION)
    )


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
            {"reply": provider_error(error), "speak": True, "provenance": None, "trace": []},
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


Command = Callable[[Jarvis, Reply], Reply]

# The commands this module serves, composed by the command-center router.
COMMANDS: dict[str, Command] = {
    "say": _say,
}
