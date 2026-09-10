"""EchoSpeechPerception: the default ear — pass spoken text straight through.

The command center's browser already does speech-to-text with the Web Speech API and
sends the transcript over the socket. So Jarvis's default ear is an identity
pass-through: the utterance *is* already transcribed text, and ``transcribe`` simply
returns it unchanged. Raw audio is out of its reach (it returns '') -- a live
transcriber that turns audio into text can replace it behind the same Protocol
(D7, D8): network stays at the edge; the core never depends on it.
"""

from __future__ import annotations


class EchoSpeechPerception:
    """Returns the already-transcribed utterance unchanged (browser STT path)."""

    provider = "echo"
    model = ""
    can_hear_audio = False

    def transcribe(self, utterance: str) -> str:
        """The utterance is already text (the browser transcribed it)."""
        return utterance

    def transcribe_audio(self, audio: bytes) -> str:
        """This ear cannot hear raw audio -- it stays silent rather than guessing."""
        return ""
