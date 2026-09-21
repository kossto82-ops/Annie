# Jarvis — AI Context

## What Jarvis is

Jarvis is a long-term cognitive companion. It is a persistent cognitive system whose primary unit is a **Cognitive Episode** rather than a chat turn.

The intended loop is:

`Experience → Perception → Interpretation → Attention → Memory → Reasoning → Reflection → Decision → Action → Outcome → Learning → Updated state`

The response is only one possible output of cognition.

## Non-negotiable principles

- Beliefs are provisional.
- Evidence is first-class and carries provenance/source/weight.
- Confidence is **derived**, never manually assigned to a belief.
- Contradictions are explicit.
- Competing hypotheses can coexist.
- Uncertainty must not be hidden by premature conclusions.
- Memory preserves evidence and state; memory is not truth.
- The LLM, when present, extracts candidate evidence; the core remains the judge.
- Providers must be swappable.
- Core tests must remain deterministic/offline.
- The system should grow through evidence and experience, not through increasingly large prompts.

## Current system

### Domain

- `CognitiveEpisode` — aggregate root and unit of cognition; carries recalled memories (from the memory
  seam), an optional inference (from the reasoning seam), consulted edges (from the knowledge-source
  seam), and goal.
- `Belief` — evidence-grounded entity. `Hypothesis` / `HypothesisSet` — competing explanations.
- `CompanionModel` — model of the companion.
- `IntentClassifier` (`domain/conversation/intent.py`) — deterministic bilingual classify of a user
  turn (GREETING / SMALLTALK / FEEDBACK / INSTRUCTION / REMEMBER / STATEMENT / ACT, Increment 160);
  short-term `ConversationContext` holds a bounded recent-turn ring (capacity 12), separate from
  long-term memory. Since Increment 167 the STATEMENT path is a real memory writer: an everyday
  ≥3-word non-question sentence becomes `USER_STATEMENT` evidence (companion channel when
  first-person), so conversation stays short-term context but its statements become durable memory
  (see "Conversation vs long-term memory" below).
- Value objects cover evidence, confidence, temporal stability, goals, actions, deliberation,
  reflection, energy, connections, state summaries, recalled memories, inferences, capabilities,
  notes, email messages, calendar events, scheduled tasks, tool specs/calls/results, retrieved
  documents, research reports, model runs, etc.
- Domain events represent episode, evidence, belief, contradiction, hypothesis, action and tool changes.

### Cognitive services

- evidence weighting (source policy + optional decay composition, Increment 113)
- reflection (genuine review stage, Increment 112), connection/association
- curiosity, hypothesis generation, action recommendation (graded stance)
- goal reflection (recurring goals / reflection effort), self-observation (3 tendencies)
- capability scout / evaluator / gap-observation (Odysseus, D37)
- knowledge source (deliberate edge consultation, D38), model compare

### Executive/core

`ExecutiveController` orchestrates the lifecycle of an episode. It stays thin; before deciding it may
**recall** (memory seam), **consult** a knowledge edge, and **reason** (reasoner seam) — each a
candidate-evidence source, never a decision-maker (D35/D36/D38).

`Jarvis` is the public composition/API surface (~110 methods). `NervousSystem` provides synchronous
event signalling. `EpisodeTrace` groups cognitive events by episode; persistent Jarvis keeps the trace
on disk (JSONL, Increment 112).

### Memory

Repositories are defined in the domain and implemented by infrastructure. In-memory and JSON-backed
stores exist, plus a JSONL episode trace; `Jarvis.persistent(directory)` wires durable JSON persistence
for all stores (incl. capabilities, refutations, trace).

