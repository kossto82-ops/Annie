# Jarvis — Final Architectural Audit Report

> Generated 2026-09-13. Read-only analysis — no code modified.
> Method: Source-level verification against all 5 audit phases, code inspection, test suite execution (1647 passed, 3 skipped in 21.84s).

---

## 1. Executive Summary

Jarvis is a well-engineered proof-of-concept for a cognitive companion system. It has a genuine epistemic core (evidence-derived confidence), real learning mechanisms (self-observation, reflective cycle), and a clean architecture with proper separation of concerns. The codebase is ~7500 LOC, stdlib-only with zero runtime dependencies, and passes 1647 tests deterministically offline.

However, several documented capabilities are either not wired into the cognitive loop (knowledge graph, conversation persistence) or exist primarily as narration changes rather than fundamental behavioral changes (self-model, meta-observation). The system is genuinely impressive as a proof-of-concept, but it is not yet a persistent cognitive companion in any meaningful operational sense.

**Verdict:** Jarvis is a sophisticated cognitive architecture prototype with real epistemic integrity. It is not production-ready as a companion system. The gap between "what exists in code" and "what the system actually does" is the primary risk.

---

## 2. Architecture (per component)

| Area | Status | Note |
|---|---|---|
| Domain: Belief / Confidence / Evidence / TemporalStability | EXISTS | Confidence = `supporting / (supporting + contradicting + 1)`; never reaches 1.0; no setter. Structural invariant verified. |
| Domain: CognitiveEpisode (state machine) | EXISTS | `CREATED→REASONING→REFLECTING→DECIDING→COMPLETED/FAILED`, illegal transitions blocked. |
| Domain: Hypothesis / HypothesisSet | EXISTS | `leading()` returns None on tie — does not collapse uncertainty. |
| Domain: SemanticMemory / KnowledgeNode / KnowledgeEdge / MetaKnowledge | EXISTS | Fully implemented with repository protocols, SQLite and in-memory stores. **Not wired into cognitive loop.** |
| Domain: services (association, reflection, curiosity, action_advisor, goal_reflection, self_observation, hypothesis_generation, abstraction, meta_observation) | EXISTS | All used and tested. None dead. |
| Domain: Reasoner / MemoryRetriever (seams) | EXISTS (protocol) | LLM proposes; core judges. |
| Domain: ToolRegistry / ToolPolicy / PermissionLevel | EXISTS | Genuinely safe: EXTERNAL_ACTION requires approval, destructive acts refuse. No bypass found. |
| Executive: `ExecutiveController.run` | EXISTS (thin) | ~50 lines episode cycle, delegates to domain. |
| Executive: `_reflect` | EXISTS (real) | **No longer a stub** (verified at `executive_controller.py:623`). Records genuine review notes about contested/well-grounded/thinly-grounded conclusions. Changes nothing about the belief; only records provenance. |
| Infra: stores in-memory + JSON + SQLite | EXISTS | SQLite backed via `Jarvis.database()`, JSON via `Jarvis.persistent()`. Crash-safe (atomic temp+rename, SQLite transactions). |
| Infra: EpisodeTrace | EXISTS (persistent) | JSONL + SQLite (`SqliteEpisodeTrace`). Survives restarts. |
| Infra: LanguageModel + registry + OpenAI-compatible adapter + pydantic-ai | EXISTS | Provider-agnostic; 13+ providers + Ollama/LM Studio; transport injectable. Live opt-in. |
| Infra: KnowledgeGraphRepository (in-memory + SQLite) | EXISTS | Fully implemented. **Never instantiated in any composition root. No production code populates or queries the graph.** |
| Infra: ConversationRepository (in-memory + SQLite) | EXISTS | Protocol defined, stores exist. **Not wired into `ConversationContext` by default.** |
| Interface: command center (handle/route/snapshot) | EXISTS (pure, testable) | HTTP stdlib; voice and face client-side. |
| Tools / agency in the world | EXISTS (gated) | `ToolRegistry`, `ToolPolicy`, `FileSystemTool`, `EchoTool`, MCP tools. Earned agency via `Jarvis.execute` (Increment 160). Sandbox reads/writes run; external/destructive refuse at gate. |
| Forgetting / decay temporal | EXISTS (opt-in) | `DecayingWeightingPolicy` wired in Increment 113. Nothing forgets unless explicitly wired. |
| Self-observation | EXISTS | Three tendencies: evidence habit, overconfidence, prediction accuracy. Generates beliefs about Jarvis itself. |
| Meta-observation (second-order) | EXISTS | Three observers: reasoning effectiveness, retrieval quality, attention allocation. Returns `MetaKnowledge`. |

