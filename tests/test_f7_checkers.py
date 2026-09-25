"""Doc-truth gates for the JARVIS repository (roadmap F7, Increment 181).

The two Increment-181 checkers — the doc-truth gate (counts, decision refs,
SYSTEM_TODAY symbols, HISTORICAL manifest) and the broad-``except`` audit —
are offline obstacles to docs drifting from the tree and to `except Exception`
silently swallowing again. These tests run both against the live repository and
their embedded self-tests, keeping the F1 wrappers' pattern.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC_TRUTH = ROOT / "scripts" / "check_docs_truth.py"
BROAD_EXCEPTS = ROOT / "scripts" / "check_broad_excepts.py"


def _run_checker(checker: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(checker), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def test_doc_truth_check_passes_live() -> None:
    result = _run_checker(DOC_TRUTH)
    assert result.returncode == 0, result.stdout + result.stderr


def test_doc_truth_checker_selftest_passes() -> None:
    result = _run_checker(DOC_TRUTH, "--selftest")
    assert result.returncode == 0, result.stdout + result.stderr


def test_broad_except_audit_passes_live() -> None:
    result = _run_checker(BROAD_EXCEPTS)
    assert result.returncode == 0, result.stdout + result.stderr


def test_broad_except_checker_selftest_passes() -> None:
    result = _run_checker(BROAD_EXCEPTS, "--selftest")
    assert result.returncode == 0, result.stdout + result.stderr