**Recall seam** (`MemoryRetriever` + `RecalledMemory`): a deterministic lexical adapter is the offline
default; an embedding-backed retriever (recall by meaning, Increment 108) is opt-in via
`Jarvis.enable_embedding_recall(embedder)`. Since Increment 168 the lexical adapter itself ranks every
durable candidate by meaning: one domain scorer `relatedness = max(surface_overlap, concept_relevance)`
(bilingual `CONCEPT_MAP`, paraphrase and ES↔EN), so the meaning channel works with no embeddings at all.
`SEMANTIC` is no longer a special case — it is just another durable candidate, winning only as a tie-break
at exact relevance (the distilled pattern outranks the concrete copies it generalizes over). Short-term
conversation turns stay surface-only: matched lexically, never echoed as answers. Recall supplies *stance*
only, never belief-confidence (memory is not truth, Vision §22). Since Increment 138 both paths are wrapped
by `DocumentMemoryRetriever`, which folds matching companion **documents** into the recalled set as
`MemoryKind.DOCUMENT` (`DocumentHit` name/snippet/relevance; lexical match; snippets never quote opaque
binary bytes).

**Reasoning seam** (`Reasoner` + `Inference`): `LlmReasoner` proposes a provisional answer; folded in as
the weakest `EvidenceSource.INFERENCE` (0.2) so an unconfirmed answer is held faintly and matures only
via `confirm()` (learning loop, Increment 110). Since Increment 138 the reasoner receives the short-term
recent turns (`ConversationContext`) in **both** the conversational (`say`/`reason`) and episode
(`think(…, conversation=…)` → `executive run` → `_reason_into`) paths; a session `ReasoningSpan`
(Increment 145) carries the reasoning threads across turns with a deterministic lifecycle (model proposes
content only). `Jarvis.reason_stream` records the span only on a completed stream.

**Conversation vs long-term memory**: `MemoryKind.CONVERSATION` turns are surface-only candidates —
matched lexically, never recited as answers; long-term recall (beliefs, episodes, semantic patterns,
graph, documents) is what meaning should reach (Increment 167). Statements cross into memory deliberately:
`_remember_statement` stores an everyday ≥3-word non-question sentence as `USER_STATEMENT` evidence
(`EvidenceSource.USER_STATEMENT`, weight 1.0, persisted) — and through the companion channel when
first-person — so a follow-up question after a restart is answered from memory (Increment 167).

**Change of mind** (Increment 169): `Belief.revise()` makes a corrected decision first-class — the new
stance supersedes the earlier one, the superseded statement moves into the belief's `precedents` archive
and is never recalled as current, and `BeliefRevised` flows through the nervous system. Companions:
`companion.revise_companion(...)` / `Jarvis.revise_companion(trait, evidence, replaces=…)`. Resolution
survives restarts on all three store families (in-memory, JSON, SQLite).

**Evidence-request writer** (Increment 170): an episode that is COMPANION-origin, FULL-attention,
question-shaped, and carries no evidence leaves a transient `EvidenceRequest` in the unresolved store so
curiosity can return to it; `is_question_shape` is the public alias (in `executive_controller.py`,
reusing `_QUESTION_CUES` + trailing `?`). The write is epistemically inert — no evidence, no belief.

**Forgetting** (`DecayingWeightingPolicy`, opt-in): evidence contribution fades with a half-life clock —
nothing forgets unless a decaying policy is explicitly wired in (Increment 113). The
`forget()`/`identify_forgetting_candidates()` consolidation services exist and are tested (Phase 11) but
nothing schedules them in the running system.

### Perception / LLM

- `PerceptionSource` (text → evidence), `CompanionPerceptionSource` (utterance → traits about the
  companion), `SpeechPerceptionSource` (speech → evidence).
