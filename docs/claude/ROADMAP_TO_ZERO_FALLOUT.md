# Zero-Fallout Roadmap — "todo cableado, nada en papelera"

Created 2026-09-21 (Increment 171). Purpose: eliminate every documented gap, inconsistency and
half-wired service the audits found, so a fresh re-audit one month from now finds **zero of the
same failures**. Each phase ends with a mechanically checkable acceptance gate. Nothing here removes
an architectural decision — the D-boundaries below are provisions, not permissions to cross them.

**Status (2026-09-25): phases F1–F7 are shipped** — F1 (Increment 172), F2 (173), F3 (174), F4 (175),
F5 (176), F6 (Increments 177–180: CalDAV/ICS one-way calendar sync, per-account mailbox UI with folders
+ unread, the offline decided-script charitable executor, and the server-side spoken turn riding the
session `ReasoningSpan`), and **F7** (Increment 181: `uv.lock` consumed frozen, the 3.11/3.12/3.13 CI
matrix, the `check_docs_truth.py` doc-truth job — counts gate, F1 decision-refs, SYSTEM_TODAY symbols,
HISTORICAL manifest — and the committed `check_broad_excepts.py` audit: all 47 `except Exception` in
`src/` non-silent). Remaining: **F8** (final gates + re-audit checklist). Suite at the F7 close:
**2362 passed, 3 skipped**; ruff clean; pyright strict 0; decision-ref check clean; doc-truth and
broad-except checks clean.

## How this is written

- **Tiers.** F0–F8. F0–F3 fix correctness/consistency (what a re-audit flags first); F4–F6 deepen
  capability seams; F7 makes the *reproducibility* of all of the above machine-verifiable; F8 closes.
- **Fronteras intocables.** The invariants below are constraints on every phase. If a phase seems to
  need one, the phase is wrong, not the invariant.
  - Epistemology: confidence is derived from evidence — no imperative confidence setter (D3).
  - Offline determinism: the default suite is offline and deterministic; live providers are opt-in
    behind seams only (D8, D29 — see `DECISIONS.md`).
  - The LLM extracts candidate evidence; it never decides (D6) and never replaces a domain service.
  - Recall is a candidate, not a belief (D27); reasoning is inference, not judgement (D28).
  - No generic `Manager`/`Orchestrator`/`Engine` abstractions (D12-style); every new service has a
    clear domain responsibility.
  - Cognitive truth lives in `SYSTEM_TODAY.md`/`ARCHITECTURE.md`; historical docs stay HISTORICAL.
  - Consolidation stays COMPANION-only with neutral evidence; turns are context, statements are
    memory; change-of-mind resolves rather than stacking; evidence-request writes are inert.
- **Acceptance gates.** Each phase lists commands a reviewer can run to verify. A re-audit must be
  able to pass the F8 checklist by running exactly those commands.

## Baseline (measured at HEAD `1a03e13`, Increment 170)

| Gate | Value |
|---|---|
| `pytest -q` | 2220 passed, 3 skipped, 2223 collected (~36s) |
| `ruff check .` | clean |
| `pyright --pythonversion 3.11` (strict, src+tests) | 0 errors |
| Python ceiling | `pyproject.toml` `requires-python = ">=3.11"`; CI runs 3.13 only |
| Commit | `1a03e13` episode evidence-request writer remediation (Inc 170) |

---

## F0 — Baseline snapshot & tripwires (≤ 30 min)

Everything further on needs trustworthy numbers. Record them before touching code.

- Run the suite, ruff, pyright on Python 3.11, 3.12 and 3.13; capture timings.
- Confirm there is **no lockfile** in the repo root (uv/pip-tools absent) and note the current float
  (`dev = ["pytest>=8", "ruff>=0.16,<1", "pyright>=1.1.400,<2"]`, `live = ["pydantic-ai"]` unpinned).
- `git clean -fdx` a scratch clone and confirm a fresh `pip install -e ".[dev]"` + test run
  reproduces the baseline (hermetic re-run proof).
