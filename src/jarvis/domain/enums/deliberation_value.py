"""How much a deliberation is worth (Vision §15, §14).

Not every problem is worth the same reasoning. Vision §15 lists what energy should
let Jarvis reason about: complexity, cost, urgency, expected value, available
resources -- and that "a simple problem should not trigger an unnecessarily
expensive reasoning process" while "a high-value ambiguous problem may justify
deeper reasoning". ``DeliberationValue`` is Jarvis's knob for that worth: a call
to :meth:`~jarvis.jarvis.Jarvis.think` or
:meth:`~jarvis.jarvis.Jarvis.deliberate` can say how much the question is worth,
and the attention router uses it to charge (spend) attention accordingly.

Like every decision, this only *routes depth*; it never decides what Jarvis
believes (D6). A high-value problem gets the full lifecycle; a cheap one is
answered briefly rather than running the whole integration.
"""

from __future__ import annotations

from enum import Enum


class DeliberationValue(Enum):
    """The worth of a deliberation, guiding how much attention it is charged."""

    CHEAP = "cheap"  # a low-value / simple problem -- answer briefly when nothing new
    NORMAL = "normal"  # the default -- already-known triggers are brief, else full
    HIGH = "high"  # a high-value / ambiguous problem -- warrant the full lifecycle
