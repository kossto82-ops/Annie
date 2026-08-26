"""The command center: a local control surface for talking to Jarvis (Vision §30, §40).

A developer's standing requirement is a place to *speak with* Jarvis and *tune* it
at runtime. The core stays dependency-free, so the rich surface lives where it is
free: a browser. A stdlib HTTP server serves one self-contained page and a small
JSON bridge into the Jarvis core; the browser supplies voice output
(``speechSynthesis``), voice input (``SpeechRecognition``) and the animated
point-cloud face — none of which cost the core a single dependency.

Everything that decides *what Jarvis says or does* is a pure function here
(:func:`~jarvis.interface.command_center.handle`, :func:`~jarvis.interface.command_center.route`),
unit-tested with no socket and no network. The socket in :mod:`jarvis.interface.server`
is a thin wrapper that only moves bytes.
"""
