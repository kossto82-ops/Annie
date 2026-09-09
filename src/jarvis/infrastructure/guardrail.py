"""Honest-silence guardrail on live provider replies (Vision §37).

Jarvis is truthful because it never imports a fabricated answer: a provider error, a
validation failure, or an unreadable reply yields `""`. A *refusal* is another such
case in disguise -- the model declining to answer (a safety filter, a "I can't help
with that", a local SLM reacting to out-of-distribution input) is not evidence, and it
must not cross the seam wearing the costume of a real reply. The guardrail turns a
recognised refusal into honest silence before the text enters perception, reasoning,
recall, or voice.

Two signals are recognised, both deterministic and offline-testable:

* **`finish_reason='content_filter'`** -- the structured signal OpenAI-compatible
  providers send when their safety layer stopped the reply.
* **Refusal text** -- phrasings that mark a decline (English and Spanish, since the
  living language here is Spanish). Matched conservatively against whole phrases, so an
  ordinary answer that merely *mentions* a word like "can't" is never silenced.

The guardrail is a pure predicate over the reply: it imports nothing, talks to no one,
and always returns an honest string (`""` or the reply untouched). Providers get the
same behaviour through `guard_reply`: `""` where the model declined, the text otherwise.
"""

from __future__ import annotations

_REFUSAL_PHRASES: tuple[str, ...] = (
    # English
    "i can't help with that",
    "i cannot help with that",
    "i'm sorry, but i can't",
    "i'm sorry, i can't",
    "i am sorry, but i cannot",
    "i am unable to help",
    "i won't be able to help",
    "i won't help",
    "i can't assist",
    "i cannot assist",
    "i'm not capable of helping",
    "as an ai language model, i cannot",
    "as an ai, i cannot",
    "i don't feel comfortable",
    "i'm not comfortable",
    "i can't answer that",
    "i cannot answer that",
    "i must decline",
    "i decline to",
    "the content has been filtered",
    "content filter was triggered",
    # Spanish
    "no puedo ayudarte",
    "no puedo ayudarle",
    "no puedo hacer eso",
    "lo siento, pero no puedo",
    "no estoy aquí para ayudarte",
    "no estoy en condiciones de",
    "no tengo la capacidad de",
    "no me siento cómodo",
    "no puedo asistirte",
    "no puedo responder",
    "fui diseñado para no",
)


def is_refusal(text: str) -> bool:
    """True when the reply is a provider decline rather than a real answer."""
    if not text:
        return False
    collapsed = " ".join(text.lower().split())
    return any(phrase in collapsed for phrase in _REFUSAL_PHRASES)


def content_filtered(finish_reason: str | None) -> bool:
    """True when the provider's safety layer stopped the reply."""
    return finish_reason == "content_filter"


def guard_reply(reply: str, finish_reason: str | None = None) -> str:
    """The reply may cross the seam: `""` where the provider declined, text otherwise."""
    if content_filtered(finish_reason) or is_refusal(reply):
        return ""
    return reply