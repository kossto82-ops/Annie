"""Launch the command center: ``python -m jarvis.interface`` (Vision §30, §40).

Reads a little configuration from the environment so nothing is hard-coded:

    JARVIS_UI_HOST   bind address           (default 127.0.0.1)
    JARVIS_UI_PORT   port                    (default 8765)
    JARVIS_HOME      persistent memory dir   (default ./.jarvis; set empty for in-memory)
    JARVIS_LLM_*     the perceiver's model   (see jarvis.infrastructure.env_settings)

Then open the printed URL in a browser to talk to Jarvis — by text or by voice.
"""

from __future__ import annotations

import os

from jarvis.interface.server import run


def main() -> None:
    host = os.environ.get("JARVIS_UI_HOST", "127.0.0.1")
    port = int(os.environ.get("JARVIS_UI_PORT", "8765"))
    home_value = os.environ.get("JARVIS_HOME", "./.jarvis")
    home = home_value or None  # an explicitly empty JARVIS_HOME means in-memory
    run(host=host, port=port, home=home)


if __name__ == "__main__":
    main()
