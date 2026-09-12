"""Shared helpers used across multiple command-center domain modules."""

from __future__ import annotations

from jarvis.domain.entities.belief import Belief
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.executive.executive_controller import subject_of
from jarvis.jarvis import Jarvis

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

_OFFLINE_PERCEIVERS = frozenset({"", "keyword", "scripted", "stub"})


def _evidence_json(evidence: Evidence) -> dict[str, object]:
    """One piece of evidence as the panel renders it — content, provenance, weight."""
    return {
        "content": evidence.content,
        "source": evidence.source.name,
        "weight": evidence.weight.value,
    }


def _provenance(belief: Belief) -> dict[str, object]:
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


def _capability_not_ready(jarvis: Jarvis, capability: str) -> dict[str, object]:
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


def _ready_marker(jarvis: Jarvis, capability: str) -> str:
    """A concise "(ready)" taste when an acquired capability is live-backed."""
    return " (ready)" if jarvis.can_do(capability) else ""


def _recall_block(jarvis: Jarvis) -> dict[str, object]:
    """How recall works right now: by meaning or by surface tokens (F9).

    ``meaning`` is live only when the embedding edge is wired and earned
    (``can_do``); otherwise recall stays lexical. No scores here -- candidates
    surface through the ``recall`` command.
    """
    mode = "meaning" if jarvis.can_do("recall by meaning") else "lexical"
    return {"mode": mode}


def _companion_name(jarvis: Jarvis) -> str | None:
    """The companion's name if Jarvis has learned it, for a warmer greeting (best effort)."""
    for belief in jarvis.companion.beliefs():
        statement = belief.explain().statement.lower()
        for cue in ("name is ", "llama ", "nombre es ", "soy "):
            if cue in statement:
                name = belief.explain().statement.split()[-1].strip(".,!?")
                return name if name.isalpha() else None
    return None
