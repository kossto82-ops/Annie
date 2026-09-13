# Jarvis — Post-Audit Implementation Plan

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

## Phase 3 — Temporal Cognition

### 3A: Historical Beliefs
`belief_at_time(subject, timestamp)` — reconstruct historical state from episodes.

### 3B: Temporal Patterns
Detect stable/changing preferences, recurring contradictions.

## Phases 4-11

See the full roadmap in the user's instructions.

## Testing Standard

Every phase includes:
- Unit tests for local logic
- Integration tests for subsystem interaction
- End-to-end tests for real cognitive flows
- Persistence tests for restart continuity
- Adversarial tests for failure and abuse

## Documentation Standard

After each phase: update only documentation that needs updating. Describe what actually exists.
