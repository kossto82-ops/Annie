# Semantic & Attention Audit — JARVIS

> **HISTORICAL / SUPERSEDED (2026-09-21).** Dated audit record (2026-09-14); the gaps it graded
> ("SEMANTIC LIMITED / ATTENTION PARTIAL") are closed by Increments 162-165. Read
> `docs/claude/SYSTEM_TODAY.md` + `docs/claude/ARCHITECTURE.md` for the current state.

**Date:** 2026-09-14
**Scope:** `src/jarvis` (HEAD of `main`)
**Evidence:** live runtime probes (`python` against the real package, quoted below) + a new 45-test harness at `tests/semantic_attention/` + full source review of the cognition path. Full suite: **1718 passed, 1 failed (pre-existing env-dependent pydantic-ai test), 6 skipped** — the harness introduced zero regressions.

---

## Scorecard

| Capability | Grade | Evidence classification |
|---|---|---|
| **Semantic generalization** (meaning beyond lexical similarity) | **FAIL** (lexical-only) | Tier 1 (lexical variation) — **absent**. Tier 2–4 (paraphrase / structural analogy / abstract transfer) — **absent**. Generalization across ALL tiers is exact word-set identity, and the abstraction layer is dead code. |
| **Attention development** (preferences from accumulated experience) | **PARTIAL** | Binary FULL/BRIEF is *derived* from current belief confidence, not learned. BUT two genuine learning loops exist and reproduce: self-observation → knob/behavior change, and meta-observation → `grounded_confidence` adjustment. Curiosity *priority* is static. |

**Overall classification: SEMANTIC LIMITED / ATTENTION PARTIAL.**

Plain language: JARVIS generalizes only across **identical word sets**; it treats paraphrases, analogies, and cross-domain transfer as brand-new topics (no recall, no abstraction). Its attention is a deterministic depth router, not a ranked preference system — but it does genuinely learn from experience *about* its attention/confidence habits and adjusts its own thresholds.

---

## 1. Semantic generalization

### 1.1 The abstraction mechanism is exact word-set identity — and dead code

`src/jarvis/domain/services/abstraction.py` — `_cluster_episodes` keys clusters by `frozenset` of subject words (stopwords removed, length > 2). No stemming, no synonyms, no embeddings. Word sets must be **identical** to cluster.

Confirmed, live (not inferred):

```
probe7 tier1 clustering: []
probe7 tier3 clustering: []
```

Three episodes sharing the meaning "suppliers keep missing promised delivery dates" but worded differently (Tier 1 — same concept, partial overlap) → **no cluster**. Three episodes with the same structure across different entities (Tier 3) → **no cluster**.

