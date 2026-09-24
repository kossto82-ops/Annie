"""SpeechPerceptionSource: the ear's seam between spoken input and Jarvis.

The mouth (``ResponseRenderer`` / voice) turns Jarvis's reply into speech; this is
its mirror on the input side -- the ear that turns a *spoken* utterance into text
Jarvis can treat as an observation (Vision §3, §32, §38). Where the browser already
does speech-to-text (the Web Speech API), a provider can be an identity pass-through
(``EchoSpeechPerception``) that simply returns the already-transcribed text; a richer
provider can transcribe raw audio via :meth:`transcribe_audio` behind the same seam
(e.g. a Whisper backer at the command center), and -- when it reports
``can_stream_partials`` -- supply *partial* transcripts as a live utterance grows via
:meth:`stream_transcribe` (roadmap F5: live voice streaming + VAD).

Like every capability, this is a *producer*, not a decision-maker: it only delivers
text into the core. It never decides what Jarvis believes (D6, Vision §38), and a
source that cannot hear stays silent rather than inventing (Vision §37).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class SpeechPerceptionSource(Protocol):
    """Translates a spoken utterance into transcribed text for Jarvis.

    ``utterance`` is whatever the surface offers: already-transcribed text (browser
    STT) or a reference to raw audio for a richer transcriber. The returned text is
    an *observation* Jarvis then perceives through the ordinary ``PerceptionSource``
    -- never a belief on its own.

    The metadata attributes let a surface report -- honestly -- which ear is wired
    and how it hears: ``provider`` names it, ``model`` the engine it transcribes
    with ('' when there is none), and ``can_hear_audio`` says whether raw audio
    produces real text here (a Whisper backer can; the browser's echo pass-through
    cannot). ``can_stream_partials`` is the feature-detect for live streaming: when
    True, :meth:`stream_transcribe` yields increasing partial transcripts as the
    audio chunks arrive, so a console can render words while the user still speaks.
    They are self-description, never a promise.
    """

    provider: str
    model: str
    can_hear_audio: bool
    can_stream_partials: bool

    def transcribe(self, utterance: str) -> str:
        """Return the transcribed text of ``utterance`` -- '' when it cannot hear."""
        ...

    def transcribe_audio(self, audio: bytes) -> str:
        """Transcribe raw audio bytes -- '' when this ear cannot hear raw audio."""
        ...

    def stream_transcribe(self, chunks: Iterable[bytes]) -> Iterator[str]:
        """Yield partial transcripts as ``chunks`` arrive -- nothing when it cannot stream.

        Consumed eagerly by the caller (a console live-preview tick): each yielded
        string is the best transcript of *everything received so far*, so a
        ``stream_transcribe([first, later])`` grows ``"hola"`` -> ``"hola, mundo"``
        and never repeats. An ear that reports ``can_stream_partials = False`` yields
        nothing -- for it a console falls back to silence segmentation instead (F5).
        """
        ...
