"""Who a stored document belongs to -- its attribution (Vision §26 provenance).

Documents are kept bytes with a name chosen by whoever gave them. Ownership is
the provenance of *attribution*: whose artifact the file is, so Jarvis can answer
"whose is this, and where did it come from?" honestly. It is never a claim about
the content -- a companion-shared runbook is just as factual or mistaken as one
Jarvis materialised. It says whose hands it came from.
"""

from __future__ import annotations

from enum import Enum


class DocumentOwner(Enum):
    """The origin a stored document is attributed to."""

    COMPANION = "companion"  # the companion gave Jarvis this file to keep
    JARVIS = "jarvis"  # Jarvis materialised it (a generated artifact/report)