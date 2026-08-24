"""Guard: every runnable example still runs end-to-end without error.

Examples are documentation that executes; if the public surface drifts, an example
breaks here rather than rotting silently. Each is run as ``__main__`` (which calls
its ``main()``), with stdout captured so the suite stays quiet.
"""

from __future__ import annotations

import contextlib
import io
import runpy
from pathlib import Path

import pytest

_EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
_EXAMPLES = (
    "main_loop",
    "goal_arc",
    "goal_parts",
    "perceiving",
    "conversation",
    "resolving",
)


@pytest.mark.parametrize("name", _EXAMPLES)
def test_example_runs_without_error(name: str) -> None:
    path = _EXAMPLES_DIR / f"{name}.py"
    assert path.exists(), f"missing example: {path}"
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(str(path), run_name="__main__")
