"""Events about actions and their outcomes (Vision §27, §23)."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.events.domain_event import CognitiveEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class ActionOutcomeRecorded(CognitiveEvent):
    """An action's actual outcome was recorded and compared to what was expected."""

    action_id: str
    description: str
    met_expectation: bool
