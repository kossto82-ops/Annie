"""One live loopback round-trip through the real HTTP server (Vision §30).

Opt-in, mirroring the live-LLM test: binding a socket is skipped by default so CI and
sandboxed runs stay hermetic and green. Set JARVIS_UI_SMOKE=1 to actually bind an
ephemeral port on 127.0.0.1 and confirm the page and JSON bridge answer. The routing
logic itself is covered socket-free in test_command_center.py.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.request

import pytest

from jarvis import Jarvis
from jarvis.interface.server import create_server

_SMOKE = os.environ.get("JARVIS_UI_SMOKE") == "1"
_skip = pytest.mark.skipif(not _SMOKE, reason="set JARVIS_UI_SMOKE=1 to bind a socket")


@_skip
def test_the_server_serves_page_and_state() -> None:
    server = create_server(Jarvis(), host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as page:
            assert page.status == 200
            assert b"command center" in page.read().lower()
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/say",
            data=b'{"text": "hello"}',
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as reply:
            body = json.loads(reply.read())
        assert "reply" in body
        assert "state" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
