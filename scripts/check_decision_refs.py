"""Decision-reference integrity checker (roadmap F1, Increment 172).

``docs/claude/DECISIONS.md`` is the single authority for architectural decisions.
This script scans the live docs and the ``src/`` tree and fails on any ``D<number>``
token that does not resolve to a decision *defined* in ``DECISIONS.md``.

Whitelisted by design (history, not live guidance):

- ``STATUS.md`` (the whole file is the historical log; its own adr-lite D1-D40
  numbering is mapped to the authority in the appendix there);
- ``docs/claude/audits/*`` (dated audit reports);
- dated gate / forensic / closure records (``*GATE*``, ``*FORENSIC_CLOSURE*``,
  ``*CLOSURE*``);
- the HISTORICAL marker files listed in ``docs/claude/INDEX.md``.

Also enforces that the authority's decision numbers are contiguous (1..max), so a
future decision cannot be numbered leaving a dead reference behind.

Usage::

    python scripts/check_decision_refs.py            # check the repository
    python scripts/check_decision_refs.py --selftest # embedded fixture checks

Exit code is 0 when clean, 1 otherwise. Stdlib only; offline by design (D8).
"""

from __future__ import annotations

import pathlib
import re
import sys
import tempfile

AUTHORITY = pathlib.Path("docs/claude/DECISIONS.md")

HISTORICAL_DOCS = frozenset(
    {
        pathlib.Path("docs/claude/INTEGRACION_ODYSSEUS.md"),
        pathlib.Path("docs/claude/INTERNET_AGENT_REACH.md"),
        pathlib.Path("docs/claude/MEMORY_AND_REASONING_ANALYSIS.md"),
        pathlib.Path("docs/claude/SEMANTIC_ATTENTION_AUDIT.md"),
        pathlib.Path("docs/claude/SEMANTIC_COGNITION_IMPLEMENTATION.md"),
        pathlib.Path("docs/claude/REMEDIATION_PLAN.md"),
        pathlib.Path("docs/claude/REMEDIATION_REPORT.md"),
        pathlib.Path("docs/claude/ROADMAP_ARCHITECTURAL_AUDIT.md"),
        pathlib.Path("docs/claude/IMPLEMENTATION_PLAN.md"),
        pathlib.Path("docs/claude/PLAN_COMMAND_CENTER.md"),
    }
)

LIVE_ROOT_DOCS = (
    pathlib.Path("CLAUDE.md"),
    pathlib.Path("README.md"),
    pathlib.Path("DevRunbook.md"),
)

_TOKEN = re.compile(r"\bD(\d{1,2})\b")
_HEADER = re.compile(r"^## D(\d{1,2})\s+[-–—]\s+", re.MULTILINE)


def authorized_numbers(text: str) -> frozenset[int]:
    """Every decision number defined as a ``## D<number>`` header."""
    return frozenset(int(m) for m in _HEADER.findall(text))


def is_whitelisted(rel: pathlib.Path) -> bool:
    name = rel.name
    if rel == pathlib.Path("STATUS.md"):
        return True
    if rel in HISTORICAL_DOCS:
        return True
    if "audits" in rel.parts:
        return True
    return (
        "GATE" in name
        or "FORENSIC_CLOSURE" in name
        or ("CLOSURE" in name and "FORENSIC" not in name)
    )


def live_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Deterministic list of live markdown + python sources to scan."""
    out: list[pathlib.Path] = []
    for rel in LIVE_ROOT_DOCS:
        if (root / rel).exists():
            out.append(rel)
    docs = root / "docs"
    if docs.is_dir():
        for path in sorted(docs.rglob("*.md")):
            rel = path.relative_to(root)
            if not is_whitelisted(rel):
                out.append(rel)
    src = root / "src"
    if src.is_dir():
        for path in sorted(src.rglob("*.py")):
            out.append(path.relative_to(root))
    return out


def unreferenced(rel: pathlib.Path, root: pathlib.Path) -> list[tuple[int, str]]:
    """All ``D<number>`` tokens in one file: ``(line_no, token)``."""
    text = (root / rel).read_text(encoding="utf-8")
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _TOKEN.finditer(line):
            hits.append((lineno, match.group(0)))
    return hits


def check_root(root: pathlib.Path) -> tuple[list[str], int]:
    authority = root / AUTHORITY
    if not authority.exists():
        return [f"{AUTHORITY} not found under {root}"], 1

    authorized = authorized_numbers(authority.read_text(encoding="utf-8"))
    problems: list[str] = []

    if authorized:
        max_num = max(authorized)
        expected = frozenset(range(1, max_num + 1))
        if authorized != expected:
            missing = sorted(expected - authorized)
            problems.append(
                f"{AUTHORITY} is not contiguous 1..{max_num}; missing: {missing}"
            )
    else:
        problems.append(f"{AUTHORITY} defines no ## D<number> headers")

    for rel in live_files(root):
        for lineno, token in unreferenced(rel, root):
            number = int(token[1:])
            if number not in authorized:
                problems.append(
                    f"{rel}:{lineno}: '{token}' does not resolve in {AUTHORITY}"
                )
    return problems, 0


def selftest_fixtures() -> tuple[pathlib.Path, pathlib.Path]:
    """Good fixture tree: authority + one live doc + one live module. (Bad trees are
    built inline in :func:`run_selftest`.)"""
    good = pathlib.Path(tempfile.mkdtemp(prefix="decfs_good_"))
    authority = good / AUTHORITY
    authority.parent.mkdir(parents=True, exist_ok=True)
    authority.write_text(
        "## D1 - one\n%%\n## D2 - two\n\n## D3 - three\n", encoding="utf-8"
    )
    (good / "docs").mkdir(exist_ok=True)
    (good / "docs" / "LIVE.md").write_text("Uses D3 with D1 context.\n", encoding="utf-8")
    (good / "src").mkdir(exist_ok=True)
    (good / "src" / "mod.py").write_text("# fine (D2)\n", encoding="utf-8")
    return good, authority


def run_selftest() -> int:
    """Mutating fixture checks: a clean tree passes, a dangling ref fails."""
    good, _ = selftest_fixtures()
    good_problems, _ = check_root(good)
    if good_problems:
        print(
            "SELFTEST FAIL: clean fixture flagged:\n" + "\n".join(good_problems)
        )
        return 1

    bad = pathlib.Path(tempfile.mkdtemp(prefix="decfs_bad_"))
    authority = bad / AUTHORITY
    authority.parent.mkdir(parents=True, exist_ok=True)
    authority.write_text("## D1 - one\n## D2 - two\n## D3 - three\n", encoding="utf-8")
    (bad / "docs").mkdir(exist_ok=True)
    (bad / "docs" / "LIVE.md").write_text("Mentions D5.\n", encoding="utf-8")
    bad_problems, _ = check_root(bad)
    if not any("'D5' does not resolve" in p for p in bad_problems):
        print("SELFTEST FAIL: dangling ref not reported:\n" + "\n".join(bad_problems))
        return 1

    authority.write_text(
        "## D1 - one\n## D3 - three\n", encoding="utf-8"
    )  # gap at D2
    gap_problems, _ = check_root(bad)
    if not any("not contiguous" in p for p in gap_problems):
        print("SELFTEST FAIL: numbering gap not reported:\n" + "\n".join(gap_problems))
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    root = pathlib.Path.cwd()

    if "--selftest" in args:
        return run_selftest()

    problems, _ = check_root(root)
    for problem in problems:
        print(problem)
    if problems:
        print(f"decision-reference check FAILED: {len(problems)} problem(s)")
        return 1
    print("decision-reference check: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())