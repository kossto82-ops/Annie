"""capability_scout: proposes candidate capabilities for a recognised need.

This is the *discovery* stage of Odysseus (capability acquisition): given a
:class:`CapabilityNeed`, it surfaces candidate :class:`Capability` proposals that
could satisfy it, drawn from a deterministic catalog of what Jarvis could
acquire. The scout is an evidence *producer*, not a decision-maker (Vision §32,
§38): it only pairs a need with plausible capabilities; whether any is worth
pursuing is a separate, later evaluation step.

Like the keyword perceiver, matching here is deliberately shallow -- it scans a
need's statement/rationale for keyword cues that line up with known capability
templates. Semantic matching could replace it behind the same seam (D11), but
exact/keyword matching is the correct first step for a small feature: an empty
result is an honest "no candidate yet", never a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.value_objects.capability import Capability
from jarvis.domain.value_objects.capability_need import CapabilityNeed

_WORD = re.compile(r"\w+")


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


@dataclass(frozen=True, slots=True, kw_only=True)
class _Template:
    """A known kind of capability and the cues that suggest it."""

    name: str
    description: str
    requirement: str
    cues: frozenset[str]


_TEMPLATES: tuple[_Template, ...] = (
    _Template(
        name="search the web",
        description="retrieve timely outside information by searching the Internet",
        requirement="an Internet source (e.g. the agent-reach provider)",
        cues=frozenset({"web", "internet", "search", "online", "noticias", "noticia"}),
    ),
    _Template(
        name="read external documents",
        description="fetch and read documents from external URLs",
        requirement="an Internet source and a URL",
        cues=frozenset({"read", "document", "url", "article", "link", "enlace"}),
    ),
    _Template(
        name="recall by meaning",
        description="retrieve long-term memory by meaning rather than exact words",
        requirement="a local embedding model",
        cues=frozenset({"embedding", "semantic", "recall", "recuerdo", "significado"}),
    ),
    _Template(
        name="deep research",
        description="investigate a question in depth through a search instance",
        requirement="a SearXNG (or compatible) instance",
        cues=frozenset({"research", "investig", "profund", "indepth", "in depth"}),
    ),
    _Template(
        name="compare language models",
        description="ask several language models one question and gather their replies blind",
        requirement="models configured in the language-model registry",
        cues=frozenset({"compare", "compar", "benchmark", "several models", "modelos"}),
    ),
    _Template(
        name="reason with a language model",
        description="propose provisional answers when belief and memory cannot",
        requirement="a language-model provider",
        cues=frozenset({"llm", "reason", "razo", "provisional", "modelo"}),
    ),
    _Template(
        name="perceive speech",
        description="hear the companion's spoken words",
        requirement="a speech-to-text provider",
        cues=frozenset({"speech", "voice", "hear", "habla", "voz", "audio"}),
    ),
    _Template(
        name="send and read email",
        description="read, triage and send email through a mailbox",
        requirement="a configured IMAP/SMTP mailbox",
        cues=frozenset({"email", "mail", "inbox", "correo", "mensaje", "message"}),
    ),
    _Template(
        name="manage notes",
        description="keep notes, todos and reminders",
        requirement="the local notes store",
        cues=frozenset({"note", "notes", "todo", "reminder", "nota", "apunte", "tarea"}),
    ),
    _Template(
        name="manage calendar",
        description="see and schedule calendar events",
        requirement="a CalDAV (or local) calendar",
        cues=frozenset({"calendar", "agenda", "event", "schedule", "calendario", "evento", "cita"}),
    ),
    _Template(
        name="manage tasks",
        description="create and run scheduled recurring tasks",
        requirement="the local task scheduler",
        cues=frozenset(
            {"task", "cron", "scheduled", "recurring", "every", "automatically", "programa"}
        ),
    ),
    _Template(
        name="delegate to an agent",
        description="hand a concrete task to an edge agent that executes it with its tools",
        requirement="an edge agent (a tool-backed executor, e.g. Odysseus agent mode)",
        cues=frozenset(
            {"agent", "delegate", "do it", "execute", "run it", "agente", "delegar", "hazlo"}
        ),
    ),
)


def catalog() -> tuple[Capability, ...]:
    """The known catalog of what Jarvis could grow to do (Odysseus, Vision §34).

    Deterministic and ordered: every capability in the toolkit, with its purpose
    and requirement, even when none has been proposed or acquired yet. A surface
    uses this to show the full landscape -- not just what is held -- and pair real
    state (proposed/acquired) with what remains available to grow.
    """
    return tuple(
        Capability(
            name=t.name,
            description=t.description,
            requirement=t.requirement,
            provenance="the built-in capability catalog",
            status=CapabilityStatus.PROPOSED,  # catalog entries are candidates, not held
        )
        for t in _TEMPLATES
    )


def scout(need: CapabilityNeed) -> tuple[Capability, ...]:
    """Return candidate capabilities for ``need``, ordered by cue match.

    A need that matches no template yields an empty tuple -- an honest "no
    candidate yet", not a fabricated one.
    """
    cues = _words(need.statement) | _words(need.rationale)
    if need.success_criterion is not None:
        cues |= _words(need.success_criterion)

    matched: list[tuple[int, Capability]] = []
    for template in _TEMPLATES:
        hits = len(cues & template.cues)
        if hits == 0:
            continue
        matched.append(
            (
                -hits,
                Capability(
                    name=template.name,
                    description=template.description,
                    requirement=template.requirement,
                    provenance=(
                        f"met the capability need: {need.statement} "
                        f"({hits} matching cue(s))"
                    ),
                    status=CapabilityStatus.PROPOSED,
                ),
            )
        )
    matched.sort(key=lambda pair: pair[0])
    return tuple(capability for _, capability in matched)
