"""What a companion's message *is*, before Jarvis decides what to do with it.

The core conversational fix (Vision §5, §37): not every message is knowledge.
Conversation drives memory, not memory drives conversation. Before perceiving a
message into evidence or traits, Jarvis first understands its *intent* and only the
intents that genuinely carry knowledge (an explicit "remember this", or a real
statement/question to reason about) are allowed to touch memory or beliefs. A
greeting, small talk, feedback about Jarvis, or an instruction are conversation —
they are answered as conversation and never silently turned into beliefs.

Classification is deterministic and offline (no model), bilingual (Spanish/English),
and intentionally conservative: when nothing marks a message as conversational, it
falls through to STATEMENT and the normal reasoning path is unchanged.
"""

from __future__ import annotations

import re
from enum import Enum

_WORD = re.compile(r"\w+", re.UNICODE)


class ConversationIntent(Enum):
    """The kind of turn a companion's message is."""

    GREETING = "greeting"  # "hola", "hi" -- open the conversation
    SMALLTALK = "smalltalk"  # "¿qué tal?", "how are you?" -- casual, no knowledge
    FEEDBACK = "feedback"  # about Jarvis itself ("no funcionas bien") -- not a belief
    INSTRUCTION = "instruction"  # "busca X", "habla con la IA" -- an action to interpret
    REMEMBER = "remember"  # "recuerda que ..." -- the one intent that IS memory
    STATEMENT = "statement"  # default: a claim/question to reason about (the knowledge path)


# Multi-word cues are matched as substrings of the lowered text; single words as tokens.
_REMEMBER_CUES = (
    "recuerda que",
    "recuérdate",
    "acuérdate",
    "acuerdate",
    "anota que",
    "apunta que",
    "no olvides",
    "ten en cuenta",
    "remember that",
    "note that",
    "keep in mind",
    "don't forget",
    "dont forget",
)
_INSTRUCTION_CUES = (
    "habla con",
    "consulta",
    "pregunta a",
    "pregúntale",
    "preguntale",
    "busca",
    "búscame",
    "comprueba",
    "verifica",
    "revisa",
    "averigua",
    "search",
    "look up",
    "look it up",
    "check with",
    "ask the",
    "find out",
    "google",
)
_GREETING_TOKENS = frozenset(
    {"hola", "holi", "holis", "buenas", "hey", "hi", "hello", "ey", "saludos"}
)
_GREETING_PHRASES = ("buenos días", "buenas tardes", "buenas noches", "good morning")
_SMALLTALK_CUES = (
    "qué tal",
    "que tal",
    "cómo estás",
    "como estas",
    "cómo va",
    "como va",
    "qué pasa",
    "que pasa",
    "qué cuentas",
    "how are you",
    "how's it going",
    "hows it going",
    "what's up",
    "whats up",
    "how are things",
)
# Feedback is *about Jarvis*: a second-person marker AND a complaint/should marker.
_SECOND_PERSON = frozenset(
    {
        "funcionas", "sirves", "sabes", "eres", "haces", "trabajas", "respondes",
        "entiendes", "deberías", "deberias", "you", "youre",
    }
)
_COMPLAINT = frozenset(
    {
        "no", "mal", "peor", "fatal", "desastre", "inútil", "inutil", "terrible",
        "broken", "bad", "wrong", "useless", "worse", "nada",
    }
)


def _has_phrase(text: str, cues: tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)


def classify(text: str) -> ConversationIntent:
    """Read a companion's message as one conversational intent (first match wins)."""
    lowered = text.strip().lower()
    tokens = set(_WORD.findall(lowered))

    if _has_phrase(lowered, _REMEMBER_CUES):
        return ConversationIntent.REMEMBER
    if _has_phrase(lowered, _INSTRUCTION_CUES):
        return ConversationIntent.INSTRUCTION
    if _is_feedback(lowered, tokens):
        return ConversationIntent.FEEDBACK
    if tokens & _GREETING_TOKENS or _has_phrase(lowered, _GREETING_PHRASES):
        return ConversationIntent.GREETING
    if _has_phrase(lowered, _SMALLTALK_CUES):
        return ConversationIntent.SMALLTALK
    return ConversationIntent.STATEMENT


def remembered_content(text: str) -> str:
    """The thing to remember, with the leading "remember that ..." cue stripped.

    "Recuerda que prefiero la noche" -> "prefiero la noche". When no cue is cleanly
    strippable, the whole message is returned (still an honest record of what was said).
    """
    lowered = text.strip().lower()
    for cue in _REMEMBER_CUES:
        index = lowered.find(cue)
        if index != -1:
            remainder = text.strip()[index + len(cue) :].strip(" :,-.!?¿¡")
            if remainder:
                return remainder
    return text.strip()


def _is_feedback(lowered: str, tokens: set[str]) -> bool:
    """True when the message complains about Jarvis rather than stating knowledge."""
    if "frustrad" in lowered:  # "estoy frustrado contigo"
        return True
    if not tokens & _SECOND_PERSON:
        return False
    # "deberías ..." is itself a complaint about Jarvis; otherwise a negativity marker.
    return bool(tokens & _COMPLAINT) or "deberías" in tokens or "deberias" in tokens
