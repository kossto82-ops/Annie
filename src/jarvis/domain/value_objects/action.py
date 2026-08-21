"""Action: an intended act, distinct from thinking (Vision §27).

Jarvis must distinguish *thinking* from *acting*. An Action is a declared
intention with an expected outcome, a predicted confidence, and a reversibility
flag (relevant later for earned autonomy, Vision §28). It carries no side effect
itself -- performing anything in the world is out of scope here. After it
happens, comparing the expected outcome with the actual one becomes learning
evidence (Vision §20).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from jarvis.domain.value_objects.confidence import Confidence


@dataclass(frozen=True, slots=True, kw_only=True)
class Action:
    """A declared intention to act, with its expected outcome."""

    description: str
    expected: str
    confidence: Confidence  # how confident Jarvis is the expected outcome will occur
    reversible: bool
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not self.description or not self.description.strip():
            raise ValueError("An action requires a non-empty description")
        if not self.expected or not self.expected.strip():
            raise ValueError("An action requires an expected outcome")
