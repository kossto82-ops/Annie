"""Broad-except audit gate (roadmap F7, Increment 181).

F7's acceptance wants the ``except Exception`` count in ``src/`` to be
*audited, not drifting*: every blanket catch must be listed here, with a
category and a swallow policy, and the live tree must match this table
exactly -- no unlisted site, no stale entry. Any silent swallow (a catch that
discards an error into a fake success) fails the gate.

Categories (where the catch sits):

* ``boundary``      -- IO/edge/protocol boundary (adapter, provider, tool,
                        store, transport). The injected code can raise
                        anything; the *core* must stay deterministic.
* ``presentation``  -- rendering/voice/UI layer: a failure must never break
                        the page or the reply.
* ``cleanup``       -- ``finally`` teardown whose own failure must not mask
                        the operation's real outcome.

Swallow policies (what happens to the caught error):

* ``outcome``  -- an honest result/message carries the failure (never empty).
* ``degrade``  -- documented fallback (e.g. a store panel shows zero, recall
                  falls back to lexical, a provider yields no inference).
* ``reraise``  -- cleanup then re-raise; nothing is swallowed.
* ``cleanup``  -- only the teardown's own exception is suppressed.
* ``report``   -- the honest failure is recorded, then re-raised.

There is deliberately no ``silent`` policy: the loader rejects it. The audit
is keyed by *ordinal* (order of appearance within a file), so it survives
line-number shifts while remaining exactly checkable.

Usage::

    python scripts/check_broad_excepts.py             # check the repository
    python scripts/check_broad_excepts.py --selftest  # embedded fixture checks

Exit code is 0 when clean, 1 otherwise. Stdlib only; offline by design (D8).
"""

from __future__ import annotations

import pathlib
import re
import sys
import tempfile

_ALLOWED_POLICIES = frozenset({"outcome", "degrade", "reraise", "cleanup", "report"})

_SITE_RE = re.compile(
    r"except\s+(?:BaseException|Exception)\b"
    r"|except\s*:"
    r"|suppress\(\s*(?:[\w.]+\.)?Exception\s*\)"
)

