# Jarvis — Post-Audit Implementation Plan

> **HISTORICAL / COMPLETADO (2026-09-21).** Plan de implementación del 2026-09-13
> (Phases 0-12 + fases del pydantic-ai thread), todo ejecutado a través del Incremento 161.
> Conservado por traza; la verdad actual vive en `docs/claude/SYSTEM_TODAY.md`.

Generated: 2026-09-13

## Baseline (Phase 0)

- **Tests**: 1647 passed, 3 skipped (16.10s)
- **Ruff**: 1 import-sort error (fixed with `--fix`)
- **Pyright strict**: 354 errors (pre-existing; mostly `reportPrivateUsage` — accessing `_` prefixed members across modules in strict mode)
- **Zero runtime dependencies** (stdlib only)
- **Python ≥3.11**

## Phase 1 — Wire What Already Exists ✅

### 1A: Semantic Memory + Conversation → Recall ✅

**Implemented**: Added `semantic_memories` and `conversation` parameters to `LexicalMemoryRetriever` and `EmbeddingMemoryRetriever` constructors, passing them to `gather_candidates()`. Wired in `Jarvis.__init__` and `enable_embedding_recall`.

**Files changed**:
- `src/jarvis/infrastructure/lexical_memory_retriever.py` — added 2 params + TYPE_CHECKING imports
- `src/jarvis/infrastructure/embedding_memory_retriever.py` — added 2 params + TYPE_CHECKING imports
- `src/jarvis/jarvis.py` — added `semantic_memory_store` and `conversation_repository` params, wired to retrievers

**Result**: Semantic memories and conversation turns now surface as recall candidates (`MemoryKind.SEMANTIC`, `MemoryKind.CONVERSATION`).

### 1B: Conversation Persistence ✅

**Implemented**: Added `conversation_repository` parameter to `Jarvis.__init__`, wired to `ConversationContext(repository=...)`. Added `InMemoryConversationStore` to `build_persistent_kwargs` and `SqliteConversationStore` to `build_database_kwargs`.

**Files changed**:
- `src/jarvis/jarvis.py` — added param, wired to ConversationContext
- `src/jarvis/persistence.py` — added conversation store to both factories

**Result**: Conversation turns now persist across restarts (SQLite path) or are at least wired for persistence (JSON path uses in-memory store).

### 1C: Evidence Deduplication ✅

**Implemented**: Added optional `_dedup_policy` field to `Belief` and `SemanticMemory`. When configured, identical evidence (same content + source + direction) is skipped. Without a policy, all evidence is appended unconditionally (preserving historical default).

**Files changed**:
- `src/jarvis/domain/entities/belief.py` — added `_dedup_policy` field + dedup check in `add_evidence`
- `src/jarvis/domain/entities/semantic_memory.py` — added `_dedup_policy` parameter + dedup check in `add_evidence`

**Result**: Dedup is opt-in. The invariant "a belief must never be stronger than the evidence supporting it" remains intact. No existing behavior changed.

### 1D: Knowledge Graph — Not Wired (Finding)

**Evaluation**: The graph is fully implemented (`KnowledgeNode`, `KnowledgeEdge`, `KnowledgeGraphRepository`, in-memory + SQLite stores, BFS traversal) but:
- No production code populates it (no entity extraction from beliefs/episodes)
- No production code queries it for cognitive context
- The existing retrieval systems (lexical, semantic, document) already provide good coverage

**Required to make it useful**:
1. Entity extraction from beliefs/episodes (needs NLP or LLM)
2. Relationship extraction
3. Graph population logic
4. Graph retrieval integration with recall

**Recommendation**: The graph does not demonstrate useful cognitive value in its current state. Rather than maintaining dead architecture, we report this finding and leave the graph as-is (well-implemented infrastructure that could be valuable later if entity extraction becomes a priority).

### Phase 1 Verification

- **Tests**: 1647 passed, 3 skipped ✅
- **Ruff**: All checks passed ✅
- **All 4 systems connected**: Semantic memory → recall, Conversation → persistence, Evidence → dedup policy, Knowledge graph → evaluated (not wired)

## Phase 2 — Close the Learning Loop ✅

### 2A: CognitiveKnobs Adaptation ✅

**Implemented**: Added `adapt_knobs_from_self_observation()` to `domain/services/self_observation.py`. This function:
- Evaluates self-observation beliefs after each episode
- When a habit crosses the learned-habit threshold (0.5), adjusts `grounded_confidence`
- Adjustments are bounded (±0.05 per step), reversible (drifts back toward baseline), and inspectable (returns reason string)
- Wired into `ExecutiveController.run()` after `_remember()` — the adaptation bridge closes the learning loop

**Files changed**:
- `src/jarvis/domain/services/self_observation.py` — added `adapt_knobs_from_self_observation()` function
- `src/jarvis/executive/executive_controller.py` — wired adaptation call after episode recording

