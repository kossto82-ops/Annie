"""SpeechPerceptionSource: the ear's seam between spoken input and Jarvis.

The mouth (``ResponseRenderer`` / voice) turns Jarvis's reply into speech; this is
its mirror on the input side -- the ear that turns a *spoken* utterance into text
Jarvis can treat as an observation (Vision §3, §32, §38). Where the browser already
does speech-to-text (the Web Speech API), a provider can be an identity pass-through
(``EchoSpeechPerception``) that simply returns the already-transcribed text; a richer
provider could transcribe raw audio behind the same seam.

Like every capability, this is a *producer*, not a decision-maker: it only delivers
text into the core. It never decides what Jarvis believes (D6, Vision §38), and a
source that cannot hear stays silent rather than inventing (Vision §37).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SpeechPerceptionSource(Protocol):
    """Translates a spoken utterance into transcribed text for Jarvis.

    ``utterance`` is whatever the surface offers: already-transcribed text (browser
    STT) or a reference to raw audio for a richer transcriber. The returned text is
    an *observation* Jarvis then perceives through the ordinary ``PerceptionSource``
    -- never a belief on its own.
    """

    def transcribe(self, utterance: str) -> str:
        """Return the transcribed text of ``utterance`` -- '' when it cannot hear."""
        ...