- `LanguageModel` is provider-agnostic; `LlmPerception` uses it to extract candidate evidence, not to
  decide beliefs. `OpenAiCompatibleModel` + the provider registry support many remote and local
  endpoints (OpenAI, Groq, Grok, DeepSeek, Kimi, Mistral, Perplexity, OpenRouter, Together, NVIDIA NIM,
  local Ollama/LM Studio, `openai-compatible` by `base_url`). Provider `pydantic` (opt-in,
  `pip install jarvis[live]`) drives the same model/endpoint through a Pydantic AI `Agent` behind the
  same seam; its perceiver asks for structured `PerceptionClaim`s (Vision §38), reasoner/renderer stay
  plain-text. The model-driven `PydanticAiTaskAgent` is a `TaskAgent` whose tool
  sequence is chosen by a Pydantic AI `Agent` over the sandboxed `ToolRegistry`: the
  registry still holds the gate (permission/approval) and the trace, and outcomes are
  narrated from recorded calls, never the model's closing words (D6/Vision §37).
  `build_task_agent` (Phase 3) uses this executor for decided multi-step tasks when a
  live `pydantic` provider is configured at the composition root, and falls back to the
  deterministic decided-script `ToolRegistryTaskAgent` otherwise (delegation stays
  behind the `TaskAgent` seam; cognition stays in the core). Phase 5 added the
  evaluation pieces: `Usage` token accounting on the pydantic adapters, a decided-script
  delegation fallback on a provider outage, and reasoner-level streaming (`infer_stream`
  / `Jarvis.reason_stream`, which advances the reasoning span only on a completed
  stream). Phase 4 (part 1) added live instrumentation: `InstrumentedLanguageModel` /
  `InstrumentedTaskAgent` wrappers and a shared `InstrumentationStore` observe each
  observable call (outcome, duration) behind the same seams, surfaced through
  `Jarvis.provider_stats()` and the command center's `provider` snapshot block.
- `env_settings` resolves providers/keys from `JARVIS_LLM_*` (keys per provider `JARVIS_LLM_KEY_<PROVIDER>`,
  models per provider `JARVIS_LLM_MODEL_<PROVIDER>`); the command center can persist them to `.env`
  (write-only secret discipline). Embeddings use `JARVIS_EMBED_*` (independent of the chat provider).
- A live API call is opt-in; secrets belong in environment/configuration, never source control. The
  reasoner and response renderer build from the same provider registry.

### Capabilities (Odysseus + edges)

`Capability` is bookkeeping; the live side is a `CapabilityProvider` at the edge (D7/D37).
`Jarvis.can_do(name)` is true only when a capability is *acquired* and live-backed. Recognised needs are
ordinary beliefs whose confidence is derived from evidence; autonomy is earned (deliberate acquire/reject).
Gap detection (`capability_gap_observation`) can self-initiate needs from recurring failure subjects and
auto-scout in the reflective cycle.

Edge seams (domain protocol → infrastructure adapter, injectable io/net, offline default):
web internet (`ExternalSource`/Agent-Reach), deep research (`ResearchSource`/SearXNG), blind model
comparison (`ModelComparator`), tool registry + policy (`ToolRegistry`), notes (`NotesStore`), mail
(`MailBox`/real IMAP-SMTP), calendar (`CalendarStore`/local + Google), tasks (`TaskScheduler`),
agent delegation (`TaskAgent`), speech perception (`SpeechPerceptionSource`), and files/documents
(`DocumentStore` over bytes + `LocalDocumentStore`, flat name-keyed; `JARVIS_PROJECT_ROOTS` feeds the
`FileSystemTool` `project:` roots as a tool edge). Material actions can be
delegated to an edge agent behind these seams, never cognition (revised D1).

### Command Center

Local browser UI served by the stdlib HTTP server. The browser handles voice input/output, the visual
face/sphere, and the capability/tool panels. Python remains the cognitive core.

`handle`, `route`, and `snapshot` are pure/socket-free and tested independently from the server. Surface
commands: `say` (with streaming + reasoning panel), `explain`, `reflect`, `wonder`, `introspect`,
`perceiver` (switch provider/model/key), `capability` (notice/list/acquire/reject), `tool` (list/run),
`external` (read/search web), `research`, `compare`, `documents` (list/read/save/remove/search), plus the
notes/mail/calendar/tasks delegation.
`_say` routes on intent first (Increment 114): questions never touch perception/beliefs; since
Increment 167 a STATEMENT intent (an everyday ≥3-word non-question sentence) is stored as
`USER_STATEMENT` evidence through `_remember_statement` and persisted (companion channel when
first-person), so a follow-up question after a restart answers from memory.