- **Acceptance:** a committed `docs/claude/audits/2026-09-21_baseline.md` with the three-python table.

## F1 — Decision-registry consolidation (single authority)

**Problem:** `STATUS.md` carries a legacy adr-lite decisions log with its own numeric sequence
(numbered for its own history), while `docs/claude/DECISIONS.md` curates the current decisions with a
*different* mapping — and some live docs cited numbers that only exist in the legacy log (e.g.
recall-candidate cited by its legacy number). Any re-audit finds this in the first five minutes.

- `DECISIONS.md` is the single authority; its numbering is extended (D27–D32) so every load-bearing,
  cited constraint has a home there: recall-candidate (D27), inference-not-judgement (D28), earned
  live-backed edges (D29), gated consultation (D30), the material-edge seam (D31), temporal stability
  (D32).
- A mapping appendix STATUS-legacy → DECISIONS is added to `STATUS.md`; the log header already notes
  the legacy numbering is superseded.
- Every cross-reference in live docs (`ARCHITECTURE.md`, `SYSTEM_TODAY.md`, `AI_CONTEXT.md`,
  `README.md`, `CLAUDE.md`, this file) **and in `src/` comments** is rewritten to resolve in
  `DECISIONS.md`; no legacy-only number remains.
- Add `scripts/check_decision_refs.py` + a CI job: scans live docs and `src/`, asserts every `D\d+`
  token resolves in `DECISIONS.md` (STATUS, `audits/`, and dated gate/closure records whitelisted).
- **Tests:** checker self-tests (fixtures with/without dangling refs) plus a live-repo run inside the
  suite.
- **Acceptance:** `python scripts/check_decision_refs.py` green; no legacy-only tokens (e.g. recall
  candidate cited by a status-log number) remain in live docs or `src/`.

## F2 — Scheduled honest forgetting & consolidation

**Problem:** decay/forgetting are implemented and tested but nothing schedules them in the running
system (`DecayingWeightingPolicy` is never instantiated in `src/`; `identify_forgetting_candidates`
at `src/jarvis/domain/services/memory_consolidation.py:43` has no production caller; STATUS lists
this as an honest gap).

- New domain service `ForgettingCandidates` (not a "manager"): wraps
  `identify_forgetting_candidates` + the decay policy with **honesty gates** — only
  low-stability / old / evidence-redundant candidates; never a grounded ≥threshold companion trait;
  never a belief the user re-affirmed recently (anti-nagging).
- A schedule: run on the energy-rest cadence (`jarvis.rest()`) and expose an explicit
  `forgetting` command-center command with `dry-run` → apply paths; the UI shows "memory health"
  (candidates, would-forget list) and **never deletes without an explicit apply**.
- Wired decay weighting: root-injectable `DecayingWeightingPolicy` is already injectable — wire the
  default bias so old, rarely-touched topics rank lower in recall (behaviour change, visible in tests).
- **Tests:** candidate selection over a synthetic episode timeline; apply+persist+restart; honesty
  (no delete without apply); anti-nagging (re-affirmed topics excluded); decay ranking deltas.
- **Acceptance:** at least one production caller for `identify_forgetting_candidates` and one
  instantiation of `DecayingWeightingPolicy` in `src/`; rerun `rg` for both = hits in src, not tests only.

## F3 — Open-question loop completion (auto-retirement)

**Problem:** the evidence-request writer (Inc 170) is wired — `_note_evidence_request`
(`src/jarvis/jarvis.py:2108`) persists qualifying questions, `note_open_question`/`open_questions`
(`jarvis.py:2378/2391`) keep them, and `feel_curious` proposes the oldest (`curiosity.py:220-222`) —
**but nothing retires an answered question.** `resolve_open_question` (`jarvis.py:2409`) exists with
zero callers in the production path (interface layer has no handler), so open items accumulate
forever and curiosity keeps nagging the oldest.