# path (relative to the project root) -> (category, policy, justification)
# Keyed by the 1-based ordinal of each broad site in file order. If a file has
# sites, the tuple length must equal the live count; leaving a file out means
# it must have none.
AUDIT: dict[str, tuple[tuple[str, str, str], ...]] = {
    "src/jarvis/domain/services/capability_orchestration.py": (
        ("boundary", "outcome",
         "ExternalSource boundary; honest FAILED outcome keeps the error"),
        ("boundary", "degrade",
         "report-only channel probe; a bare False lets the search decide"),
    ),
    "src/jarvis/domain/tools/tool_registry.py": (
        ("boundary", "outcome",
         "Tool boundary at the gate; honest ToolCallResult(ok=False)"),
    ),
    "src/jarvis/infrastructure/agent_reach_source.py": (
        ("boundary", "reraise",
         "LLM-search fetch; wrapped in a contextual RuntimeError"),
        ("boundary", "reraise",
         "Jina fetch; wrapped in a contextual RuntimeError"),
    ),
    "src/jarvis/infrastructure/caldav_sync.py": (
        ("boundary", "reraise",
         "transport fetch; wrapped in a CalDavSyncError"),
    ),
    "src/jarvis/infrastructure/embedding_memory_retriever.py": (
        ("boundary", "degrade",
         "embedder/network; falls back to lexical recall, never breaks"),
    ),
    "src/jarvis/infrastructure/filesystem_tool.py": (
        ("boundary", "outcome",
         "tool I/O; an honest ToolCallResult(ok=False)"),
    ),
    "src/jarvis/infrastructure/knowledge_source.py": (
        ("boundary", "degrade",
         "research edge failed: None consult, never a fabricated claim"),
        ("boundary", "degrade",
         "comparator edge failed: None consult, never a fabricated claim"),
    ),
    "src/jarvis/infrastructure/llm_document_editor.py": (
        ("boundary", "degrade",
         "provider failure: no proposal, never a crash (Vision 37)"),
    ),
    "src/jarvis/infrastructure/llm_reasoner.py": (
        ("boundary", "degrade",
         "provider failure: no inference, never a crash (Vision 37)"),
    ),
    "src/jarvis/infrastructure/llm_response_renderer.py": (
        ("presentation", "outcome",
         "rendering must never break the reply; falls back"),
        ("presentation", "outcome",
         "streaming render falls back to the canonical reply"),
    ),
    "src/jarvis/infrastructure/mail_source.py": (
        ("cleanup", "cleanup", "IMAP logout teardown; the real error propagates"),
        ("cleanup", "cleanup", "IMAP logout teardown; the real error propagates"),
        ("cleanup", "cleanup", "IMAP logout teardown; the real error propagates"),
        ("cleanup", "cleanup", "SMTP close teardown; the real error propagates"),
    ),
    "src/jarvis/infrastructure/mcp_tools.py": (
        ("boundary", "outcome",
         "external tool call stays honest via ToolCallResult(ok=False)"),
    ),
    "src/jarvis/infrastructure/model_compare_source.py": (
        ("boundary", "reraise",
         "comparison model failure; wrapped with the model label"),
    ),
    "src/jarvis/infrastructure/odysseus_search_source.py": (
        ("boundary", "reraise",
         "searxng fetch; wrapped in a contextual RuntimeError"),
    ),
    "src/jarvis/infrastructure/pydantic_ai_model.py": (
        ("boundary", "degrade",
         "provider error/refusal -> guarded honest silence (Vision 37)"),
        ("boundary", "degrade",
         "stream ends early, honestly, on any error"),
    ),
    "src/jarvis/infrastructure/pydantic_ai_task_agent.py": (
        ("boundary", "outcome",
         "provider/loop failure -> fallback or an honest failed TaskResult"),
    ),
    "src/jarvis/infrastructure/task_agent_source.py": (
        ("boundary", "degrade",
         "live MCP edge unreachable: keep local tools, stay offline"),
    ),
    "src/jarvis/interface/_cognition.py": (
        ("boundary", "outcome",
         "companion perceiver/provider failure; honest provider_error"),
        ("presentation", "degrade",
         "a greeting must never break the page; fallback greeting"),
    ),
    "src/jarvis/interface/_conversation.py": (
        ("boundary", "outcome",
         "say pipeline boundary; honest provider_error, never empty"),
        ("boundary", "outcome",
         "web-search act path; honest bilingual error"),
        ("boundary", "outcome",
         "streaming say; honest provider_error, never empty"),
    ),
    "src/jarvis/interface/_crud.py": (
        ("boundary", "outcome", "store boundary; an honest 'I couldn't do that'"),
        ("boundary", "outcome", "store boundary; an honest 'I couldn't do that'"),
        ("boundary", "outcome", "store boundary; an honest 'I couldn't do that'"),
        ("boundary", "outcome", "mailbox boundary; an honest 'I couldn't do that'"),
        ("boundary", "outcome", "store boundary; an honest 'I couldn't do that'"),
    ),
    "src/jarvis/interface/_external.py": (
        ("boundary", "outcome", "external provider boundary; honest error"),
        ("boundary", "outcome", "research provider boundary; honest error"),
        ("boundary", "outcome", "model provider boundary; honest error"),
    ),
    "src/jarvis/interface/_providers.py": (
        ("boundary", "outcome",
         "provider probe; honest {ok: False, reply: ...}"),
    ),
    "src/jarvis/interface/_recall.py": (
        ("boundary", "degrade", "store boundary; the panel shows an empty list"),
    ),
    "src/jarvis/interface/_state.py": (
        ("boundary", "degrade", "store boundary; the panel shows an empty list"),
        ("boundary", "degrade", "store boundary; the panel shows an empty list"),
        ("boundary", "degrade", "store boundary; the panel shows an empty list"),
        ("boundary", "degrade", "store boundary; the panel shows zeros"),
        ("boundary", "degrade", "store boundary; the panel shows an empty list"),
        ("boundary", "degrade", "store boundary; the panel shows 0 beliefs"),
        ("boundary", "degrade", "store boundary; the panel shows 0 threads"),
        ("boundary", "degrade", "store boundary; the panel shows a default"),
        ("boundary", "degrade", "store boundary; the panel shows an empty list"),
    ),
    "src/jarvis/interface/command_center.py": (
        ("boundary", "outcome", "transcription failure; a 502 JSON error"),
        ("boundary", "outcome", "streaming transcription; a 502 JSON error"),
    ),
    "src/jarvis/interface/server.py": (
        ("boundary", "degrade",
         "invalid backup provider config; use the primary model only"),
    ),
    "src/jarvis/jarvis.py": (
        ("boundary", "degrade",
         "reason_stream provider boundary; span records only on completion"),
    ),
    "src/jarvis/surfaces.py": (
        ("boundary", "report",
         "run_task failure is recorded honestly, then re-raised"),
    ),
}


