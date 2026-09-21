# Forensic Closure — Episode-Path ReasoningSpan v1

**Date:** 2026-09-20
**Scope:** Final closure re-audit and freeze of the *Episode-Path ReasoningSpan v1* seam
(`b6a2159`, Increment 166) after the test-hygiene remediation (`a3ab390`) and the three
subsequent increments (167–169).
**Method:** committed-diff inspection, code trace of the full propagation chain, empirical E7
non-vacuousness probe, focused and full regression suites, lint, strict types.
**Final verdict:** **EPISODE-PATH REASONINGSPAN v1 — CLOSED / FROZEN.**

This record supersedes the historical FAIL gate of 2026-09-19 (`71ee914`). The failure was never
in the production architecture: the E1–E9 contract verified clean then and verifies clean now. The
blockers were the audit's own type/test hygiene, and they have been repaired (Section 2). No
production file was changed by the remediation; no production file was changed by this final audit.

---

## 1. Historical gate (kept as history, not the current verdict)

The initial closure attempt returned **FAIL — DO NOT FREEZE** (`71ee914`). Every functional
condition E1–E9 passed in production code, but the audit gate was broken by two blockers:

1. **Five Pyright strict errors at HEAD**, all in the new test code
   (`tests/test_reasoning_span.py`):
   - `reportRedeclaration`: `_RecordingModel` declared twice.
   - `reportOptionalMemberAccess` (×2): `episode.working_belief.evidence` accessed without a guard.
   - `reportUnknownMemberType` + `reportAttributeAccessIssue`: `SemanticMemory.content` accessed —
     a field that does not exist.
2. **Vacuous E7 test** (`test_no_semantic_memory_leakage`): with the default constructor
   `semantic_memories is None` the guard skipped the whole body; with a manually wired store a
   single `think()` left it empty; and had the loop body ever run it would have raised
   `AttributeError` on `SemanticMemory.content`.

The historical record in full lives at `71ee914`; this document records its substance above and the
remediated closure below.

## 2. Remediation

Applied in `a3ab390` (single-commit closure remediation, test file only, `36+/23-`):

- **Duplicate helper removed** — the second `_RecordingModel` declaration was deleted; the module
  already had a single `_RecordingModel` + `_recording_reasoner` helper.