---

## 3. Interaction Trace (real)

`POST /api/say → route → handle → _say_core`:

1. **Confirm**: ≤5 words yes/no matures the previous episode's provisional answer (`confirm`).
2. **Perceive**: `perceive(text)` → `Evidence` (default `KeywordPerception`; LLM behind `PerceptionSource` protocol).
3. **Companion channel**: second pass `note_companion` → user traits. **Two LLM round-trips per turn** (code documents this cost).
4. **Context seed**: `CompanionModel` → `SYSTEM_OBSERVATION` evidence.
5. **Recall**: lexical by default; embeddings if embedder present; threshold 0.2. Since Increment 138, `DocumentMemoryRetriever` wraps recall with document hits.
6. **Reasoning** (`_reason_into`): only if no grounded belief nor strong recall → `Inference` weight 0.2. Since Increment 145, receives session `ReasoningSpan` for multi-turn continuity.
7. **Tools**: `ToolRegistry` available. Permission gating by `ToolPolicy`. External actions require approval. MCP tools available when configured.
8. **Decision**: conclusion string by confidence/stability thresholds.
9. **Persistence**: immediate to JSON/SQLite + energy update.

**Key observation**: The intent classifier routes conversation turns (GREETING/SMALLTALK/FEEDBACK/INSTRUCTION/REMEMBER/STATEMENT) without touching perception/memory/beliefs. Only STATEMENT and REMEMBER enter the cognitive path.

**Gap**: Conversation turns that are not REMEMBER/STATEMENT never influence long-term memory. Yesterday's conversation does NOT influence today's cognition unless it was explicitly a STATEMENT that formed a belief.

---

## 4. Memory Audit

### What is stored
- **Beliefs**: evidence-grounded conclusions with derived confidence. Persisted to JSON (`beliefs.json`) or SQLite (`jarvis.db`).
- **Episodes**: cognitive episode records with trigger, conclusion, confidence, stability. Persisted.
- **Companion traits**: model of the user from observed utterances. Persisted.
- **Goals**: recurring goals with progress tracking. Persisted.
- **Actions**: action-outcome beliefs for learning. Persisted.
- **Semantic memory**: patterns abstracted from multiple episodes. **Exists in code, not wired into recall by default.**
- **Knowledge graph**: nodes and edges. **Exists in code, never populated.**
- **Capabilities**: bookkeeping of acquired capabilities. Persisted.
- **Meta-knowledge**: second-order observations about cognitive processes. Exists.
- **Episode trace**: provenance trail of cognitive events. Persisted (JSONL + SQLite).
- **Conversation turns**: **Protocol exists, stores exist, not wired by default.**

### Where stored
JSON files (file-backed twin) or SQLite (transactional twin via `Jarvis.database()`).

### How retrieved
`MemoryRetriever.recall()` gathers candidates from:
- World beliefs (existing beliefs relevant to query)
- Episodes (past cognitive episodes)
- Companion traits (user model)
- Goals
- Documents (`MemoryKind.DOCUMENT`, since Increment 138)

**NOT retrieved**: Semantic memories, knowledge graph nodes, conversation turns, meta-knowledge.

### How what to remember is decided
Every percept is attached as `Evidence` to a `Belief`. Beliefs form when evidence accumulates. No explicit "what to remember" gate — everything that is perceived becomes evidence.

### How what to retrieve is decided
Token overlap / cosine similarity (lexical/embedding). Threshold 0.2. No temporal, relational, or structured queries.