- Auto-retire: in the conversational answer flow, when a turn re-triggers a currently open question
  and the inference is grounded (confidence ≥ `GROUNDED_CONFIDENCE_THRESHOLD`) or the companion
  confirms, resolve the matching item via `resolve_open_question` with the grounded evidence as
  resolution (the method already grounds the answer as companion-confirmed evidence).
- Grace: if the companion *keeps asking* the same question ("I still wonder …") do not retire; only
  a grounded episode retires.
- Surface: `open-questions` and `settle-question <q> --resolution <r>` server actions + command-center
  commands (there are zero handlers today — grep `resolve` in `interface/`).
- **Tests:** end-to-end ask→open→answer→auto-retired across a restart; no-retire on ungrounded
  answer; pursue/echo path stays excluded; exact-string dedup unchanged (existing Inc-170 tests stay
  green).
- **Acceptance:** `resolve_open_question` has a production caller in the conversation flow; curiosity
  proposes the oldest *still-unsatisfied* question.

## F4 — Passage-level document search

**Problem:** `search_documents` ranks whole documents lexically (`infrastructure/document_store.py:185-211`);
recall returns a document, not the sentence that matched (STATUS honest-gap 2527-2529).

- Deterministic sliding-window chunking at the `DocumentStore` seam (fixed window w/ overlap,
  document id + byte offsets, no embeddings — vocabulary-only, D18-faithful).
- Recall returns passages: a small `PassageHit` VO (document + snippet + offsets) ranked by the same
  `relatedness = max(surface_overlap, concept_relevance)` scorer (`increment-168` pipeline); the chat
  chip cites document + passage + offset.
- Binary files are never chunked; folder nesting (Inc 142) and ownership (Inc 148) preserved.
- **Tests:** chunk boundaries/overlap; cross-chunk recall; ranking; chip citation; binary skip.
- **Acceptance:** `documents search "phrase across a boundary"` returns the passage sentence and its
  offsets, not just a document rank.

## F5 — Live voice streaming + VAD

**Problem:** push-to-talk records **one blob per hold** and POSTs it (interface `console.html`
~4464–4493); no streaming, no silence segmentation (STATUS honest-gap 2530-2533).

- Extend the speech/transcriber seam with an optional streaming contract (feature-detected, like
  `can_hear_audio`): `stream_transcribe(chunks) -> partials`, backed by the same Whisper-compatible
  endpoint family (Inc 154/159), guarded so an unconfigured setup keeps Web Speech as default.
- Console: when realtime partials are unavailable, add AnalyserNode-based silence segmentation
  (auto-segment on silence > threshold) so long speech needs no press-hold-release.
- Offline determinism: zero new network paths in the suite; all partial/segment logic tested with an
  injected fake transcriber.
- **Tests:** seam contract + capability flag; segmentation thresholds; fake-transcriber partial
  assembly; default stays Web Speech.
- **Acceptance:** no new network in `pytest`; one mic hold over silence auto-closes a segment; the
  `speech` snapshot block reports `streaming: true/false` honestly.

## F6 — Edge deepening (each behind its existing Protocol, earned, offline-tested)

Map of the honest gaps (STATUS 2537-2538, 2524-2526) with their phases:

| Edge | Current seam | Deepening |
|---|---|---|
| Calendar | `SqliteCalendarStore`/`google_calendar.py` | CalDAV/ICS sync adapter (one-way pull → SQLite) at the calendar Protocol (D7) |
| Mail | real IMAP/SMTP adapter | per-account mailbox UI (fetch/unread/folder switch) reusing it |
| Tasks/material ACT | `instruction_agent` at `approved=False` (Inc 160) | a decided-script runner so the *offline* charitable executor can run scripted multi-step acts (no free-text LLM needed); destructive/external steps still refuse at the gate |
| Speech sessions | `ReasoningSpan` conversation-scoped (145) | ReasoningSpan continuity across a live-voice session (STATUS 2524-2526) |