- **Optional accesses narrowed** — `episode.working_belief` is bound to a local with an explicit
  `assert belief is not None` before `.evidence` is read (the suite's established pattern).
- **Invalid `SemanticMemory.content` assumption removed** — assertions now read the real fields:
  `memory.pattern` and `memory.evidence[].content`.
- **E7 rewritten against a real populated semantic-memory store** — wires an
  `InMemorySemanticMemoryStore` into `Jarvis`, runs three same-topic episodes so consolidation
  (`min_sources=3`) genuinely writes a memory, then asserts the span marker semantics.
- **No production changes.** `b6a2159..a3ab390` touches exactly one file: the test file.

## 3. Final validation (run on the current working tree, HEAD `331eb48`)

| Gate | Command | Result |
|---|---|---|
| Focused | `python -m pytest tests/test_reasoning_span.py -q` | **27 passed** |
| Episode path | `TestEpisodePathReasoningSpan` (7 tests, within the focused run) | **7/7 passed** |
| Related | `python -m pytest tests/test_reasoning.py tests/test_public_surface.py -q` | **26 passed** |
| Full | `python -m pytest -q` | **2200 passed, 3 skipped** |
| Lint | `python -m ruff check src tests` | **All checks passed** |
| Types | `python -m pyright` (strict, src+tests) | **0 errors, 0 warnings** |

The test file is byte-identical to `a3ab390` (`git diff a3ab390..HEAD -- tests/test_reasoning_span.py`
is empty). Since the remediation, increments 167–169 touched production jars only in unrelated
surfaces: `jarvis.py` gained `revise_companion` (Increment 169) and `executive_controller.py`
gained meaning-based companion-trait ranking / superseded-stance skipping (Increments 167–168).
None of these changes touch the span seam.

## 4. Production verification (E1–E9, re-traced at current HEAD)

| Condition | Status | Evidence (HEAD) |
|---|---|---|
| **E1** Explicit propagation `Jarvis.think → cognitive.think → run_episode → executive.run → _reason_into → reasoner.infer(..., span)` | **PASS** | `jarvis.py:2071-2072` (snapshot + forward); `cognitive.py:139-144, 154-164` (`think`/`run_episode` keyword-only `span`); `executive_controller.py:577-629` (`run`→`_reason_into(..., span=span)`); `executive_controller.py:935` `infer(episode.trigger, recalled, conversation, span)`; `reasoner.py:34-44` protocol carries `span` |
| **E2** `span is not None` (no truthiness fallback): `span=None` → live instance snapshot; `span=()` → explicitly empty | **PASS** | `jarvis.py:2071`: `threads = span if span is not None else self._reasoning_span.threads()`; test `test_explicit_empty_span_does_not_substitute_live_span` asserts no `<reasoning_span>` in the `span=()` prompt |
| **E3** Completion-only recording | **PASS** | `jarvis.py:2073-2075`: `inference = episode.inference; if inference is not None: self._reasoning_span.record(trigger, inference.answer)` — the episode's concluded inference is non-`None` only when `_reason_into` called `episode.infer` |
| **E4** Recorded thread = `(trigger, inference.answer)`, never span contents | **PASS** | `jarvis.py:2075`; span contents are read only for the prompt (`llm_reasoner.py:101-104`); recording is independent of span contents |
| **E5** Failed inference does not record | **PASS** | `llm_reasoner.py:58-63` returns `None` on provider failure → `_reason_into` returns without `episode.infer` (`executive_controller.py:936-938`) → `episode.inference` is `None` → no `record`; test `test_failure_does_not_advance_the_span` |
| **E6** Instance isolation | **PASS** | `_reasoning_span = ReasoningSpan()` per instance (`jarvis.py:621`); test `test_instance_isolation` |
| **E7** Context-only boundary — never evidence, belief, confidence, SemanticMemory, or persisted state | **PASS** | Span is never written to beliefs (`_reason_into` observes a fresh `Evidence` from `inference.answer` at `executive_controller.py:939-943`), never into semantic memory (`consolidate_semantic_memories` takes episodes, not span threads, `executive_controller.py:1210-1213`), never persisted (no serializer references `ReasoningSpan`); snapshot exposure is read-only (`_state.py:118,526`). Dedicated non-vacuous test — Section 5 |
| **E8** Conversational `reason()` / `reason_stream()` semantics unchanged | **PASS** | `jarvis.py:693,716` keep the pre-existing truthy-fallback `span if span else` and completion-gated recording (`jarvis.py:697-698, 734-735`), identical to the parent commit `13231a8`; Increment 166 did not touch them |
| **E9** Frozen seams untouched | **PASS** | The span seam is additive: keyword-only parameters with defaults; no change to Topic Identity v3, Topic-Anchored Belief Addressing v1, Polarity, Evidence, Confidence, Semantic Memory, Persistence, Session, or Reflection architecture |

## 5. E7 test — non-vacuousness (empirically probed)

`test_no_semantic_memory_leakage` (at `tests/test_reasoning_span.py:270-294`) was probed on the
current tree. Concrete evidence:

1. **A real `InMemorySemanticMemoryStore` is wired** — `Jarvis(..., semantic_memory_store=store)`;
   probe confirms `jarvis.semantic_memories is store` (the injected object, not `None`).
2. **The store genuinely receives a legitimate semantic memory** — three same-topic episodes
   (`"delivery keeps failing"` × 3) drive consolidation (`min_sources=3`) to one memory:
   `pattern = 'recurrence: DELIVER, FAIL'`, evidence `"episode 'delivery keeps failing' (outcome:
   negative)"`. The test's own `assert stored, "consolidation should have created a memory…"`
   fails, rather than skips, if the store is empty.
3. **The span marker reaches the second prompt** — probe: `len(model.prompts) == 3`,
   `"<reasoning_span>" in model.prompts[2]`, `marker in model.prompts[2]` all true. The marker
   (`UNIQUE_SPAN_THREAD_MARKER`) is a distinctive string that exists only inside the recorded span
   thread, so its presence in the prompt proves the `ReasoningSpan → reasoner prompt` direction.
4. **Marker absent from every stored pattern** — probe walks `memory.pattern` for each stored
   memory: `False` for all.
5. **Marker absent from every stored evidence item** — probe walks `memory.evidence[].content`:
   `False` for all.
6. **Independent of `semantic_memories is None`** — there is no such guard; the store is injected
   and populated by design.
7. **No nonexistent `SemanticMemory.content`** — assertions read the real fields `pattern` and
   `evidence` (entity at `semantic_memory.py:71, 97-99`).

Conceptual boundary proven:

```text
ReasoningSpan ──► reasoner prompt                 (proven: marker in prompt)
ReasoningSpan ──► SemanticMemory                  (proven absent: marker never stored)
Inference.answer ─► Evidence ─► consolidation     (allowed, legitimate: the store is genuinely written)
```

The single stored memory is formed from the delivery-topic episodes' own content; the marker's
thread lives only in the prompt. The test therefore asserts the E7 invariant where it could
actually be violated — no longer vacuous.

## 6. Frozen invariants

- **E1** Episode path explicitly propagates `ReasoningSpan`.
- **E2** `span=None` means live snapshot; `span=()` means explicitly empty (no truthiness fallback).
- **E3** Only completed episode inference (`episode.inference is not None`) can advance the span.
- **E4** Recorded thread content is `(trigger, inference.answer)`.
- **E5** Failed inference does not advance the span.
- **E6** `ReasoningSpan` is per-`Jarvis`-instance.
- **E7** `ReasoningSpan` is contextual and never epistemically authoritative.
- **E8** Conversational `ReasoningSpan` behavior (`reason`/`reason_stream`) remains unchanged.
- **E9** No frozen cognitive seam (Topic Identity v3, Topic-Anchored Addressing v1, Polarity,
  Evidence, Confidence, Semantic Memory, Persistence, Session, Reflection) is redefined.

## 7. Accepted limitations (frozen, not defects)

- `curiosity.pursue` remains conversation-free / cold: `run_episode` defaults `span=()`; the
  curiosity path reasons without the session threads and records nothing.
- `ReasoningSpan` remains per-`Jarvis`-instance.
- `reset_reasoning()` remains the explicit reset seam (`jarvis.py:745-747`).
- `ReasoningSpan` is not persisted.
- No first-class session object is introduced.
- Episode-path reasoning remains non-streaming (blocking `infer` at
  `executive_controller.py:935`); streaming stays the conversational `reason_stream` surface.
- No proactive scheduler is introduced by this seam.

These are not defects unless current repository evidence contradicts them — none does.

## 8. Commit status

No commit was created by this final closure audit. The remediation (`a3ab390`) and the seam
(`b6a2159`) already exist in history; the working tree at HEAD `331eb48` is clean except this
document.