### Episodic memory
`EpisodeRecord` captures trigger, kind, confidence, stability, conclusion. Persistent.

### Semantic memory
`SemanticMemory` entity exists with repository protocol, SQLite and in-memory stores. Abstraction service (`abstract_patterns`) exists. **Not wired into cognitive loop or recall.**

### Working memory
`ConversationContext` — in-memory deque (capacity 12). Session-scoped `ReasoningSpan` for multi-turn threads.

### User context
`CompanionModel` — flat traits from observed utterances. Persisted.

### Beliefs / confidence
Structurally derived via `derive_confidence()`. No setter. Formula: `supporting / (supporting + contradicting + 1)`. Never reaches 1.0.

### Belief update
Evidence added via `belief.add_evidence()`. Confidence re-derived from all evidence. Contradictions recorded as first-class events.

### Forgetting
Opt-in `DecayingWeightingPolicy` (half-life clock). Nothing forgets unless explicitly wired.

### Contradiction handling
Contradicting evidence is explicit. Belief confidence drops. Contradictions are visible in `BeliefExplanation`. Never silently overwritten.

### Duplicate evidence
**No deduplication.** Identical evidence can be added multiple times, increasing confidence. This is a design choice (each observation counts independently) but could be exploited.

---

## 5. Reasoning Audit

Jarvis **reasons** in a domain-specific sense, not just text generation:

- **Cognitive episodes** with state machine lifecycle (`CREATED→REASONING→REFLECTING→DECIDING→COMPLETED/FAILED`).
- **Competing hypotheses** (`HypothesisSet`) that coexist without forced resolution.
- **Falsation** via `Challenge` stage — leading hypothesis's temporal stability flagged if resting on narrow time window.
- **EvidenceRequest** names concrete evidence gaps.
- **`ExecutiveController._reflect`** records genuine review notes (contested/well-grounded/thin). Changes nothing about the belief — only provenance.
- **ReasoningSpan** carries multi-turn threads across turns with deterministic lifecycle.

**Limitations:**
- The reflective cycle (`reflect_cycle`) runs all 7 stages but each is a separate function call — there is no feedback loop where one stage's output gates the next.
- `observe_evidence_habit` changes decision *text* ("I tend to conclude without sufficient evidence") but does not actually demand more evidence before concluding. It is a belief about Jarvis, not a behavioral change.
- Meta-observation produces `MetaKnowledge` statements but these do not feed back to alter reasoning strategy, attention allocation, or retrieval behavior. They are observations, not adaptations.

**Distinction**: The reasoning architecture is real (domain state machine, evidence-derived confidence, falsation). But the learning/adaptation layer is narratively rich and mechanically thin.

---

## 6. Tools / Agency Audit

**Genuinely safe architecture:**

- `ToolRegistry` holds all available tools.
- `ToolPolicy` gates by `PermissionLevel`: `EXTERNAL_ACTION` requires approval.
- Permission levels: read, write, external action, destructive.
- No bypass path found.
- `Jarvis.execute` (Increment 160) performs material directives through the same gated registry.
- Sandbox reads/writes run; external/destructive acts refuse honestly at the gate.
- MCP tools available when configured (`JARVIS_MCP_CONFIG`), all gated as `EXTERNAL_ACTION`.

**Available tools:**
| Tool | Exists | Works | Permissions | Reversible |
|------|--------|-------|-------------|------------|
| FileSystemTool | Yes | Yes | project roots only | Yes (write) |
| EchoTool | Yes | Yes | none | Yes |
| MCP tools | Yes | Yes (when configured) | EXTERNAL_ACTION | depends |
| Calendar CRUD | Yes | Yes | domain seam | Yes |
| Notes CRUD | Yes | Yes | domain seam | Yes |
| Task scheduler | Yes | Yes | domain seam | Yes |
| Mail (IMAP/SMTP) | Yes | Yes | domain seam | Yes |
| Documents | Yes | Yes | domain seam | Yes |
| Web (Agent-Reach) | Yes | Yes | EXTERNAL_ACTION | read-only |
| Deep research (SearXNG) | Yes | Yes | EXTERNAL_ACTION | read-only |
| Model compare | Yes | Yes | EXTERNAL_ACTION | read-only |
| Speech (Whisper) | Yes | Yes | domain seam | read-only |