### 2B: Prove Behavioral Change ✅

**Implemented**: Created `tests/test_adaptation_proves_behavior.py` with 7 tests demonstrating:
1. Before learning: threshold stays at default
2. After repeated failure: threshold rises
3. Bounded: threshold never exceeds 0.9
4. Bounded below: threshold never drops below 0.1
5. Reversible: threshold drifts back when habit stops
6. Step-bounded: each call moves by at most 0.05
7. Accumulates: multiple calls compound

**Result**: The learning loop is closed. Self-observation → self-model → cognitive parameter change → changed future behavior.

### 2C: MetaKnowledge Feedback — Deferred

Meta-observation produces `MetaKnowledge` instances but feeding them back to strategy adjustment requires more infrastructure. Deferred to a future phase as the core learning loop (2A/2B) is now functional.

## Phase 3 — Temporal Cognition ✅

### 3A: Historical Belief Queries ✅

**Implemented**: Created `domain/services/temporal_reasoning.py` with three pure functions:
- `belief_timeline(subject, history)` — returns time-ordered snapshots of a belief's evolution (confidence, stability, decision at each episode)
- `what_changed(subject, start, end, history)` — detects confidence shifts ≥0.1 within a time window
- `belief_snapshot_at(subject, at_time, history)` — reconstructs what was believed at a specific point in time

These answer the roadmap's three questions:
1. **What was believed then?** → `belief_snapshot_at(subject, time, history)`
2. **What is believed now?** → latest entry from `belief_timeline(subject, history)`
3. **What evidence changed it?** → `what_changed(subject, start, end, history)` returns the delta

10 tests prove the behavior across filtering, ordering, time windows, and edge cases.

### 3B: Temporal Pattern Detection — Deferred

Simple patterns (stable preference, changing preference, recurring contradiction) could be built on top of the timeline infrastructure but are not yet wired into cognition. Deferred.

## Phase 4 — Unresolved Items ✅

Codebase is clean: zero TODOs, FIXMEs, or HACKs. No incomplete-work markers found.

## Phase 5 — Decision History with Reasoning ✅

### 5A: Persist Reflection and Evidence Snapshot ✅

**Implemented**:
- Added `EvidenceSnapshot` dataclass to `episode_record.py` — lightweight immutable copy of evidence at episode end
- Added `reflection_note: str | None` and `evidence_snapshot: tuple[EvidenceSnapshot, ...]` to `EpisodeRecord`
- Added `_reflection_note: str | None` field to `CognitiveEpisode` — `record_reflection()` now stores the note on the episode (not just in the event trace)
- Updated `ExecutiveController._remember()` to populate both fields from the episode and belief

**What's now persistable**:
1. What was decided → `decision` field
2. Why (reflection) → `reflection_note` field
3. What evidence supported it → `evidence_snapshot` field
4. When → `recorded_at` field
5. Confidence/stability at time → `conclusion_confidence`, `conclusion_stability`

8 tests prove the new fields work and decision history is reconstructable.

## Phase 6 — Reflection Gating ✅

### 6A: Selective Reflection ✅

**Implemented**: Added `_should_reflect()` method to `ExecutiveController` that gates reflection based on:
1. **Contested evidence** → always reflect (contradictions need attention)
2. **Confidence near threshold** (±0.2 margin) → reflect (uncertain grounding)
3. **Thin belief** (≤3 evidence pieces) → reflect (establishing baseline)
4. **Well-established belief** with clear grounding → skip (saves cognitive work)

Previously, reflection happened on every `FULL` attention episode. Now it only happens when warranted, while preserving all existing test expectations.

6 tests prove the gating behavior across contested, thin, established, and boundary cases.

## Phase 7 — Meta-Knowledge Feedback ✅

### 7A: Second-Order Reflection Loop ✅

**Implemented**:
- Added `adapt_from_meta_observation()` method to `ExecutiveController`
- Wired into `run()` loop after first-order adaptation bridge
- Two feedback mechanisms:
  1. **Reasoning effectiveness**: When deliberations outperform conclusions (confidence ≥0.4), returns feedback suggesting prefer consider() over think()
  2. **Attention allocation**: When most episodes are ungrounded (>70%), raises `grounded_confidence` threshold by 0.05 (bounded at 0.9)

**Bug fixes in meta_observation.py**:
- Fixed evidence `supports` logic in `observe_reasoning_effectiveness` — deliberation episodes now correctly support the "deliberations outperform" claim
- Fixed evidence `supports` logic in `observe_attention_allocation` — ungrounded episodes now correctly support the "insufficient attention" claim

5 tests prove the feedback loop works across reasoning effectiveness, attention allocation, and boundary cases.

## Phases 8-11

### Phase 8 — Temporal Pattern Detection ✅

