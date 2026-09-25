"""Doc-truth CI checker (roadmap F7, Increment 181).

Closes the "docs drift from reality" finding mechanically, offline, and
self-tested. Four gates:

1. **Counts gate.** Every live doc that cites a suite total (README.md,
   CLAUDE.md, the ROADMAP status marker, and STATUS.md's *latest* entry —
   totals there only grow, so the file maximum is the current claim) must c
   ≥ ``LAST_PUBLISHED_SUITE_TOTAL``, the total published by the previous
   increment. This is regression-proofing the doc-vs-test drift: a doc can
   never silently fall below the last published suite total.

2. **Decision-reference integrity** (reuses the F1 checker,
   ``check_decision_refs.py``, with its whitelists intact).

3. **``SYSTEM_TODAY.md`` spot checks.** The document is the source of truth
   for how Jarvis works *today*, so its inline backticks are a contract:
   every backticked name (file refs and ``\\w``/``.`` symbol tokens) must
   resolve in the tree — a ``.py``/``.md`` ref exists at its path, and each
   dotted word segment of an identifier is a whole-word hit in ``src/``.
   Unbackticked prose is prose and is not checked.

4. **HISTORICAL manifest.** The table in ``docs/claude/INDEX.md`` is the
   single machine-readable list: every row it marks HISTORICAL must exist and
   carry a HISTORICAL banner in its first three lines; every ``docs/claude``
   file carrying that banner must be marked in ``INDEX.md``; and the manifest
   must equal the F1 checker's own whitelist (no second, drifting list).

Usage::

    python scripts/check_docs_truth.py             # check the repository
    python scripts/check_docs_truth.py --selftest  # embedded fixture checks

Exit code is 0 when clean, 1 otherwise. Stdlib only; offline by design (D8).
"""

from __future__ import annotations

import pathlib
import re
import sys
import tempfile

import check_decision_refs as decision_refs

LAST_PUBLISHED_SUITE_TOTAL = 2352  # Increment 180 (roadmap F6d) published total.

COUNTS_FILES = (
    pathlib.Path("README.md"),
    pathlib.Path("CLAUDE.md"),
    pathlib.Path("docs/claude/ROADMAP_TO_ZERO_FALLOUT.md"),
    pathlib.Path("STATUS.md"),
)
COUNTS_RULES = (
    re.compile(r"(\d{4,5})\s+passed"),
    re.compile(r"~?(\d{3,5})\s+tests?(?:,? all)?\s+passing"),
)
SYSTEM_TODAY = pathlib.Path("docs/claude/SYSTEM_TODAY.md")
INDEX = pathlib.Path("docs/claude/INDEX.md")
INLINE_TOKEN = re.compile(r"`([^`\n]+)`")
IDENTIFIER = re.compile(r"\w+")
BANNER = re.compile(r"^.{0,6}HISTORICAL", re.MULTILINE)
INDEX_ROW = re.compile(r"^\|\s*`?([^`|]+\.md)`?.*HISTORICAL", re.MULTILINE)


def suite_claims(text: str) -> list[int]:
    """All suite-total figures cited in one document, in order."""
    claims: list[int] = []
    for rule in COUNTS_RULES:
        claims.extend(int(m) for m in rule.findall(text))
    return claims


def counts_problems(root: pathlib.Path) -> list[str]:
    """Every live doc's best claim must not undercut the published total."""
    problems: list[str] = []
    for rel in COUNTS_FILES:
        path = root / rel
        if not path.exists():
            continue  # optional docs (e.g. README in fixtures) are not required
        claims = suite_claims(path.read_text(encoding="utf-8"))
        if not claims:
            continue
        best = max(claims)
        if best < LAST_PUBLISHED_SUITE_TOTAL:
            problems.append(
                f"{rel}: best cited suite total {best} is below the last "
                f"published {LAST_PUBLISHED_SUITE_TOTAL}"
            )
    return problems


def symbol_tokens(text: str) -> list[str]:
    """Inline backticked tokens that are file refs or ``\\w``/``.`` identifiers.

    Multi-line fenced content is not "inline" and is ignored; the diagram's
    names are prose, not backticked symbols.
    """
    tokens: list[str] = []
    for match in INLINE_TOKEN.finditer(text):
        token = match.group(1).strip()
        if token and re.fullmatch(r"[\w./.]+", token):
            tokens.append(token)
    return tokens


def file_exists(rel: str, root: pathlib.Path) -> bool:
    """A dotted path resolves when it exists relative to the root or as a
    basename under one of the known trees (src/ or docs/)."""
    dirt = pathlib.Path(rel)
    if (root / dirt).is_file():
        return True
    name = dirt.name
    if name.endswith(".py"):
        return any(p.name == name for p in (root / "src").rglob("*.py"))
    if name.endswith(".md"):
        return any(p.name == name for p in (root / "docs").rglob("*.md"))
    return False


def symbols_problems(root: pathlib.Path) -> list[str]:
    """SYSTEM_TODAY backticks: every referenced file/symbol must exist."""
    path = root / SYSTEM_TODAY
    if not path.exists():
        return []
    sources: list[str] = []
    for p in sorted((root / "src").rglob("*")):
        if p.is_file() and p.suffix in {".py", ".html", ".js"}:
            sources.append(p.read_text(encoding="utf-8"))
    corpus = "\n".join(sources)
    problems: list[str] = []
    for token in symbol_tokens(path.read_text(encoding="utf-8")):
        if "." in token and file_exists(token, root):
            continue
        for segment in IDENTIFIER.findall(token):
            if not segment.isidentifier() or segment.isdigit():
                continue
            if re.search(rf"\b{re.escape(segment)}\b", corpus) is None:
                problems.append(
                    f"{SYSTEM_TODAY}: backticked name {token!r} has no hit "
                    f"for {segment!r} in src/"
                )
    return problems