def broad_sites(rel: pathlib.Path, root: pathlib.Path) -> list[tuple[int, str]]:
    """Broad-swallow sites in one module: ``(line_no, matched_text)`` in order."""
    text = (root / rel).read_text(encoding="utf-8")
    hits: list[tuple[int, str]] = []
    for match in _SITE_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        hits.append((line, match.group(0)))
    return hits


def scan_all(root: pathlib.Path) -> dict[str, list[tuple[int, str]]]:
    """Every broad site in ``src/**/*.py``, in file order."""
    found: dict[str, list[tuple[int, str]]] = {}
    src = root / "src"
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        sites = broad_sites(rel, root)
        if sites:
            found[rel] = sites
    return found


def check_audit(root: pathlib.Path) -> tuple[list[str], dict[str, int]]:
    """Compare the live tree against the committed audit table.

    Returns ``(problems, blockers)`` where ``blockers`` maps each audited file
    to its live ``except``-site count (for the acceptance report).
    """
    found = scan_all(root)
    problems: list[str] = []
    blockers: dict[str, int] = {}

    for rel, sites in found.items():
        blockers[rel] = sum(1 for _line, text in sites if "except" in text)
        expected = AUDIT.get(rel, ())
        if len(sites) != len(expected):
            problems.append(
                f"{rel}: {len(sites)} live site(s) vs {len(expected)} audited"
            )
            continue
        for (line, text), (category, policy, _reason) in zip(sites, expected, strict=True):
            if policy not in _ALLOWED_POLICIES:
                problems.append(f"{rel}:{line}: disallowed policy {policy!r}")
            if "except" in text and category == "cleanup":
                problems.append(f"{rel}:{line}: cleanup site is not a suppress")
    for rel in sorted(AUDIT):
        if rel not in blockers:
            problems.append(f"{rel}: audit entry has no live site (stale)")
    return problems, blockers


def run_selftest() -> int:
    """Fixture trees: clean passes; unlisted site, stale entry, and a
    disallowed policy each fail."""
    good = pathlib.Path(tempfile.mkdtemp(prefix="bex_good_"))
    (good / "src" / "pkg").mkdir(parents=True)
    (good / "src" / "pkg" / "a.py").write_text(
        "try:\n    run()\nexcept Exception:\n    return ()", encoding="utf-8"
    )
    (good / "src" / "pkg" / "b.py").write_text(
        "import contextlib\nwith contextlib.suppress(Exception):\n    run()",
        encoding="utf-8",
    )
    old = dict(AUDIT)
    AUDIT.clear()
    AUDIT.update(
        {
            "src/pkg/a.py": (("boundary", "outcome", "fixture"),),
            "src/pkg/b.py": (("cleanup", "cleanup", "suppress fixture"),),
        }
    )
    try:
        problems, blockers = check_audit(good)
        if problems:
            print("SELFTEST FAIL (clean fixture):\n" + "\n".join(problems))
            return 1
        if blockers.get("src/pkg/b.py") != 0:
            print(f"SELFTEST FAIL (blockers): {blockers}")
            return 1

        bad = pathlib.Path(tempfile.mkdtemp(prefix="bex_bad_"))
        (bad / "src").mkdir()
        (bad / "src" / "m.py").write_text(
            "except Exception:\n    pass\n", encoding="utf-8"
        )
        if not (check_audit(bad)[0]):
            print("SELFTEST FAIL: unlisted site not reported")
            return 1

        AUDIT["src/bad2.py"] = (("boundary", "outcome", "stale"),)
        if not (check_audit(good)[0]):
            print("SELFTEST FAIL: stale audit entry not reported")
            return 1

        AUDIT["src/pkg/a.py"] = (("boundary", "silent", "fixture"),)
        if not any(
            "disallowed policy" in p
            for p in check_audit(good)[0]
        ):
            print("SELFTEST FAIL: silent policy not rejected")
            return 1
        return 0
    finally:
        AUDIT.clear()
        AUDIT.update(old)


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    root = pathlib.Path.cwd()
    if "--selftest" in args:
        return run_selftest()

    problems, blockers = check_audit(root)

    total_excepts = sum(blockers.values())
    total_sites = sum(len(sites) for sites in scan_all(root).values())
    if problems:
        for problem in problems:
            print(problem)
        print(f"broad-except audit FAILED: {len(problems)} problem(s)")
        return 1
    print(
        f"broad-except audit: clean - {total_sites} audited site(s) "
        f"({total_excepts} `except Exception`, all non-silent, no drift)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())