## Reflective cycle

The implemented autonomous reflective cycle is:

`Remember → Connect → Reflect → Hypothesise → Challenge → Learn → Act`

`reflect_cycle()` runs all seven stages end to end and is self-triggered by curiosity (un-mined
load-bearing patterns). The cycle is evidence-grounded, revisable, auditable, and implemented inside the
core rather than as an external agent wrapper. The Reflect stage records genuine review notes
(`EpisodeReflected`), failures leave `EpisodeFailed`, and the trace persists across restarts (P0/P1,
Increments 111–112).

## Current state snapshot

- Reflective cycle: complete (all seven stages) and traceable.
- Conversation intent layer + short-term context: implemented.
- Recall by meaning (lexical `relatedness` scorer with a bilingual concept map — the offline default —
  plus opt-in embedding retrieval) and identity-aware/canonical-topic answers: implemented.
- Statements become memory (≥3-word non-question sentences persist as `USER_STATEMENT` evidence) and a
  changed mind is resolved (`Belief.revise()`, precedents archive): implemented.
- Provisional reasoning + learning loop (confirm) + decay/forgetting *services* (opt-in, not scheduled
  in the running system): implemented.
- Episodic, belief, companion, action and goal memory: implemented; all persistent (crash-safe JSON).
- LLM abstraction/registry/live providers + self-diagnosing errors: implemented; live is opt-in.
- Capabilities: acquisition model + scout + edge providers + 12+ catalog entries (web, research, compare,
  tools, notes, mail, calendar, tasks, agent, speech seam).
- Command Center: implemented (voice, sphere/face, streaming, reasoning panel, capability/tool panels,
  Documentos panel with list/search/read/write/remove).
- Documents in recall: `MemoryKind.DOCUMENT` + `DocumentHit`, lexical `search_documents`, wrapped recall
  (semantic + documents), and document chips in `say` replies (read-through on click); folder-aware names
  (Increment 142), recorded ownership per file — `DocumentOwner` attribution + stored/updated timing in
  `DocumentMeta`, `documents info`, `[jarvis]` tags in list, `owner` on save (Increment 148) — and
  chat editing via `documents edit` behind a `DocumentEditor` proposal seam (Increment 149).
- Cognition thresholds are live-tunable: one `CognitiveKnobs` VO (grounded/insight/max_goal_reflections)
  injectable at `Jarvis(...)`, runtime-swappable, exposed as a `tunables` action + sliders (Increment 141).
- The per-belief weighting policy is root-injectable: `Jarvis(default_belief_policy=...)` /
  `set_belief_policy(...)` override the source policy every fresh belief is born with (goals, actions,
  companion traits, self-observed habits); the swap reaches subsequent creations only and is inherited by
  `Jarvis.persistent()` (Increment 144).
- Deep multi-turn reasoning: a session `ReasoningSpan` (`domain/reasoning/reasoning_span.py`) carries the
  reasoning threads across turns; the thread lifecycle is deterministic (open/revise, move-on, seal on
  confirmation, dispute on correction), the model only proposes content, and `LlmReasoner` renders the
  threads into the prompt (Increment 145).
- Temporal stability for hypotheses: hypotheses derive the same span-based `TemporalStability` as
  beliefs; the `Challenge` narration flags a narrow-time-window leader as possible overfitting without
  touching its strength, ranking or ties (Increment 146).
- One `CognitiveEpisode` shape (Increment 147): the episode holds ONE conclusion-model — a `Belief` or a
  `HypothesisSet` — in a single slot; both ride the same lifecycle, the same event boundary, and
  `kind` (CONCLUSION/DELIBERATION) is derived from that conclusion, never painted by the caller.
