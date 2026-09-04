"""EchoSpeechPerception: the default ear — pass spoken text straight through.

The command center's browser already does speech-to-text with the Web Speech API and
sends the transcript over the socket. So Jarvis's default ear is an identity
pass-through: the utterance *is* already transcribed text, and ``transcribe`` simply
returns it unchanged. This keeps the ``SpeechPerceptionSource`` seam live (the
"perceive speech" capability reads as earned) without duplicating STT in Python. A
richer transcriber that turns raw audio into text can replace it behind the same
Protocol (D7, D8): network stays at the edge; the core never depends on it.
"""

from __future__ import annotations


class EchoSpeechPerception:
    """Returns the already-transcribed utterance unchanged (browser STT path)."""

    def transcribe(self, utterance: str) -> str:
        """The utterance is already text (the browser transcribed it)."""
        return utterance
