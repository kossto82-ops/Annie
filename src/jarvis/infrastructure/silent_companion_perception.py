"""The default companion perceiver: it reads nothing (Vision §37, §38).

Learning about the companion from free conversation needs a language model to read an
utterance into traits (see `LlmCompanionPerception`). The offline default therefore
stays silent rather than fabricating traits from a dumb rule — honest silence, and the
relational channel simply does nothing until a real perceiver is configured.
"""

from __future__ import annotations

from jarvis.domain.perception.companion_perception import CompanionObservation


class SilentCompanionPerception:
    """A companion perceiver that never infers anything (the offline default)."""

    def read_companion(self, utterance: str) -> tuple[CompanionObservation, ...]:
        return ()
