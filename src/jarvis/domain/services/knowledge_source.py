"""KnowledgeSource: the deliberate-consult seam (Vision §37, §38; D6).

Recall answers from what Jarvis already knows; reasoning proposes a provisional
answer when neither belief nor memory can help. Neither can *find out*. This is
the seam for that: when an episode has no grounded belief, no strong memory, and
Jarvis deliberately decides it should go look, a ``KnowledgeSource`` gathers
candidate evidence about the trigger and hands it to the core as one piece of
evidence to weigh -- never as a verdict.

The seam mirrors ``Reasoner`` and ``MemoryRetriever`` (D7): it is a domain
Protocol; the edges that actually gather -- deep research, blind model
comparison -- live in infrastructure and wrap their sources behind it. A bare
Jarvis wires none of it, so the offline core is unchanged (D8); wiring one only
lets an episode *choose* to consult, it never forces a consultation.

An honest ``KnowledgeSource`` never fabricates: it returns an Evidence it
actually gathered, or ``None`` when it has nothing to offer (an empty query
result, a model that returned nothing, an edge failure). ``None`` is not a
conclusion -- the episode continues exactly as if no consult had happened.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jarvis.domain.value_objects.evidence import Evidence


@runtime_checkable
class KnowledgeSource(Protocol):
    """Deliberately gathers candidate evidence about a question, on request.

    The core calls :meth:`gather` only when it cannot conclude from what it
    knows, and only once per episode. What comes back is *candidate* evidence;
    the core still derives the belief's confidence from it (D6).
    """

    kind: str

    def gather(self, question: str) -> Evidence | None:
        """Return one piece of candidate evidence about ``question``, or None.

        ``None`` means "nothing gathered": the consult changes nothing and the
        episode continues exactly as before. A real failure of the edge is
        reported the same way -- an empty consult is an honest empty consult,
        never a fabricated claim (D6, D8).
        """
        ...