Harness assertions that pin this down (`tests/semantic_attention/test_lexical_abstraction.py`):
- Different word sets, even high-overlap paraphrases → 0 patterns.
- Analogous triggers with different entities → 0 patterns.
- Cross-domain transfers → 0 patterns.
- No stemming (`promised`/`promising`), no synonyms (`missed`/`failed`), word-set identity only (`man` vs `person` don't cluster).

### 1.2 The abstraction function is not wired into cognition

`grep abstract_patterns` across `src/` → **one hit, its own definition**. `abstract_patterns()` has zero callers. The semantic memory store is **write-orphaned**: no code path calls `semantic_memory_store.save(...)`; the store is only ever *read* by retrievers (`memory_candidates.py:117`).

Harness confirms live behavior:

```
tests/semantic_attention/test_attention_behavior.py::test_semantic_store_not_updated_by_think PASSED
```

`think()` with evidence writes an episode, but the wired `InMemorySemanticMemoryStore` remains empty. **No semantic memory is ever produced by normal cognition.** The only way a semantic memory exists today is manual seeding (as this harness does) — which the production composition roots never do.

### 1.3 Pattern text leaks Spanish into the English-only core

`abstraction.py:89,96` builds patterns as `"Los patrones relacionados con: ..., ..."` and evidence `"episodio '<trigger>'"`. Even if abstraction were wired, the stored pattern strings are Spanish — so lexical recall from English queries would match almost nothing.

### 1.4 Recall is token overlap with a hard 0.2 floor

`src/jarvis/infrastructure/lexical_memory_retriever.py` — relevance = `|query_tokens ∩ text_tokens| / |query_tokens|`. `executive_controller.py:72` sets `_MIN_RECALL_RELEVANCE = 0.2`; anything below is dropped (`recall`, line 306; `_recall_into`, line 570).

Live probe of the recall path with a seeded semantic memory:

```
probe5 recall(supplier):   []                 # query shares no tokens with pattern
probe5 recall(contractor): [('unsupported optimistic claims about deadlines...', 'semantic', 0.2)]
probe6 default semantic store: None           # not wired in the default Jarvo
```

### 1.5 Default recall reachability

- Offline default (`Jarvis()`): `enable_recall=False`, no retriever → `recall()` returns `()`.
- `enable_recall=True` wires `DocumentMemoryRetriever(LexicalMemoryRetriever)` (`jarvis.py:597-610`) — still token overlap; documents layered on.
- Embedding retriever exists (`embedding_memory_retriever.py`) but is only reachable via the opt-in `enable_embedding_recall(embedder)` seam (`jarvis.py:748`) with `JARVIS_EMBED_*` config. **No composition root calls it.**

### 1.6 Composition roots never wire semantic memory / KG

Verified by grep across:
- `jarvis.py` `persistent()` (line 1869) and `database()` (line 1887) — no `semantic_memory_store`
- `interface/server.py` `create_jarvis` (both home and no-home branches) — `enable_recall=True` but no semantic store, no knowledge graph
- `infrastructure/sqlite_database.py` `build_sqlite_repositories` — no semantic store in the factory

### 1.7 Tier-by-tier verdict

| Tier | Requirement | Result |
|---|---|---|
| **1 — Lexical variation** | same concept, different words | **FAIL** — only identical word sets cluster/re-call |
| **2 — Paraphrase** | same meaning, no shared content words | **FAIL** |
| **3 — Structural analogy** | same relation, different entities | **FAIL** |
| **4 — Abstract transfer** | pattern reapplied across domains | **FAIL** |

---

## 2. Attention

### 2.1 Attention is a deterministic depth router, not a learned preference

`executive_controller.py:149-160`:

```python
already_known = belief.confidence.value >= grounded
if already_known and not given_new_evidence:
    return Attention.BRIEF
return Attention.FULL
```

BRIEF only when the exact trigger's belief is already confident (≥ 0.5) with no new evidence. Confirmed live:

```
probe1 attention: Attention.FULL     # new topic + evidence
probe2 attention: Attention.BRIEF    # same trigger, belief grounded, no new evidence
probe3 attention: Attention.FULL     # analogy trigger -> brand new topic
```

Attention is binary (FULL/BRIEF), one-dimensional, and derived from immediate state — there is **no ranked/priority attention** (e.g. tiered effort, importance ranking, or saliency learned from past episodes). Attention does not "develop": repeating an experience changes the *belief*, and attention follows the belief automatically.

### 2.2 The honest-negative path works

A same-trigger repeat with a 0.0-confidence belief stays FULL (harness `test_ungrounded_repeat_stays_full`), and new evidence on a known trigger keeps FULL (`test_same_trigger_second_new_evidence_is_full`). So BRIEF is never used to dodge work — it only fires when Jarvis truthfully already holds the view.

### 2.3 Learning loops that DO exist (genuine experience → behavior change)

**Self-observation (Phase 2A, `self_observation.py`).** Reproduced live: after repeated ungrounded episodes, the decision text changes from the honest silence ("Insufficient evidence…") to a learned acknowledgement:

```
"I have learned that I tend to conclude without sufficient evidence, so rather
than guess about: ungrounded topic 3, I am asking for evidence before concluding
(confidence 0.00)."
```

Harness `test_ungrounded_episode_fires_acknowledgement` covers this. This is **learning about one's own attention/confidence habits**, expressed through `adapt_knobs_from_self_observation` changing knobs after every recorded episode (`executive_controller.py:415-419`).

**Meta-observation (Phase 7, `meta_observation.py`).** `adapt_from_meta_observation()` (executive_controller.py:238-284) evaluates reasoning effectiveness, retrieval quality, and attention allocation; when attention is judged insufficient it raises `grounded_confidence` by 0.05 (cap 0.9). Harness `test_meta_observation_adjusts_knobs` confirms the seam executes without error and can only raise (or leave) the threshold.

**Attention investment tracks accumulated evidence.** With enough grounding, repeated triggers produce BRIEF (`test_brief_after_grounded_repetition`); new evidence always forces FULL. So accumulated experience DOES shape attention — but only through the belief's confidence, not through a preference model.

### 2.4 Curiosity cascade is static

`feel_curious()` + `pursue()` reproduce (harness `TestCuriosityCascadeInitiative`, 3 tests) — a fresh Jarvis is quiet, committed evidence can raise an impulse, and `pursue()` runs a CURIOSITY-origin episode. But the cascade priority (self → contested → load-bearing → recurring goals → capability → meta → temporal) is a hardcoded list in `jarvis/curiosity.py`; experience cannot re-rank it. There is no "what to attend to next" learning.

### 2.5 Categorization / lateral links

- **No categories:** no category/tag/label surface on episodes (harness `test_no_explicit_categories_exist`).
- **Lateral connections:** none — an unrelated follow-up trigger recalls nothing (harness `test_no_associative_link_across_domains`).

---

## 3. The one working semantic path: recall → reasoner → belief

When a semantic memory IS present and the query clears the 0.2 token floor, a live reasoner genuinely grounds a belief from it. Reproduced (`tests/semantic_attention/test_attention_behavior.py::TestRecallChainToDecision`):

- `recall` surfaces the pattern → a `ProbeReasoner` receives it in `infer(query, memory, ...)` → returns `Inference` → `_reason_into` observes it as weight-0.6 INFERENCE evidence (`executive_controller.py:622-633`) → belief confidence > 0.
- Without a live reasoner (offline `SilentReasoner` default), recalled memory alone is **not** evidence: `inference is None`, episode concludes "Insufficient evidence".

So the architecture *can* route semantic knowledge into decisions — but only if (a) a reasoner is wired, and (b) a semantic memory was pre-seeded by hand, because nothing in the lifecycle creates them.

---

## 4. Architecture rating (Part 22–24 summary)

| Aspect | State |
|---|---|
| Recall → decision chain (when memory exists) | **Working seam** (D11 honoured) |
| Semantic memory production | **Missing** — write path dead, function exists but uncalled |
| Semantic retrieval | **Lexical only by default**; embedding opt-in, unwired |
| Composition roots | No semantic store, no KG server-side |
| Attention routing | Binary, derived, deterministic |
| Self/meta knowledge → knobs | **Real and reproduced** |
| Curiosity re-ranking | Static |
| Categories / lateral association | None |
| Test coverage of these behaviors | New 45-test harness (`tests/semantic_attention/`) |

---

## 5. Recommended minimal changes (justification above)

1. **Wire abstraction into the cognition lifecycle.** Call `abstract_patterns` over episode history in `_remember` (executive_controller.py:822) and `store.save(...)` into the wired semantic store. Deliver a German-free, English pattern template (fixes the §1.3 Spanish leak while touching it).
2. **Composition roots must supply the store.** `persistent()`, `database()`, and `create_jarvis` should construct `SqliteSemanticMemoryStore` and pass it — otherwise wiring the write path changes nothing in production.
3. **Semantic retriever opt-in via existing seam.** `enable_embedding_recall` already exists (`jarvis.py:748`); only its call sites in the composition roots are missing.

These are the *minimal* changes that make the existing (unused) abstraction architecture real. Deeper semantic generalization (paraphrase/structure/transfer) requires a meaning-based scorer — beyond the current evidence-based domain model and a decision for a follow-up.

---

## 6. Evidence index

- Harness: `tests/semantic_attention/` — 45 tests, all passing, ruff-clean.
  - `test_lexical_abstraction.py` — abstraction tiers 1–4, stem/synonym/identity limits
  - `test_attention_behavior.py` — attention routing, semantic recall floor, recall→reasoner→belief
  - `test_attention_preferences.py` — curiosity cascade, self/meta learning loops, honesty
  - `test_learning_deep.py` — recurrence, cross-domain, lateral, categorization, composition
- Live probes (scratch): attention FULL/BRIEF routing, recall floors, empty store behavior, dead-code confirmation.
- Source anchors:
  - `domain/services/abstraction.py:52-116` (word-set clustering; Spanish patterns; dead code)
  - `executive/executive_controller.py:149-160` (attention), `:72` (recall floor), `:238-284` (meta-observation), `:415-419` (self-observation loop), `:553-595` (recall), `:597-633` (reasoning)
  - `infrastructure/lexical_memory_retriever.py:46-56` (token relevance)
  - `jarvis.py:588-610` (retriever wiring), `:748` (embedding seam), `:1869/:1887` (persistent/database), `interface/server.py:183/214` (server composition)