def historical_manifest(root: pathlib.Path) -> tuple[set[str], set[str]]:
    """``(marked_in_index, banner_in_docs)`` for ``docs/claude/*.md``.

    ``docs/claude/audits/`` is self-describing (the folder name *is* the
    whitelist, mirroring the F1 checker) and is excluded from both sides.
    """
    index = (root / INDEX).read_text(encoding="utf-8")
    marked = {
        m.group(1).strip()
        for m in INDEX_ROW.finditer(index)
        if m.group(1).strip().startswith("docs/claude/")
    }
    docs_dir = root / "docs" / "claude"
    banner: set[str] = set()
    for path in sorted(docs_dir.rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        if any(part == "audits" for part in path.parts):
            continue
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:3])
        if BANNER.search(head):
            banner.add(rel)
    return marked, banner


def manifest_problems(root: pathlib.Path) -> list[str]:
    """INDEX.md is the single HISTORICAL list; banners must match exactly."""
    marked, banner = historical_manifest(root)
    problems: list[str] = []
    missing = marked - banner
    for rel in sorted(missing):
        problems.append(f"{rel}: marked HISTORICAL in INDEX.md but no banner")
    unlisted = banner - marked
    for rel in sorted(unlisted):
        problems.append(f"{rel}: has a HISTORICAL banner but is not in INDEX.md")
    f1 = {str(p).replace("\\", "/") for p in decision_refs.HISTORICAL_DOCS}
    if f1 != marked:
        fm = f1 - marked
        mf = marked - f1
        if fm:
            problems.append(
                "check_decision_refs whitelists files not in INDEX.md: "
                + ", ".join(sorted(fm))
            )
        if mf:
            problems.append(
                "INDEX.md marks files the F1 checker does not whitelist: "
                + ", ".join(sorted(mf))
            )
    return problems


def check_root(root: pathlib.Path) -> tuple[list[str], list[str]]:
    """All doc-truth gates at ``root``. Returns (problems, placeholders)."""
    problems = counts_problems(root)
    problems.extend(symbols_problems(root))
    problems.extend(manifest_problems(root))
    ref_problems, _ = decision_refs.check_root(root)
    problems.extend(ref_problems)
    return problems, []


def run_selftest() -> int:
    """Fixture tree: clean passes; a dropped count, a dangling symbol, a
    banner without a manifest row, and a dangling D-ref each fail."""
    good = pathlib.Path(tempfile.mkdtemp(prefix="doct_good_"))
    (good / "README.md").write_text(
        f"~{LAST_PUBLISHED_SUITE_TOTAL} tests, all passing\n", encoding="utf-8"
    )
    (good / "docs" / "claude").mkdir(parents=True)
    (good / "docs" / "claude" / "SYSTEM_TODAY.md").write_text(
        "See `Jarvis.run` and `docs/claude/AI_CONTEXT.md`.\n", encoding="utf-8"
    )
    (good / "docs" / "claude" / "AI_CONTEXT.md").write_text(
        "D1 - fine.\n", encoding="utf-8"
    )
    (good / "docs" / "claude" / "DECISIONS.md").write_text(
        "## D1 - one\n", encoding="utf-8"
    )
    (good / "docs" / "claude" / "INDEX.md").write_text("", encoding="utf-8")
    (good / "src" / "jarvis").mkdir(parents=True)
    (good / "src" / "jarvis" / "jarvis.py").write_text(
        "class Jarvis:\n    def run(self) -> None: ...\n", encoding="utf-8"
    )
    good_docs = decision_refs.HISTORICAL_DOCS
    decision_refs.HISTORICAL_DOCS = frozenset({})
    try:
        problems, _ = check_root(good)
        if problems:
            print("SELFTEST FAIL (clean fixture):\n" + "\n".join(problems))
            return 1

        (good / "README.md").write_text(
            f"~{LAST_PUBLISHED_SUITE_TOTAL - 10} tests, all passing\n",
            encoding="utf-8",
        )
        if not any("below the last published" in p for p in check_root(good)[0]):
            print("SELFTEST FAIL: understated count not reported")
            return 1
        (good / "README.md").write_text(
            f"~{LAST_PUBLISHED_SUITE_TOTAL} tests, all passing\n",
            encoding="utf-8",
        )

        (good / "docs" / "claude" / "SYSTEM_TODAY.md").write_text(
            "Uses `jarvis.missing_symbol`.\n", encoding="utf-8"
        )
        if not any("no hit" in p for p in check_root(good)[0]):
            print("SELFTEST FAIL: dangling symbol not reported")
            return 1
        (good / "docs" / "claude" / "SYSTEM_TODAY.md").write_text(
            "See `Jarvis.run` and `docs/claude/AI_CONTEXT.md`.\n",
            encoding="utf-8",
        )

        (good / "docs" / "claude" / "ORPHAN.md").write_text(
            "> **HISTORICAL / SUPERSEDED.**\n", encoding="utf-8"
        )
        if not any("not in INDEX.md" in p for p in check_root(good)[0]):
            print("SELFTEST FAIL: orphan banner not reported")
            return 1
        return 0
    finally:
        decision_refs.HISTORICAL_DOCS = good_docs


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    root = pathlib.Path.cwd()
    if "--selftest" in args:
        return run_selftest()

    problems, _ = check_root(root)
    for problem in problems:
        print(problem)
    if problems:
        print(f"doc-truth check FAILED: {len(problems)} problem(s)")
        return 1
    print(
        "doc-truth check: clean (counts, decision-refs, SYSTEM_TODAY symbols, "
        "HISTORICAL manifest)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())