**Assessment**: The agency architecture is the strongest part of the system. Permission gating is real, earned, and reversible. No hidden bypasses.

---

## 7. Model Layer Audit

```
Jarvis → LanguageModel (Protocol) → registry → provider
```

- Provider-agnostic. Zero coupling to any SDK in domain code.
- `OpenAiCompatibleModel` supports 13+ providers (OpenAI, Groq, Grok, DeepSeek, Kimi, Mistral, Perplexity, OpenRouter, Together, NVIDIA NIM, Ollama/LM Studio, `openai-compatible` by `base_url`).
- `PydanticAiModel` (opt-in, `pip install jarvis[live]`) drives same model through Pydantic AI Agent behind the same seam.
- Live call is opt-in; default is `ScriptedModel` (offline, deterministic).
- Secrets only in env/`.env`, per-provider, write-only.
- Provider guardrails (Increment 157): refusal → honest silence.
- Instrumentation (Increment 156): per-call accounting, `provider_stats()`.
- Embeddings independent of chat provider (`JARVIS_EMBED_*`).

**Assessment**: Clean, swappable, well-gated. The model layer is architecturally correct.

---

## 8. Testing Audit

**1647 tests passing, 3 skipped, 21.84s.** All deterministic and offline.

### Coverage by area
| Area | Coverage | Notes |
|------|----------|-------|
| Domain entities | Strong | Belief, Confidence, Evidence, Hypothesis, SemanticMemory, KnowledgeNode, KnowledgeEdge, MetaKnowledge all tested. |
| Cognitive services | Strong | Association, reflection, curiosity, action_advisor, goal_reflection, self_observation, hypothesis_generation, abstraction, meta_observation all tested. |
| Executive | Good | `ExecutiveController` lifecycle tested. |
| Infrastructure stores | Good | JSON, SQLite, in-memory stores all tested. |
| Command center | Moderate | `handle`, `route`, `snapshot` tested socket-free. |
| Nervous system | Weak | Mostly smoke tests. |
| server.py | Weak | Binding only (opt-in smoke). |
| End-to-end | Present | `test_examples.py` — 6 real e2e examples. |

### Missing tests
- **Adversarial testing**: No tests for malicious input, injection, or abuse of the tool registry permission model.
- **Concurrency**: No tests for multi-threaded access to stores.
- **Edge cases in persistence**: No tests for corruption recovery, partial writes, or schema migration.
- **Live provider integration**: No integration tests with real API calls (by design — D8).

### Test quality
- Invariant coverage is good: confidence derivation, state machine transitions, permission gating all have dedicated tests.
- The test suite is the project's strongest quality signal.

---

## 9. Problems (Critical)

### P0 — Knowledge graph is dead code
`KnowledgeNode`, `KnowledgeEdge`, `KnowledgeGraphRepository`, `InMemoryKnowledgeGraphStore`, `SqliteKnowledgeGraphStore` are fully implemented and tested but **never wired into any cognitive path**. No code in `curiosity.py`, `jarvis.py`, `executive/`, or any service imports or uses the graph. This is ~400 lines of production code and ~300 lines of tests that serve no operational purpose.

### P0 — Conversation persistence is unwired by default
`ConversationRepository` protocol exists, `InMemoryConversationStore` and `SqliteConversationStore` exist, and `ConversationContext` accepts an optional repository. But the default composition does not inject one. **Yesterday's conversation does not influence today's cognition.** The system has no memory of past conversations unless explicitly wired at composition time.

### P0 — Semantic memory is not in recall
`SemanticMemory` entity, repository, abstraction service, and SQLite store all exist. But `memory_candidates.py` does not include semantic memories as candidates. `MemoryRetriever.recall()` never surfaces them. The abstraction pipeline exists but feeds nothing.