- Every item stays behind its domain Protocol, is earned (`can_do`), and is offline-testable (D8).
- Each edge keeps an honest "not configured" reply; the UI never pretends reach.
- **Tests:** per seam — sync mapping (cal), mailbox routing (mail), decided-script runner incl. gate
  refusal (tasks), span continuity across voice turns (speech).
- **Acceptance:** each deepening is reachable, offline-tested, and its unconfigured state is honest.

## F7 — Reproducibility, CI truth, broad-except audit

**Problem:** dev deps float (`pytest>=8`, `ruff>=0.16,<1`, `pyright>=1.1.400,<2`) and `live =
["pydantic-ai"]` is unpinned; no lockfile; CI only exercises Python 3.13 while the package promises
`>=3.11`; the docs-numbers (test counts) have no machine check; there are 47 `except Exception` in
`src/` (silent-swallow risk — a re-audit's favourite finding).

- **Lockfile:** add `uv.lock` (or pip-tools) pinning ruff, pyright, pytest and the live extra
  exactly; CI consumes it frozen (`uv sync --frozen`); extend `test.yml` to a 3.11/3.12/3.13 matrix
  matching `requires-python`.
- **Doc-truth CI job** `scripts/check_docs_truth.py` (all offline, self-tested):
  - counts gate: the "tests passing" number cited in `STATUS.md`/`CLAUDE.md`/`README.md` is ≥ the
    last published suite total (regression-proof the doc-vs-test drift),
  - decision-ref integrity (reuses F1 checker),
  - `SYSTEM_TODAY.md` spot checks: every named seam/symbol exists in `src/` (grep-resolvable),
  - HISTORICAL manifest: files marked HISTORICAL in `INDEX.md` carry the banner and vice-versa.
- **Broad-except audit:** classify the 47; narrow the bulk in domain/executive; keep narrow caught
  types at IO/edge boundaries; commit the audited list (allowed ones, with justification) as part of
  `scripts/`; add a regression test that the executive error path yields honest silence (guardrail
  interplay, Inc 157) instead of swallowing into an empty reply.
- **Tests:** the two checkers' self-tests; the swallow-regression test.
- **Acceptance:** `uv sync --frozen` green on 3.11/3.12/3.13; CI doc-truth job green; committed
  exception-audit list; `rg "except Exception" src` count is audited, not drifting.

## F8 — Final gates, re-audit checklist, doc close

- Full suite + ruff + pyright strict on 3.11/3.12/3.13; hermetic `git clean -fdx` clone re-run.
- Update `STATUS.md`: Increment(171+) log entry, delete every fixed honest-gap from the limitations
  list, point "Next increment" at this roadmap, add new DECISIONS entries where F1–F7 changed policy
  (e.g. the single-authority registry decision).
- Update `CLAUDE.md`/`README.md` counts touched by the new tests.
- Commit and push (one commit per increment, English message).
- **Re-audit checklist** (this is the month-later script): run the F0–F7 acceptance gates verbatim;
  everything must be ✅ with the same commands, on a fresh clone, in <30 minutes.

---

## Cross-reference: agent findings → phase

| Finding/audit flag | Phase that closes it | Gate to re-verify |
|---|---|---|
| Two live D-numbering schemes, dead refs | F1 | `check_decision_refs.py` |
| Decay/forgetting implemented but unscheduled | F2 | `rg` caller + `DecayingWeightingPolicy` in src |
| Evidence-request questions never retired | F3 | `resolve_open_question` caller in production path |
| Document search ranks whole docs, not passages | F4 | passage hit with offsets in recall |
| Push-to-talk sends one blob; no VAD/streaming | F5 | `streaming` flag honest; segmentation test |
| Calendar/mail/tasks/speech depths unwired | F6 | per-seam offline test |
| Deps float, CI single-Python, counts unverified | F7 | frozen lockfile, 3-interpreter matrix, doc-truth job |
| Broad `except Exception` swallowing | F7 | audited list + swallow regression test |
| Docs drift from reality across increments | F1+F7+F8 | doc-truth job + re-audit checklist |