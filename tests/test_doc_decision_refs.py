"""Doc-truth gate for the JARVIS repository (roadmap F1, Increment 172).

``docs/claude/DECISIONS.md`` is the single decision authority. These tests run the
offline integrity checker (``scripts/check_decision_refs.py``) against the live
repository and its embedded self-tests, keeping the invariant enforced on CI and
on any developer machine.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_decision_refs.py"


def _run_checker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def test_decision_references_resolve_live() -> None:
    """Every D-token in live docs and src must resolve in DECISIONS.md."""
    result = _run_checker()
    assert result.returncode == 0, result.stdout + result.stderr


def test_decision_checker_selftest_passes() -> None:
    """The checker's embedded fixtures (clean, dangling ref, numbering gap)."""
    result = _run_checker("--selftest")
    assert result.returncode == 0, result.stdout + result.stderr