- Document ownership (Increment 148): `DocumentOwner` (companion vs jarvis-generated) + stored/updated
  timing live in a `DocumentMeta` snapshot per file, persisted out-of-band in a reserved `_jarvis-meta.json`
  index that `list`/`search` never surface; `write_document` takes `owner`, `document_meta()` is honest
  (`None` when a file predates provenance tracking), and the command center answers "whose is this?"
  via `documents info` while `list` tags generated files.
- Chat editing of documents (Increment 149): a `DocumentEditor` seam (`domain/retrieval/document_editor.py`)
  proposes a complete rewrite from a free-form instruction (`documents edit`); offline it declines honestly,
  an LLM-backed editor rides the `LanguageModel` seam, and Jarvis applies the proposal preserving owner,
  refuses binary, and frames the change from the real diff.
- A real database behind the repository contracts (Increment 150, D10): `Sqlite*Store` implementations
  (`infrastructure/sqlite_*_store.py`) back the belief/episode/capability/refutation Protocols with SQLite's
  transactional durability, composed by `build_sqlite_repositories`/`SqliteRepositories` into one `jarvis.db`
  and reached through `Jarvis.database(directory)`; the command center's composition root (`create_jarvis`)
  adopts it when a `home` is set. Same evidence-derived rehydration as the JSON stores.
- SQLite across the edge seams (Increment 151): `SqliteCalendarStore` / `SqliteNotesStore` /
  `SqliteTaskScheduler` back the calendar/notes/task-scheduler Protocols in their root's `jarvis.db`; the
  `JARVIS_*_ROOT` builders (`calendar_store`/`notes_store`/`task_scheduler`) serve them, while the io-injectable
  `Local*` adapters stay for offline tests and direct use (D8).
