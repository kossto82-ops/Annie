"""Open the Jarvis command center in your browser (Vision §30, §40).

    python examples/command_center.py

A local, dependency-free control surface: type or speak to Jarvis, watch the
point-cloud face react while it talks, see its beliefs, goals and energy update
live, and tune how hard it thinks. Equivalent to ``python -m jarvis.interface``.

Set JARVIS_LLM_* first if you want a real language model behind perception
(otherwise the keyword perceiver is used); set JARVIS_HOME to keep memory on disk.
"""

from __future__ import annotations

from jarvis.interface.server import run

if __name__ == "__main__":
    run()
