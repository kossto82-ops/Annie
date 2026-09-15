# Semantic Cognition & Attention Development — Implementation

**Status:** implemented, tested, ship-ready pending final classification (all parts done 2026-09-14).
**Baseline:** `docs/claude/SEMANTIC_ATTENTION_AUDIT.md` — "SEMANTIC LIMITED / ATTENTION PARTIAL".
This document records what was changed to close the audited gaps and the honest boundaries that remain.

## 0. Final classification (Part 26)

Re-grading the audit scorecard after implementation (evidence: full suite **1768 passed**, 95-test
`tests/semantic_attention/` harness, restart + Day0–7 longitudinal tests):

| Capability | Audit | Now | Basis |
|---|---|---|---|
| Semantic generalization | FAIL (word-set identity, dead code) | **PROVEN, vocabulary-bounded** | Tier 1–4 all reproduce through the concept vocabulary (stemming, synonyms, ROLE-excluded structural analogy, cross-domain transfer); wired into `_remember`; persisted; recall is concept-aware. Boundary: the ~170-stem English map — genuinely new concepts extend it by editing the map with tests (D15), never per-use. |
| Attention development | PARTIAL (binary router + static curiosity priority) | **PROVEN (ranked surface)** | `attention_priorities()` / `wake()` rank topics by accumulated experience (recurrence / unresolved / revision / recency), bounded, reversible, derived per read (D16). Day0–7 experiment: fresh Jarvis is quiet, the same history makes it wake. Boundary: the `feel_curious()` cascade keeps its static class order — ranked attention is a parallel honest surface, not a rewrite of the cascade. |

**Overall: grade B.** The audited gaps are closed and the loops are real, wired, and
restart-persistent — but the semantic core is a bounded deterministic vocabulary (no live-provider
generalization by design) and the static attention cascade is intentionally preserved, so this is a
high-quality bounded fix rather than an unbounded semantic understanding rearchitecture.

Deeper meaning modeling (learned synonyms beyond the map, unbounded paraphrase) is a follow-up that
must go through the provider/perception seams — it must not become a second bypass (D6/D15).

## 1. The loop that was missing

The audit found three operational gaps:

1. **Dead semantic abstraction.** `abstract_patterns()` existed but was called nowhere; the runtime
   path was *word-set identity only* — paraphrases, analogies and cross-domain analogies did not
   recall, abstract or re-enter reasoning (audit §1).
2. **No persisted semantic memory.** The `SemanticMemoryRepository` existed behind InMemory/SQLite
   stores, but no composition root wired one, so nothing could survive a restart.
3. **Static curiosity priority.** `feel_curious()`'s cascade was a hardcoded class order; there was no
   *ranked* attention learned from experience and no "what to attend to next" surface (audit §2.2).

## 2. What was built

### 2.1 A deterministic semantic abstraction layer (no LLM, no embeddings)

`src/jarvis/domain/services/abstraction.py` now implements a full concepts-first pipeline:

- **Conceptual vocabulary** `_CONCEPT_MAP` (~170 entries): English stems → canonical concept tokens
  (FAIL / SUCCEED / DELIVER / PROMISE / REQUEST / DECREASE / INCREASE / RISK / SAFE / DECIDE /
  CAUSE / PREVENT / TIME / COST). Includes reliability words (`unreliable`→FAIL), compound/prefix
  forms (`overpromised`→PROMISE, `underdelivered`→DELIVER) and raw coverage for
  `delivery`/`deadline`/`promise`.
- **Try-all-suffix stemmer**: for each suffix, keep the first stem that resolves in the map, so
  `promises`→PROMISE, `missed`→FAIL, `schedules`→TIME work without enumerating every inflection.
- **Entity-independent signatures**: role nouns (`supplier`, `vendor`, `contractor`, `client`, …)
  are normalised to a ROLE token that contributes nothing to a signature, so structurally analogous
  episodes about different actors cluster identically.
- **Clustering** = union-find over Jaccard ≥ 0.2 with ≥ 1 shared non-entity concept, `min_sources=3`.
- **Pattern** = the *intersection* of each cluster's signatures, rendered English-only as
  `"recurrence: FAIL, PROMISE"`.
- **Valence + contradiction-awareness**: `_valence()` flips on negation (`not fail`→positive),
  FAIL→negative, SUCCEED→positive. Each member episode feeds the memory evidence with
  `supports = valence != "positive"`, so a mixed-outcome history *contests* the pattern through the
  existing `SemanticMemoryContested` machinery instead of collapsing into false certainty.
- **Memoized, correct caching**: signatures are cached by **trigger text** (not episode id), so a
  colliding id can never serve a stale signature.

`consolidate_semantic_memories(episodes, store, min_sources=3, window=50)` is the lifecycle upsert:
it clusters only the most recent `window` episodes (bounded consolidation — no full-history
quadratic rescans) and upserts by pattern key, merging new source evidence into existing memories.

