"""What shape of cognition an episode was (Vision §12, §17).

An episode can reach a single grounded conclusion (a working belief) or weigh
competing explanations (a deliberation). Both are real acts of cognition worth
remembering, but they measure differently -- self-observation over confidence and
stability only makes sense for CONCLUSION episodes -- so the record names which.
"""

from __future__ import annotations

from enum import Enum


class EpisodeKind(Enum):
    """The kind of conclusion an episode produced."""

    CONCLUSION = "conclusion"  # a single working belief (think)
    DELIBERATION = "deliberation"  # competing hypotheses (consider)