### P1 — Self-observation is narration, not adaptation
`observe_evidence_habit` creates a Belief with statement "I tend to conclude without sufficient evidence." This belief is observable via `introspect()`. But it does not change behavior: the next episode still concludes at the same threshold. The self-model changes how Jarvis *explains* its conclusions, not how it *makes* them.

### P1 — Meta-observation does not close the loop
`observe_reasoning_effectiveness`, `observe_retrieval_quality`, `observe_attention_allocation` produce `MetaKnowledge` instances. These are stored and observable. But they do not feed back to alter reasoning strategy, retrieval weighting, or attention allocation. They are observations without adaptation.

### P1 — Reflective cycle stages are not gated
`reflect_cycle()` calls `connections → reflect → hypothesise → challenge → learn → act` sequentially. Each stage runs unconditionally. There is no feedback where one stage's output (e.g., no interesting connections found) gates whether subsequent stages run. The cycle is a pipeline, not a self-regulating loop.

### P2 — Duplicate evidence inflates confidence
No deduplication exists. Identical evidence can be added to a belief multiple times, artificially increasing confidence. The formula `supporting / (supporting + contradicting + 1)` treats each piece independently. This is a design choice (each observation counts) but is exploitable.

### P2 — Double LLM round-trip per turn
Each conversation turn requires two LLM calls: one for perception and one for companion trait extraction. This doubles latency and cost for every interaction.

### P3 — No temporal pattern detection
Temporal stability and evidence decay work well. But there are no historical state queries, no temporal pattern detection, no "what did you believe at time T?" capability beyond what timestamps on individual evidence pieces provide.

---

## 10. Technical Debt

1. **Dead code**: Knowledge graph (~700 LOC production + ~300 LOC tests) is implemented but never wired.
2. **Unwired persistence**: Conversation persistence exists but is not the default.
3. **Semantic memory not in recall**: Abstraction pipeline exists but feeds nothing.
4. **Self-observation → no behavioral adaptation**: Beliefs about habits are recorded but do not change thresholds.
5. **Meta-observation → no feedback loop**: Observations about cognitive processes do not alter those processes.
6. **No evidence deduplication**: Confidence can be artificially inflated by repeated identical evidence.
7. **Double LLM round-trip**: Two model calls per turn when one would suffice.
8. **Exact string matching for belief identity**: Semantic matching not yet implemented (D11).

---

## 11. Gap Analysis vs. Vision

| Capability | Status |
|---|---|
| Build/update beliefs with evidence | **IMPLEMENTED** |
| Derived confidence + explicit contradictions | **IMPLEMENTED** |
| Competing hypotheses without forced resolution | **IMPLEMENTED** |
| Episodic/companion/goal memory + persistence | **IMPLEMENTED** (JSON + SQLite) |
| LLM swappable / model independence | **IMPLEMENTED** |
| Recall by meaning (embeddings) | **IMPLEMENTED** (lexical fallback) |
| Reasoning multi-step verifiable | **PARTIAL** (falsation yes; result verification limited) |
| Reflective cycle end-to-end | **PARTIAL** (all 7 stages exist; stages not gated; no feedback) |
| Self-observation | **PARTIAL** (generates beliefs about habits; no behavioral change) |
| Forgetting / decay | **IMPLEMENTED** (opt-in) |
| Persistent provenance trace | **IMPLEMENTED** (JSONL + SQLite) |
| Tool execution / agency | **IMPLEMENTED** (gated, earned, reversible) |
| Autonomous capability acquisition (Odysseus) | **IMPLEMENTED** |
| Documents in recall | **IMPLEMENTED** (Increment 138-149) |
| SQLite persistence | **IMPLEMENTED** (Increment 150-152) |
| Persistent conversation across sessions | **PARTIAL** (protocol + stores exist; not wired by default) |
| Knowledge graph / entity relations | **PARTIAL** (fully implemented; not wired into cognitive loop) |
| Semantic memory in recall | **PARTIAL** (entity + service exist; not wired into recall) |
| Second-order reflection (meta-observation) | **PARTIAL** (observers exist; no feedback to cognition) |
| Temporal reasoning / historical queries | **PARTIAL** (stability + decay yes; no historical state queries) |
| Semantic matching for belief identity | **MISSING** (D11 — exact matching deliberate) |
| Adversarial testing | **MISSING** |
| Real instruction execution | **IMPLEMENTED** (Increment 160, gated) |

