"""Turning fetched documents into provenance-bearing claim evidence (external-evidence gate).

The external-evidence gate's contract: retrieved material enters Jarvis as
*epistemically qualified information*, never as truth. This module is the small
adapter that rides the existing perception seam (:class:`PerceptionSource`,
Vision §32, §38) -- the exact machinery used for any other raw text -- instead
of inventing an ``ExternalClaimExtractor``.

A document is a container of claims, opinions, instructions, ads, noise and
malice; the perceiver decides which of its claims, if any, are candidate
evidence. Each extracted claim is stamped with the document's structured origin
(:class:`EvidenceProvenance`) so "Source A claims X" stays recoverably distinct
from "Jarvis independently observed X" after the claim enters a belief.

This module *only produces candidate evidence*: it never writes to a belief,
memory, topic, or attention surface. Running the claims through the sanctioned
episode (``think``) is the caller's deliberate epistemic act.
"""

from __future__ import annotations

from collections.abc import Iterable

from jarvis.domain.perception.perception_source import PerceptionSource
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.evidence_provenance import EvidenceProvenance
from jarvis.domain.value_objects.retrieved_document import RetrievedDocument


def claims_from_document(
    document: RetrievedDocument, perceiver: PerceptionSource
) -> tuple[Evidence, ...]:
    """Perceive one document's content into claim evidence, provenance kept.

    The perceiver decides what the document *says*; this bridge only attaches
    where it came from and when it was retrieved. A perceiver that finds nothing
    yields no evidence (honest silence, Vision §37) -- never a fabricated claim.
    """
    provenance = EvidenceProvenance.from_document(document)
    claims: list[Evidence] = []
    for piece in perceiver.perceive(document.content):
        claims.append(
            Evidence(
                content=piece.content,
                source=piece.source,
                weight=piece.weight,
                supports=piece.supports,
                is_neutral=piece.is_neutral,
                context=piece.context,
                provenance=provenance,
            )
        )
    return tuple(claims)


def claims_from_documents(
    documents: Iterable[RetrievedDocument], perceiver: PerceptionSource
) -> tuple[Evidence, ...]:
    """Perceive many documents into one flat, provenance-bearing claim list."""
    claims: list[Evidence] = []
    for document in documents:
        claims.extend(claims_from_document(document, perceiver))
    return tuple(claims)