- Decision provenance joined the database (Increment 152): `SqliteEpisodeTrace` keeps the trace in a seq-ordered
  `trace_events` table in the same `jarvis.db` as the memory, so `Jarvis.database()` leaves no memory surface
  file-backed (the user's `docs` bytes and the `.env` config are the only deliberate files).
- A live STT backer (Increment 154): the ear seam (`SpeechPerceptionSource`) gains `transcribe_audio`;
  `WhisperTranscriber` drives any OpenAI-compatible `/audio/transcriptions` endpoint (openai / groq / custom
  base_url) with an injectable transport (D8), `Jarvis.transcribe(audio)` and `POST /api/speech/transcribe`
  deliver raw audio, and the command center picks the ear from `JARVIS_STT_*` (`speech_perception_from_env`);
  the browser Web Speech default and the pure `SpeechPerceptionSource` contract are untouched.
- Live-provider instrumentation (Increment 156, pydantic-ai Phase 4 part 1): `provider_stats`
  (`provider_stats.py`) — `ProviderSnapshot`/`ProviderCall`/`InstrumentationStore` plus an in-memory
  default collector — is fed by `InstrumentedLanguageModel` / `InstrumentedTaskAgent` wrappers over any
  adapter (scripted/OpenAI-compatible/pydantic alike), wired only at the `create_jarvis` composition
  root around the delegated task agent, and surfaced as `Jarvis.provider_stats()` and the command
  center's `provider` snapshot block. Bookkeeping only; it never influences a reply or decision.
- Provider guardrails (Increment 157, pydantic-ai Phase 4 part 2a): `guardrail.py` turns a provider
  *refusal* — `finish_reason='content_filter'` or a whole-phrase decline text, EN/ES — into honest
  silence (`""`) at the seam (§37, second enforcement point beside the failure path). `OpenAiCompatibleModel`
  guards `complete` and `stream` (SSE `content_filter` ends the stream; already-flowed deltas are
  forward-only); `PydanticAiModel` guards the serialised reply and wires the ≥2.41
  `RaiseContentFilterError` capability when present (feature-detected, no dependency).
- MCP client direction (Increment 158, pydantic-ai Phase 4 part 2b): `mcp_tools.py` consumes a live MCP
  *server's* tools into Jarvis's own gated `ToolRegistry` — a sync `McpTransport` seam (offline-fakeable),
  `PydanticAiMcpToolset` as the lazy live backer (async↔sync bridge), `McpTool` forwarding runs, and
  `register_mcp_tools`/`register_mcp_config`/`build_mcp_toolset` wiring namespaced tools (`repo.status`).
  Every MCP spec is `PermissionLevel.EXTERNAL_ACTION`, so approval is required and each call is an
  observed `ToolCall`. `JARVIS_MCP_CONFIG` adds the server's tools inside `build_sandboxed_registry`;
  absent `pydantic-ai` or a broken edge returns `()`/`None` (offline Jarvis untouched).
- Live STT level 2 in the console (Increment 159): the `speech` snapshot block (`provider` / `model` /
  `live`) is honest self-description — `SpeechPerceptionSource` now carries `provider`, `model`, and
  `can_hear_audio` (echo `False`, Whisper backers `True`). When a live ear is wired the console mic
  records (`getUserMedia` + `MediaRecorder`, webm) and POSTs one blob to `/api/speech/transcribe`
  which feeds `converse()`; the two mic paths are mutually exclusive (`serverEar` guards), Web Speech
  staying the offline default. Streaming/VAD remains unwired (one blob per hold).
- Reasoning/provenance visualisation: implemented (Increment 91 panel).
- Relation-aware graph recall & retrieval-strategy selection (Increment 166): the knowledge source can
  reach a belief connected to the query by traversing `GraphNode`s (relation-aware recall, `_recall_graph_into`
  plus `GraphNode.path_between`), and `ExecutiveController` selects a retrieval strategy per query —
  ROUTED_LEXICAL / SEMANTIC / GRAPH / EMBEDDING (`_retrieve_with_strategy`) from live `strategy_stats`
  (`RetrievalStrategyStats`), self-feedback recordable via `record_retrieval_outcome`.
- Statements as real memory (Increment 167): see "Conversation vs long-term memory" above; end-to-end
  tests store a first-person statement, restart on a fresh `Jarvis.database()` handle, and answer a
  follow-up question from memory.
- Recall by meaning (Increment 168): one scorer `relatedness = max(surface_overlap, concept_relevance)`
  ranks every durable candidate; the bilingual `CONCEPT_MAP` bridges paraphrase and ES↔EN; the SEMANTIC
  special case in retrieval is gone (tie-break only).
- Change-of-mind resolution (Increment 169): see "Change of mind" above; superseded statements are never
  recalled as current on any store family.
- Episode evidence-request writer (Increment 170): see "Evidence-request writer" above; a
  COMPANION-origin, FULL-attention, question-shaped, evidence-less episode leaves a transient
  `EvidenceRequest` in the unresolved store for curiosity to return to.

### Architectural Audit (Phases 0-5)

The deep architectural audit is complete. All 5 phases implemented:

- **Phase 0** — God Object Split: `jarvis.py` split into 7 focused modules (cognitive, companion, goals, actions, curiosity, introspection, persistence)
- **Phase 1** — Semantic Memory: `SemanticMemory` entity, `semantic_events.py`, abstraction service, `SemanticMemoryRepository`, `SEMANTIC` in `MemoryKind`
- **Phase 2** — Temporal Reasoning: belief timestamps, `history_in_range`/`history_about`, temporal filtering in retrievers
- **Phase 3** — Knowledge Graph: `KnowledgeNode`/`KnowledgeEdge`, `NodeKind`, `KnowledgeGraphRepository`, BFS traversal, `path_between`
- **Phase 4** — Persistent Conversation: `PersistedTurn`, `ConversationRepository`, `CONVERSATION` in `MemoryKind`, SQLite stores
- **Phase 5** — Second-Order Reflection: `MetaKnowledgeKind`, `MetaKnowledge` entity, `meta_observation` service (reasoning effectiveness, retrieval quality, attention allocation), curiosity integration

### Post-Audit Implementation (Phases 0-11, 2026-09-13)

The post-audit implementation wired existing systems into the cognitive loop:

- **Phase 0** — Baseline: 1647 tests, ruff clean, pyright strict
- **Phase 1A-C** — Wire What Already Exists: semantic memory + conversation → recall, conversation persistence, evidence deduplication
- **Phase 2** — Close the Learning Loop: `adapt_knobs_from_self_observation()` wired into ExecutiveController.run(), 7 tests proving behavioral change
- **Phase 3A** — Temporal Reasoning: `belief_timeline()`, `what_changed()`, `belief_snapshot_at()` in temporal_reasoning.py, 10 tests
- **Phase 4** — Unresolved Items: codebase clean (zero TODOs/FIXMEs/HACKs)
- **Phase 5A** — Decision History: `EvidenceSnapshot`, `reflection_note`, `evidence_snapshot` on EpisodeRecord, 8 tests
- **Phase 6A** — Reflection Gating: `_should_reflect()` on ExecutiveController, 6 tests
- **Phase 7A** — Meta-Knowledge Feedback: `adapt_from_meta_observation()` wired into run(), 5 tests
- **Phase 8** — Temporal Pattern Detection: `TemporalPattern` enum, `detect_pattern()` in temporal_reasoning.py, 6 tests
- **Phase 9** — Knowledge Graph Integration: `knowledge_graph` parameter on ExecutiveController, entity extraction in `_remember()`, 3 tests
- **Phase 10** — Proactive Cognition: `detect_pattern()` wired into `feel_curious()` cascade, 2 tests
- **Phase 11** — Memory Decay and Consolidation: `forget()` on BeliefRepository, `identify_forgetting_candidates()` in memory_consolidation.py, 7 tests
- **Phase 12** — Fallback Provider: `FallbackLanguageModel` with automatic failover, `backup_settings_from_env()`, factory `model_override` param, web search routing fix, dashboard capability count honesty

### Cognitive attention repair (Increments 163-165, 2026-09-15)

Increment 162 (semantic & attention development loop) shipped dirty to the type gate; the
repair series merged it into the local line and closed the remediation plan A-E:

- **Canonical topic identity**: `domain/services/topic_resolution.py` groups episodes by
  concept signature (`signature_of`, `resolve_episodes`, `topic_id_of`) — never by raw
  trigger; `topic_id` = `" > ".join(sorted(signature))` (e.g. `DELIVER > FAIL`), with the
  most recent trigger kept as display-only `representative`. Empty signatures never fuse
  (the `∅==∅` merge bug is guarded; single-concept topics never absorb).
- **Attention on canonical topics, external-only**: `attention_priority` regroups by
  canonical topic, filters `TriggerOrigin.COMPANION` before resolution, and fixes recency
  direction (`last_index/(window-1)`, most recent = 1.0).
- **Curiosity provenance survives persistence**: `target_topic_id` (and the impulse's
  `representative_trigger`) ride `EpisodeRecord` → `CognitiveEpisode` → `CuriosityImpulse`
  and the JSON/SQLite stores; `wake()` anchors the canonical topic and narrates its
  representative; `pursue()` runs that real trigger with `origin=CURIOSITY`, so internal
  cognition cannot re-rank attention by echoing itself.
- **External-only consolidation + neutral evidence**: `abstract_patterns`/consolidation feed
  on `COMPANION` episodes only. New `Evidence.is_neutral` — valence-less episodes
  contribute undirected evidence that `derive_confidence`/`derive_stability` skip (never a
  contradiction) and that emits neither `SemanticMemoryReinforced` nor `Contested`.
- **Vocabulary/cache edges**: negation is parity-counted (odd # of markers inverts);
  ~30 irregular verbs added to `CONCEPT_MAP`; the trigger-signature memo is a bounded
  `lru_cache(maxsize=1024)` with public `clear_signature_cache()`/`signature_cache_info()`.
- **Gates**: `consolidate_semantic_memories`'s `store` typed via `SemanticMemoryRepository`;
  new public seams (`ExecutiveController.memory_retriever` / `.semantic_memory_store`,
  `DocumentMemoryRetriever.base`) let tests stop touching privates. **pyright strict 0
  errors across the whole repo, ruff clean, 1885 passed** at HEAD (`0a6a73e`).

### Audit remediation (2026-09-14, `docs/claude/REMEDIATION_PLAN.md` → `REMEDIATION_REPORT.md`)

- **Types**: pyright strict 0 errors with no suppressions or scope cuts (was 461: facade/interface cross-module private use → public seams, COMMANDS-table router composition, consolidated duplicate helpers, deleted dead forwarders).
- **Offline suite**: full suite deterministic in ~100 s (was: hang in `test_google_calendar.py` — the snapshot read live events through a wired Google store; snapshots never read remote stores now, D16; hostile-transport regression guard added).
- **Knobs**: single authoritative copy in the executive (D17); energy unified in `EnergyLedger`.
- **Epistemics**: default-ON `same_observation` identity across Belief/Hypothesis/SemanticMemory (D15); production runs/episodes carry provenance.
- **Learning**: justified adaptations persist as `LearnedState` (JSON + SQLite, both factories); meta-knowledge re-derives from persisted history.
- **Continuity proven**: conversation hydration (bounded ring + JSON store), semantic abstraction lifecycle, graph traversal reads (`GRAPH_NODE`, KEPT AND WIRED), `why_decision` + temporal reconstruction APIs, unresolved-item lifecycle, gated `reflect_cycle` (reports its path), adversarial suite.
- **Deferred with reasons**: bounded proactive wake loop (needs shutdown-safe scheduling) and strategy-selection consumption (no automatic think-vs-consider router exists).

## Known technical debt / future directions

- Reset the audit gates at HEAD: 5 ruff errors + 44 pyright errors (all in newer tests; see STATUS.md). *(DONE — Increment 135: ruff clean · pyright strict 0 errors.)*
- Semantic matching for belief/connection identity: resolved forward — since Increments 163-165 belief
  identity is **canonical-topic-anchored** (`topic_resolution.py`: episodes group by concept signature,
  never raw trigger, empty signatures never fuse) and since Increment 168 recall reaches the same memory
  by meaning (relatedness + bilingual concept map). Still open: embeddings are not used for the *identity*
  path, and consolidation/abstraction deliberately feeds on COMPANION-origin episodes with neutral
  evidence only.
- A real SQLite DB now backs the repository contracts (`Jarvis.database()`, Increment 150) and the command
  center's composition root uses it; the JSON stores / `Jarvis.persistent()` remain as the file-backed twin;
  `TemporalStability` count/recency weighting beyond the opt-in decay policy. Decay/forgetting services
  exist and are tested but nothing schedules them in the running system.
- Speech: a live STT backer (Increment 154) is wired and used in the console (Increment 159);
  streaming/VAD mic delivery to the server ear remain open.
- Real instruction execution (earned agency, Increment 160): a material directive in conversation is
  classified as `ConversationIntent.ACT` and performed through `Jarvis.execute` behind the same
  sandboxed ToolRegistry without approval — sandbox reads/writes run, external/destructive acts
  refuse at the gate; without an executor (no `JARVIS_AGENT_ROOT`), Jarvis declines honestly. A live
  `pydantic` provider turns free text into the multi-step loop; offline, only the decided-script
  format can run, so free text fails *truthfully*.
- Streaming replies: the live path is still non-streaming at the reasoner level (surface streams).

Do not turn every future direction into immediate work. Follow the current user request.