---

## 12. Priorities

### P0 — Critical foundation
1. **Wire knowledge graph into cognitive loop** or remove dead code. The current state is misleading — documented as "implemented" but functionally absent.
2. **Wire semantic memory into recall**. The abstraction pipeline exists and produces `SemanticMemory` instances that `MemoryRetriever` never sees.
3. **Wire conversation persistence by default**. Without this, the system has no cross-session memory of conversations.

### P1 — Core capabilities
4. **Close the self-observation → adaptation loop**. When `observe_evidence_habit` detects a pattern, the system should adjust its grounding threshold (via `CognitiveKnobs`) rather than just recording a belief about the habit.
5. **Close the meta-observation → feedback loop**. When `observe_reasoning_effectiveness` finds that deliberations outperform conclusions, the system should prefer `consider()` over `think()`.
6. **Gate reflective cycle stages**. If `connections()` finds nothing interesting, skip subsequent stages. The cycle should be self-regulating, not a fixed pipeline.

### P2 — Cognitive capabilities
7. **Evidence deduplication** (or at least configurable dedup policy). Prevent artificial confidence inflation from repeated identical evidence.
8. **Temporal pattern detection**. "What did you believe about X six months ago?" should be answerable from the existing episode/belief history.
9. **Semantic matching for belief identity** (beyond D11 exact matching).

### P3 — Agency
10. **Reduce LLM round-trips**. Combine perception and companion trait extraction into a single model call.
11. **Adversarial testing for tool registry**. Verify that permission gating holds under adversarial input.

### P4 — Social / personality
12. **Coherent personality layer**. Self-observation produces tendencies but no consistent behavioral signature.

---

## 13. Recommended Next Capability

**Wire semantic memory into recall.** This is the lowest-risk, highest-value next step because:
- The entity, repository, abstraction service, and stores already exist.
- The only missing piece is adding `SemanticMemory` as a candidate source in `memory_candidates.py`.
- It immediately makes the system's abstraction pipeline operational.
- It is a ~20 line change with clear test verification.

This closes the gap between "the abstraction pipeline exists" and "the system actually uses its abstracted knowledge."

---

## 14. Architectural Integrity Assessment

### What is genuinely strong
- **Epistemic invariant**: Confidence derivation is structural, not enforced by convention. No setter exists. The formula is correct and auditable.
- **Contradictions as first-class**: Contradicting evidence is explicit, visible, and never silently discarded.
- **Agency safety**: `ToolRegistry` + `ToolPolicy` + permission levels correctly separate thought, recommendation, permission, and execution. No bypass found.
- **Provider independence**: The `LanguageModel` seam is clean. No SDK leaks into domain code.
- **Test quality**: 1647 offline-deterministic tests with good invariant coverage.
- **Clean architecture**: Proper layering (domain → executive → infrastructure → interface). No business logic in the UI.

### What is genuinely weak
- **Wiring gaps**: Knowledge graph, semantic memory, and conversation persistence are implemented but disconnected. The system's documented capabilities exceed its operational capabilities.
- **Narration over adaptation**: Self-observation and meta-observation produce beliefs/observations that do not feed back to alter behavior. The system can *say* "I tend to conclude without sufficient evidence" but does not *act* on that knowledge.
- **No cross-session conversation memory**: The system forgets all conversations on restart unless manually wired.
- **No adversarial hardening**: Permission gating is architecturally correct but untested against adversarial input.

### Overall verdict
Jarvis is a genuinely well-designed cognitive architecture with real epistemic integrity. Its primary weakness is not architectural but operational: several implemented subsystems are not wired into the cognitive loop, creating a gap between what the code contains and what the system actually does. Closing these wiring gaps (P0 items) would substantially increase the system's operational capability without requiring new architectural abstractions.
