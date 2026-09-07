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
  turn (GREETING / SMALLTALK / FEEDBACK / INSTRUCTION / REMEMBER / STATEMENT); short-term
  `ConversationContext` holds recent turns, separate from long-term memory.
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

**Recall seam** (`MemoryRetriever` + `RecalledMemory`): a deterministic lexical adapter (offline default)
and an embedding-backed semantic retriever (recall by meaning, Increment 108). Recall supplies *stance*,
never belief-confidence (memory is not truth, Vision §22). Since Increment 138 both paths are wrapped by
`DocumentMemoryRetriever`, which folds matching companion **documents** into the recalled set as
`MemoryKind.DOCUMENT` (`DocumentHit` name/snippet/relevance; lexical match; snippets never quote opaque
binary bytes).

**Reasoning seam** (`Reasoner` + `Inference`): `LlmReasoner` proposes a provisional answer; folded in as
the weakest `EvidenceSource.INFERENCE` (0.2) so an unconfirmed answer is held faintly and matures only
via `confirm()` (learning loop, Increment 110). Since Increment 138 the reasoner receives the short-term
recent turns (`ConversationContext`) in **both** the conversational (`say`/`reason`) and episode
(`think(…, conversation=…)` → `executive run` → `_reason_into`) paths; each message is still a fresh
model call (deep multi-turn spans are open).

**Forgetting** (`DecayingWeightingPolicy`, opt-in): evidence contribution fades with a half-life clock —
nothing forgets unless a decaying policy is explicitly wired in (Increment 113).

### Perception / LLM

- `PerceptionSource` (text → evidence), `CompanionPerceptionSource` (utterance → traits about the
  companion), `SpeechPerceptionSource` (speech → evidence).
- `LanguageModel` is provider-agnostic; `LlmPerception` uses it to extract candidate evidence, not to
  decide beliefs. `OpenAiCompatibleModel` + the provider registry support many remote and local
  endpoints (OpenAI, Groq, Grok, DeepSeek, Kimi, Mistral, Perplexity, OpenRouter, Together, NVIDIA NIM,
  local Ollama/LM Studio, `openai-compatible` by `base_url`).
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
`_say` routes on intent first (Increment 114): conversation turns never touch perception/memory/beliefs.

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
- Recall (lexical + semantic embeddings) and identity-aware answers: implemented.
- Provisional reasoning + learning loop (confirm) + decay forgetting: implemented.
- Episodic, belief, companion, action and goal memory: implemented; all persistent (crash-safe JSON).
- LLM abstraction/registry/live providers + self-diagnosing errors: implemented; live is opt-in.
- Capabilities: acquisition model + scout + edge providers + 12+ catalog entries (web, research, compare,
  tools, notes, mail, calendar, tasks, agent, speech seam).
- Command Center: implemented (voice, sphere/face, streaming, reasoning panel, capability/tool panels,
  Documentos panel with list/search/read/write/remove).
- Documents in recall: `MemoryKind.DOCUMENT` + `DocumentHit`, lexical `search_documents`, wrapped recall
  (semantic + documents), and document chips in `say` replies (read-through on click); folder-aware names
  (Increment 142).
- Cognition thresholds are live-tunable: one `CognitiveKnobs` VO (grounded/insight/max_goal_reflections)
  injectable at `Jarvis(...)`, runtime-swappable, exposed as a `tunables` action + sliders (Increment 141).
- The per-belief weighting policy is root-injectable: `Jarvis(default_belief_policy=...)` /
  `set_belief_policy(...)` override the source policy every fresh belief is born with (goals, actions,
  companion traits, self-observed habits); the swap reaches subsequent creations only and is inherited by
  `Jarvis.persistent()` (Increment 144).
- Reasoning/provenance visualisation: implemented (Increment 91 panel).

## Known technical debt / future directions

- Reset the audit gates at HEAD: 5 ruff errors + 44 pyright errors (all in newer tests; see STATUS.md). *(DONE — Increment 135: ruff clean · pyright strict 0 errors.)*
- Deep multi-turn reasoning: the reasoner receives the short-term `ConversationContext` in both paths
  (Increment 138) but each message is still a fresh model call; an incremental reasoning span over several
  turns is not built.
- Semantic matching for belief/connection identity (beyond exact-string D17) — embeddings exist for recall
  but not yet for identity.
- A real DB behind the repository contracts (D10); `TemporalStability` for hypotheses; more §15 energy
  modelling (charge deliberations).
- Live STT backer for the speech seam; real instruction execution (earned agency).
- Document depth: ownership, per-file search ranking, or editing via the chat itself (folder awareness landed).
- Streaming replies: the live path is still non-streaming at the reasoner level (surface streams).

Do not turn every future direction into immediate work. Follow the current user request.