### 2.2 The lifecycle closes

`ExecutiveController._remember()` now runs `consolidate_semantic_memories` against the wired
`semantic_memory_store` after every recorded episode. `Jarvis.__init__` threads the store through;
a bare `Jarvis()` (no store) never touches the abstraction layer — offline & deterministic by default.

### 2.3 Persistence everywhere

- `JsonSemanticMemoryStore` — new file-backed store (`semantic_memories.json`), mirroring the SQLite
  serialisation; confidence re-derived from evidence on load, never persisted as an assertion.
- `build_persistent_kwargs()` wires it under `directory/`.
- `SqliteRepositories.semantic` + `build_sqlite_repositories()` wire `SqliteSemanticMemoryStore`
  into the joint `jarvis.db`.
- `build_database_kwargs()` and `create_jarvis()` (both `home=` and in-memory paths) wire it too.
- `atomic_write_text` gained a short Windows-safe retry around `os.replace` (AV scanners can
  transiently hold the target open; the semantic store increased write frequency).

### 2.4 Concept-aware recall

`lexical_memory_retriever.py` scores SEMANTIC-kind candidates by
`max(lexical_relevance, _concept_relevance(query, pattern))` using `conceptual_tokens`. Strong
concept recall (≥ 0.6) correctly bypasses the live reasoner (fast, grounded inference);
weak recall still reaches it. The recall floor stays 0.2 and recall never writes to beliefs.

### 2.5 Ranked attention learned from experience

New `AttentionPriority` value object + `derive_attention_priorities(episodes, window=50)` service:

- Signals per topic: **recurrence** (how often touched), **unresolved** (episodes ending below the
  grounded threshold), **revision** (belief confidence moved across visits), **recency** (last touch).
- **Bounded by construction** — the window caps every signal; the score saturates into `[0,1]`.
- **Derived & reversible** — pure function of episode history per read; no second authoritative
  learning state, no persisted scores, recomputation is identical, nothing is mutated.
- New public surfaces: `Jarvis.attention_priorities()` (the ranking) and `Jarvis.wake()` (what to
  attend to next — an impulse when the top saliency clears `ATTEND_THRESHOLD = 0.40`, interoperable
  with `pursue()`). The static `feel_curious()` cascade is untouched; priority learning lives in a
  parallel, honest surface and is asserted not to mutate state.

## 3. Honest boundaries (what this does NOT do)

- **No LLM involved.** The abstraction layer is a hand-maintained English concept map. It generalizes
  within its vocabulary; genuinely novel/unlexicalized semantic relations need the opt-in
  provider/perception seams (D6/D7), never a second bypass.
- **The cascade stays static.** `feel_curious()` keeps its class order; `wake()` is the ranked
  pathway. We did not re-wire the cascade's internal winners because 40+ tests and the goal
  suppression/stickiness semantics pin them.
- **Clustering is intersection-based.** Adding a topic to a mixed cluster narrows the shared pattern
  (e.g. `{FAIL,PROMISE}` + `{DELIVER,TIME}` → `DELIVER`). This is the honest "mixed outcomes"
  abstraction, not a bug.
- **Recall ≠ evidence.** Recalled memory is candidate context only; beliefs stay evidence-derived (D3).

## 4. Verification

- `tests/semantic_attention/` grew from 45 → **95 tests** (baseline probes, lexical abstraction,
  semantic generalization incl. negative + contradiction + adversarial, attention preferences,
  bounded consolidation, Day0-7 longitudinal fresh-vs-experienced).
- Persistence restart tests added in `tests/test_jarvis_persistence.py` (JSON, SQLite,
  command-center roots all survive with semantic memories).
- Full suite: **1768 passed, 6 skipped, 1 pre-existing env-dependent live-provider failure**
  (the pydantic-ai on-demand test that needs a real provider). Ruf checks clean.

## 5. Files changed

| Area | Files |
|---|---|
| Abstraction | `src/jarvis/domain/services/abstraction.py` (rewritten) |
| Attention | `src/jarvis/domain/value_objects/attention_priority.py`, `src/jarvis/domain/services/attention_priority.py`, `src/jarvis/curiosity.py`, `src/jarvis/jarvis.py` |
| Persistence | `src/jarvis/infrastructure/json_semantic_memory_store.py`, `src/jarvis/persistence.py`, `src/jarvis/infrastructure/sqlite_database.py`, `src/jarvis/interface/server.py` |
| Robustness | `src/jarvis/infrastructure/atomic_write.py` |
| Recall | `src/jarvis/infrastructure/lexical_memory_retriever.py` |
| Tests | `tests/semantic_attention/` (live harness), `tests/domain/test_abstraction.py`, `tests/test_jarvis_persistence.py`, `tests/test_public_surface.py` |