**Implemented**: Added `TemporalPattern` enum, `TemporalPatternResult` dataclass, and `detect_pattern()` function to `domain/services/temporal_reasoning.py`.

5 patterns detected from a belief's confidence trajectory:
- `STABLE` — confidence range ≤0.1
- `STRENGTHENING` — avg step ≥0.05, all non-negative
- `WEAKENING` — avg step ≤-0.05, all non-positive
- `OSCILLATING` — alternating signs (sign changes ≥ steps-1)
- `RECURRING_CONTRADICTION` — outcomes alternate ≥ n-2 times

**Files changed**:
- `src/jarvis/domain/services/temporal_reasoning.py` — added `TemporalPattern`, `TemporalPatternResult`, `detect_pattern()`

6 tests in `tests/test_temporal_reasoning.py` (total 16 for temporal reasoning).

### Phase 9 — Knowledge Graph Integration ✅

**Implemented**: Wired the existing knowledge graph into the cognitive loop via entity extraction.

- Added `knowledge_graph: KnowledgeGraphRepository | None` param to `ExecutiveController.__init__`
- In `_remember()`, after recording the episode, calls `extract_entities(belief, existing_nodes=graph.all_nodes())` to populate the graph with entities and relationships
- Entity extraction uses existing regex-based extractor (no NLP needed)
- Deduplicates against existing nodes by name

**Files changed**:
- `src/jarvis/executive/executive_controller.py` — added knowledge_graph param, entity extraction in `_remember()`

3 tests in `tests/test_knowledge_graph_integration.py`.

### Phase 10 — Proactive Cognition ✅

**Implemented**: Wired temporal pattern detection into the curiosity cascade.

In `feel_curious()`, after the meta-knowledge check, iterates episode history subjects and calls `detect_pattern()` for each. `OSCILLATING` and `RECURRING_CONTRADICTION` patterns trigger curiosity impulses to investigate unstable beliefs.

**Files changed**:
- `src/jarvis/curiosity.py` — added temporal pattern check as new priority level

2 tests in `tests/test_proactive_cognition.py`.

### Phase 11 — Memory Decay and Consolidation ✅

**Implemented**:
- Added `forget()` method to `BeliefRepository` protocol and all three stores (in-memory, JSON, SQLite)
- Added `confidence_with_policy()` to `Belief` for decay checks
- Created `domain/services/memory_consolidation.py` with `identify_forgetting_candidates()` — finds beliefs with low effective confidence, stale evidence, or no evidence

**Files changed**:
- `src/jarvis/domain/repositories/belief_repository.py` — added `forget()` to protocol
- `src/jarvis/infrastructure/in_memory_belief_store.py` — implemented `forget()`
- `src/jarvis/infrastructure/json_belief_store.py` — implemented `forget()`
- `src/jarvis/infrastructure/sqlite_belief_store.py` — implemented `forget()`
- `src/jarvis/domain/entities/belief.py` — added `confidence_with_policy()`
- `src/jarvis/domain/services/memory_consolidation.py` — new consolidation service

7 tests in `tests/test_memory_consolidation.py`.

## Phase 12: Fallback Provider and Dashboard Integrity

**Goal**: Add automatic failover for the LLM provider and ensure dashboard data is honest.

**What was implemented**:
- `FallbackLanguageModel` wraps a primary and backup `LanguageModel` with automatic failover
- `backup_settings_from_env()` reads `JARVIS_LLM_BACKUP_*` environment variables
- Factory functions accept `model_override` parameter for fallback model injection
- `_instruction_reply()` routes web search cues directly to `ExternalSource`
- Dashboard `capCount` badge shows only active capabilities (ready/acquired), not full catalog

**Files changed**:
- `src/jarvis/infrastructure/fallback_model.py` — new `FallbackLanguageModel`
- `src/jarvis/infrastructure/env_settings.py` — added `backup_settings_from_env()`
- `src/jarvis/infrastructure/perceiver_factory.py` — `model_override` param on 4 factory functions
- `src/jarvis/interface/server.py` — `create_jarvis()` wired with fallback + `model_override`
- `src/jarvis/interface/_conversation.py` — web search cue routing
- `src/jarvis/interface/console.html` — `capCount` shows active-only count

218 conversation/command-center tests pass. Ruff clean.

## Final State

- **Tests**: ~1701 passing (1647 baseline + 54 new)
- **Ruff**: clean
- **Pyright**: strict mode via `pyproject.toml`
- **12 commits pushed** to `origin/main`

## Testing Standard

Every phase includes:
- Unit tests for local logic
- Integration tests for subsystem interaction
- End-to-end tests for real cognitive flows
- Persistence tests for restart continuity
- Adversarial tests for failure and abuse

## Documentation Standard

After each phase: update only documentation that needs updating. Describe what actually exists.
