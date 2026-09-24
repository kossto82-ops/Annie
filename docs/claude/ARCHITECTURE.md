# Jarvis — Architecture

## Layering

```text
                    ┌─────────────────────────────┐
                    │ Interface / Command Center  │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │ Public API / Jarvis         │
                    │ ExecutiveController         │
                    │ (cognitive, companion, goals │
                    │  actions, curiosity, etc.)  │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │ Domain / Cognition          │
                    │ Episodes                    │
                    │ Beliefs / Hypotheses        │
                    │ Semantic Memory             │
                    │ Knowledge Graph             │
                    │ Meta-Knowledge              │
                    │ Reflection / Curiosity      │
                    │ Goals / Actions              │
                    │ Capabilities (Odysseus)      │
                    │ Tools / Intent / Recall      │
                    │ Domain Events                │
                    └──────────────┬──────────────┘
                                   │ protocols
                                    ▼
                    ┌─────────────────────────────┐
                    │ Infrastructure              │
                    │ JSON / SQLite / in-memory   │
                    │ Perception                  │
                    │ Language models             │
                    │ Provider registry           │
                    └─────────────────────────────┘
```

## Repository map

```text
src/jarvis/
├── jarvis.py                 Jarvis composition root (public API + thin delegators)
├── capabilities.py           Odysseus capability acquisition surface
├── edges.py                  External edge surface (web, research, email, delegation, tools)
├── surfaces.py               CRUD surfaces (notes, documents, calendar, tasks)
├── goal_surface.py           Goal tracking surface
├── cognitive.py              think(), perceive(), consider(), reason(), confirm(), resolve()
├── companion.py              observe_companion(), explain_companion(), companion model
├── goals.py                  mark_goal_reached(), recurring_goals(), goal reflection
├── actions.py                act(), record_outcome(), belief_about_action()
├── curiosity.py              feel_curious(), pursue(), reflect_cycle(), meta-observation
├── introspection.py          observe_self(), self_beliefs(), state_summary()
├── persistence.py            persistent(), database() factories
├── domain/
│   ├── aggregates/           CognitiveEpisode, HypothesisSet, CompanionModel
│   ├── conversation/         IntentClassifier (bilingual) + ConversationContext
│   ├── entities/             Belief, Hypothesis, SemanticMemory, KnowledgeNode, KnowledgeEdge, MetaKnowledge
│   ├── enums/                episode / evidence / attention / action / capability / memory / permission / meta_knowledge kinds
│   ├── events/               domain + episode + evidence + belief + hypothesis + action + tool + semantic events
│   ├── perception/           PerceptionSource, CompanionPerceptionSource, SpeechPerceptionSource
│   ├── reasoning/            Reasoner Protocol + Inference + ReasoningSpan
│   ├── repositories/         Belief / Episode / Refutation / Capability / KnowledgeGraph / Conversation protocols
│   ├── retrieval/            MemoryRetriever, ExternalSource, ResearchSource, NotesStore,
│   │                         CalendarStore, TaskScheduler, MailBox, TaskAgent, DocumentStore, DocumentEditor
│   ├── services/             weighting, self-observation, curiosity, action advisor, goal reflection,
│   │                         reflection, hypothesis generation, association, capability scout/evaluator/
│   │                         gap-observer, knowledge source, model compare, abstraction, meta_observation,
│   │                         temporal_reasoning (belief_timeline, what_changed, belief_snapshot_at, detect_pattern),
│   │                         memory_consolidation (identify_forgetting_candidates)
│   ├── tools/                Tool Protocol, ToolRegistry, ToolPolicy
│   └── value_objects/        evidence, confidence, goals, actions, capabilities, notes, email,
│                             calendar events, scheduled tasks, tool specs/calls/results, recalled
│                             memory, inference, retrieved documents, research reports, model runs,
│                             episode_record, persisted_turn, knowledge_graph…
├── executive/                ExecutiveController (recall / consult / reason seams before deciding)
├── infrastructure/           JSON + SQLite + in-memory stores, trace (JSONL), perceivers, language models,
│                             provider registry, embedder, edge adapters (Agent-Reach, SearXNG, notes,
│                             mail IMAP/SMTP, calendar local/Google, task scheduler, task agent,
│                             LocalDocumentStore, DocumentMemoryRetriever), tools
├── interface/
│   ├── command_center.py     Router + dispatch (handle/route/Response/_COMMANDS) — ~200 lines
│   ├── _conversation.py      Chat/say pipeline, intent handlers, streaming
│   ├── _state.py             Snapshot assembly, all *_block helpers
│   ├── _cognition.py         Belief/cognition/tuning handlers
│   ├── _providers.py         Provider/speech/perceiver switching
│   ├── _external.py          External/research/compare
│   ├── _crud.py              Calendar/tasks/notes/mail/documents CRUD
│   ├── _recall.py            Memory recall, conversation sessions
│   ├── _workflow.py          Multi-step workflow chains
│   ├── _capabilities.py      Capability scouting, tool execution
│   ├── _shared.py            Shared helpers (provenance, evidence_json, etc.)
│   ├── server.py             HTTP server (socket layer)
│   └── console.html          Browser UI
├── nervous_system/           synchronous subscribe/publish/dispatch
└── observability/            EpisodeTrace (in-memory + JSONL sinks)
```

## Responsibility rules

### Domain

Owns meaning, invariants, cognitive state, evidence, beliefs, hypotheses, and domain events.

The domain must not import provider SDKs, HTTP clients, browser code, or environment-specific infrastructure.

### Executive

Coordinates domain collaborators for a cognitive episode. It should not become a second domain model or a generic workflow engine.

### Infrastructure

Implements repository/perception/model protocols and handles persistence, environment settings, network/provider details.

### Interface

Translates user/UI input into calls to the public API and renders returned state. It must not invent cognition.

### Observability

Makes cognitive activity inspectable without changing the cognitive decision itself.

## Cognitive flow

A normal reasoning episode is conceptually:

```text
trigger + evidence
       ↓
CognitiveEpisode
       ↓
retrieve/adopt existing belief if present
       ↓
recall       (memory seam: stance/context, never belief-conf — D27)
consult      (knowledge-source seam: one deliberate edge visit — D30)
reason       (reasoner seam: optional provisional inference — D28)
observe evidence
       ↓
derive confidence/stability
       ↓
ExecutiveController chooses lifecycle decision
       ↓
persist updated belief + episode
       ↓
publish domain events
```

Each seam (recall / consult / reason) is *candidate evidence or context only*; the executive stays the
decider and confidence stays derived.

### Semantic memory & the abstraction loop

Since Increment 162 a deterministic, offline semantic layer sits behind the same evidence discipline:

```text
episode completes
   ↓
_remember → consolidate_semantic_memories (domain/services/abstraction.py)
   ↓  conceptual vocabulary (stemmed + lemmatised) → entity-independent signatures → Jaccard clustering →
        "recurrence: <shared concepts>" → contradiction-aware evidence
   ↓
topic_resolution (domain/services/topic_resolution.py): canonical concept signatures group episodes —
        never by raw trigger; empty signatures never fuse; representative is display-only (Inc 163)
   ↓
SemanticMemoryRepository (InMemory / SqliteSemanticMemoryStore / JsonSemanticMemoryStore)
   ↓
lexical_memory_retriever: every durable candidate ranked relatedness = max(surface_overlap,
      concept_relevance) — recall by meaning with no embeddings; SEMANTIC is a tie-break only (Inc 168);
      strong recall bypasses the live reasoner, weak recall reaches it — candidate context only (D27);
      optional `decay` (a `DecayingWeightingPolicy`) multiplies durable candidates with a timestamp by
      `recency(t)`, so old topics rank lower (Inc 173; wired at the server root)
```

The vocabulary is a hand-maintained bilingual concept map (~stems + lemmas, ES↔EN via `CONCEPT_MAP` —
FAIL/SUCCEED/DELIVER/PROMISE/…): no LLM and no embeddings in the runtime path (D6, D8). Negation is
parity-counted (an odd number of negation markers inverts polarity). Abstracted patterns persist through
every composition root (`Jarvis.persistent()`, `Jarvis.database()`, `create_jarvis()`). Since Increment
164 consolidation/abstraction feeds on **COMPANION-origin episodes only**, and valence-less episodes
contribute *neutral* evidence (`Evidence.is_neutral`) that `derive_confidence`/`derive_stability` skip —
never a contradiction — so the semantic layer never builds valence out of nothing; consolidation stays
bounded to the most recent window so a long-lived session never rescans the whole history.

**Canonical topic identity** (Increment 163, refined by topic identity v3): episodes group by concept
signature, `topic_id = " > ".join(sorted(signature))` (e.g. `DELIVER > FAIL`), the most recent trigger
survives as display-only `representative`, single-concept topics never absorb, maturation
(consolidation/abstraction) rides the canonical topic, and curiosity `wake()`/`pursue()` carry a
persisted `target_topic_id` and run the topic's real representative trigger — internal cognition cannot
re-rank attention by echoing itself. The signature memo is a bounded `lru_cache(maxsize=1024)` with
public `clear_signature_cache()` / `signature_cache_info()`.

**Attention development** shipped as a parallel, ranked surface: `Jarvis.attention_priorities()`
derives a bounded, reversible per-topic saliency (recurrence / unresolved / revision / recency) from
episode history on every read — never persisted as a score — and `Jarvis.wake()` proposes attending to
the most salient topic. The static `feel_curious()` cascade is unchanged; priority learning is an
honest, rank-based complement ("what to attend to next"), not a reskin of the cascade.

The reflective flow is:

```text
Remember
   ↓
Connect
   ↓
Reflect
   ↓
Hypothesise
   ↓
Challenge
   ↓
Learn
   ↓
Act / recommend verification
```

The Challenge (stage four) carries the leading hypothesis's *derived* confidence and temporal stability
(shared `derive_stability` estimator with beliefs); a leader resting on a narrow time window is narrated
as possibly overfitting -- reported honestly, never altering its strength, the ranking, or a tie
(Increment 146).

Episodes hold exactly ONE conclusion-model: a working `Belief` (conclusion) or a `HypothesisSet`
(deliberation), in a single `_conclusion` slot. Both ride the same lifecycle and the same event
boundary, and `EpisodeKind` is *derived* from which one the episode held -- never painted by the record
callers (Increment 147).

The conversational flow (command center `say`, Increment 114) routes by intent first:

```text
utterance
   ↓
classify intent (GREETING/SMALLTALK/…/REMEMBER/STATEMENT/ACT)
   ↓
question → perceive (world + companion) → recall (memory + documents)
         → consult → reason (with recent turns) → reply
statement → _remember_statement → USER_STATEMENT evidence (1.0) → jarvis.think → memory
directive → ConversationIntent.ACT → Jarvis.execute → sandboxed tools at approved=False → honest narration
```

Since Increment 138 the reasoner receives the short-term `ConversationContext` (recent turns) in this
flow and in episode reasoning (`think(…, conversation=…)` → executive run → `_reason_into`). Since
**Increment 145** it also receives the session `ReasoningSpan` (`domain/reasoning/reasoning_span.py`,
`Jarvis.reasoning_span()` / `reset_reasoning()`): each answered question is a step in a bounded,
session-scoped thread span, so a follow-up continues the discussion instead of being a fresh stateless
call. The span's thread lifecycle is deterministic — answering a new query opens/revises a thread and
moves the previous one on; `confirm()` seals a thread (grounded by the belief loop, it leaves the span) or
flags it disputed (the prompt names corrected proposals so they are never asserted again). The LLM
proposes answer content; it never decides thread state (§38). Replies that
recalled a matching document carry a `documents` chip list (name + snippet) in the stream meta and the
fallback JSON.

## Conversation vs long-term memory

Since Increment 167 the memory boundary is explicit and tested:

- **Turns are context, never memory.** `MemoryKind.CONVERSATION` entries are surface-only candidates in
  recall: matched lexically, never recited as answers. Long-term recall (beliefs, episodes, semantic
  patterns, graph, documents) is what paraphrase should reach.
- **Statements are real memory.** A `STATEMENT` intent (an everyday ≥3-word non-question sentence,
  `_MIN_STATEMENT_WORDS = 3`) is stored through `_remember_statement` as `EvidenceSource.USER_STATEMENT`
  evidence (weight 1.0) and persisted — first-person statements route through the companion channel — so a
  follow-up question after a restart is answered from memory, with the stored sentence quoted verbatim.
- End-to-end proof lives in `tests/test_end_to_end_memory.py` (real SQLite via
  `Jarvis.database(tmp_path)`; "restart" = a fresh Jarvis over the same directory).

## Change of mind (revision)

Since Increment 169 a corrected decision is first-class, not a new contradiction:

- `Belief.revise(statement, evidence, ...)` swaps the belief's statement, folds the new evidence, and moves
  the superseded statement into the belief's `precedents` archive (a first-class timeline). `BeliefRevised`
  flows through the nervous system; `episodes.belief_revision_history` exposes the archive.
- Companions: `Jarvis.revise_companion(trait, evidence, replaces=…)` supersedes the earlier stance; the old
  text is never recalled as current. Revision cues are conservative and bilingual ("he cambiado de opinion",
  "me retracto", "i changed my mind", "on second thought", "ya no quiero", "i no longer want").
- Resolution survives restarts on all three store families (in-memory, JSON, SQLite).

## Episode evidence-request writer

Since Increment 170 a COMPANION-origin, FULL-attention, question-shaped, evidence-less episode leaves a
transient `EvidenceRequest` in the unresolved store — the epistemic trace that Jarvis *did* wonder and had
nothing to conclude, so curiosity can return to it. `is_question_shape` (public alias in
`executive_controller.py`) reuses the question cues (`_QUESTION_CUES` + trailing `?`). The write is
epistemically inert: no evidence, no belief, no confidence.

**The loop closes** (Increment 174, roadmap F3): `retirable_open_questions` (`jarvis.py`) is the read-only
*retirement* side of the same seam — when a conversational turn *re-triggers* an open item (turn bears on
it at the recall floor `_RE_TRIGGER_RELEVANCE = 0.2`), Jarvis looks for a grounded belief that is
*not* the working-conclusion wrapper (`WORKING_PREFIX`), for whom the natural wording is the newest
companion-origin statement (excluding the `_CONFIRM_INTRO` "the companion confirmed/corrected this"
echoes), falling back to the belief subject. Only a grounded belief (conf ≥ `grounded_confidence`) that
bears on the question at `_RE_ANSWER_RELEVANCE = 0.3` retires it — the answer is handed to
`resolve_open_question` so the loop completes in the conversation flow (`_retire_answered_questions`
in `_conversation.py`). A confirmation also grounds+retires its question; an ungrounded re-ask
("I still wonder …") never retires (grace); CURIOSITY echoes never reach the say flow. `open-questions`
/ `settle-question` command-center surfaces + `memory.open_questions` snapshot expose the store.


## Market-edge capabilities & seams

Every concrete capability sits behind a **domain Protocol** in `domain/retrieval` (or `domain/tools`)
with an **infrastructure adapter** at the edge (injectable io/net, offline default, `build_*() -> None`
when unconfigured — D7/D8). Jarvis exposes delegated methods; a `CapabilityProvider` in the registry
reports readiness, so `can_do` is honest (D29).

```text
capability name                    seam (Protocol)                      adapter at the edge
──────────────────────────────────────────────────────────────────────────────────────────────
search the web / read documents    ExternalSource                       AgentReachSource
deep research                      ResearchSource                       SearXNG adapter
compare language models            ModelComparator                      RegistryModelComparator
reason with a language model       Reasoner                             LlmReasoner / SilentReasoner
recall by meaning                  MemoryRetriever                      lexical `relatedness` scorer (Inc 168) + EmbeddingMemoryRetriever (opt-in)
manage notes                       NotesStore                           LocalNotesStore
send/read email                    MailBox                              IMAPSMTPMailBox
manage calendar                    CalendarStore                        LocalCalendarStore + Google
manage tasks                       TaskScheduler                        LocalTaskScheduler
delegate to an agent               TaskAgent                            ToolRegistryTaskAgent / PydanticAiTaskAgent (opt-in)
perceive speech                    SpeechPerceptionSource               browser STT (default) / Whisper-compatible ear (opt-in, JARVIS_STT_*)
execute tools                      ToolRegistry + ToolPolicy            FileSystemTool / EchoTool
work with files                    DocumentStore                        LocalDocumentStore
edit project files                 ToolRegistry (project: roots)        FileSystemTool
```

Material actions may be delegated to an edge agent behind these seams (revised D1) — the agent returns
*outcomes with provenance*, never Jarvis's judgement (D6), never writes to beliefs/memory directly.

## Files & documents

An extra storage seam (`DocumentStore`) treats companion files as bytes the core may list/read/write/
remove (`LocalDocumentStore`, io-injectable, offline default `build_document_store`). Names are bounded
relative paths (`runbook.md` or `docs/api.md`, both `/`-normalised), so the companion can file documents
under folders without ever escaping the sandbox (Increment 142). Every stored document carries
recorded provenance: `DocumentMeta` (`DocumentOwner` attribution — companion vs jarvis-generated —
plus stored/updated timing and size) persisted out-of-band in a reserved `_jarvis-meta.json` index that
`list`/`search` never surface; `write_document` takes `owner`, and a file that predates provenance
tracking reads honest `None` rather than a guess (Increment 148). Documents are also editable from the
chat itself through the same proposal-decided split as reasoning (Vision §38): a domain `DocumentEditor`
seam (`SilentDocumentEditor` offline, `LlmDocumentEditor` over the `LanguageModel` seam otherwise)
*proposes* the complete revised text for a free-form instruction; Jarvis applies it, preserves the
recorded owner, refuses binary files, and frames what changed from the real diff (Increment 149).
Documents also
feed **recall**: `DocumentMemoryRetriever` wraps any base retriever and appends lexical `DocumentHit`s
(`MemoryKind.DOCUMENT`, procedure `"document: <name>"`). The wrap is source-aware — the retriever keeps a
callable to the current store, so swapping `set_documents_store` at runtime is honoured without rewiring.
`say` separates document hits from memory and renders them as chips; snippets never quote opaque binary
bytes (binary findable by name only).

**Passage search** (Increment 175, roadmap F4): beyond document-level ranks, the same `DocumentStore`
seam exposes `search_passages(query, limit=5) -> tuple[PassageHit, ...]` — deterministic
sliding-window chunking (fixed 32-word window, 8-word overlap, word-boundary, byte offsets computed
over UTF-8) with **no embeddings** (D18-faithful, vocabulary-only). Each chunk is ranked by the same
`relatedness` scorer the memory line uses (Increment 168), so a 3-letter query, a bilingual paraphrase,
and a cross-window phrase all reach the *passage*, not just the file. Recall provenance becomes
`document: <name>@<start>-<end>` (offsets parsed with a trailing-anchored regex, robust to `@` in a
name); `say` document chips carry the passage snippet and its byte offsets; `documents search` returns
passage + offsets + relevance in both the reply line and the `hits` payload. Binary files are never
chunked — they keep the name-only `DocumentHit` path (byte offsets 0/0, no fake snippet).

## Cognition thresholds

The grounded/insight attention gates and the goal-reflection cap are not module constants: one validated
`CognitiveKnobs` value object (`src/jarvis/domain/value_objects/cognitive_knobs.py`, defaults
0.5/0.5/3) is injectable at `Jarvis(cognitive_knobs=...)`, swappable at runtime via
`knobs()` / `set_knobs()`, threaded into the executive and the self-observation observers, and exposed
live through the `tunables` command-center action and the settings-panel sliders (Increment 141).

## Belief weighting policy

Every belief is born with a `weighting_policy` — the source factors that turn evidence into its confidence.
The historical default is `DEFAULT_WEIGHTING`, but the *fresh-belief* source policy is root-injectable:
`Jarvis(default_belief_policy=...)` overrides it at construction (and `set_belief_policy(...)` at runtime),
so goals, actions, companion traits and self-observed habits all inherit it; the swap reaches subsequent
creations only, so nothing stored is silently re-weighted. `CompanionModel` and the self-observation
observers accept the policy as their default, and `Jarvis.persistent()` forwards it at boot (Increment 144).
The episode-path decay composition remains separately injectable per belief (Increment 113).

**Scheduled honest forgetting** (Increment 173): `ForgettingCandidates`
(`domain/services/forgetting.py`) wraps `identify_forgetting_candidates` + the decay policy with honesty
gates — never a grounded ≥threshold companion trait, never a belief reaffirmed in the last 30 days.
`Jarvis.rest()` runs the read-only sweep; the command-center `forgetting` command (`health`/`dry-run`/
`apply`) and the memory-panel "Salud de memoria" card surface it; **no delete without an explicit apply**
(read-only identify, gated apply). `DecayingWeightingPolicy.recency(observed_at)` is public and the
composition root passes a live clock (`server.py`), so recall biases old topics lower without touching
stored belief confidence.

## Odysseus (capability acquisition)

Odysseus is the mechanism by which Jarvis recognises and grows new *capabilities* --
extensions of its ability to act (Vision §34). Phase 1 delivered the core model + scout
(discovery); Phase 2 grounds recognition in evidence and wires acquisition into curiosity
and the surfaces; Phase 3 put the *live* capability at the edge behind a provider registry;
Phase 4 added the self-initiated half: Jarvis noticing recurring subjects it failed to
answer, as the seed of a need; Phase 5 backed the remaining seams -- reasoning and
meaning-recall -- so every catalog capability reports live when its
runtime provider is active; Phase 6 closed the loop -- the reflective cycle now
auto-scouts capability gaps as part of its own pass; **Phase 7 (the Odysseus Fases 0–N
sweep, Increments 115–134)** expanded the catalog to the concrete edge domains (web,
deep research, model comparison, tools, notes, mail, calendar, tasks, agent, speech)
and revised D1 so Jarvis may delegate *material* actions to an edge agent behind a domain
seam — never cognition (see `docs/claude/INTEGRACION_ODYSSEUS.md` for the full plan).

The flow:

```text
recognise_need  (a need becomes a belief, confidence derived from evidence, §8)
        ↓
capability_scout
        ↓
Capability proposals (PROPOSED), persisted
        ↓
capability_evaluator  (derived stance: suggest / ask first / withhold, §28)
        ↓
feel_curious → pursue  (a confident unmet need raises an acquisition impulse)
        ↓
acquire or reject (deliberate; autonomy is earned, Vision §28)

(Phase 4/6) observe_capability_gaps → detect_capability_gaps
        ↓
auto_scout_gaps: each recurring failure subject → recognise_need (grounded in the failed
episodes) → scout proposes how to answer better
        ↓
wired into reflect_cycle (auto) and the `capability notice` command (manual)
```

Boundaries:

- The scout is an evidence *producer* only: it pairs a need with plausible candidates from
  a deterministic catalog (keyword-matched capability templates). It decides nothing
  (Vision §32).
- A ``Capability`` is bookkeeping of what Jarvis *can* do; the capability itself is always an
  injectable, provider-agnostic capability at the edge (D7). No cognition lives inside a
  capability.
- A recognised need is an ordinary *belief* (``"I need the ability to …"``) whose confidence
  is derived from evidence (Vision §8) -- never asserted. ``capability_evaluator.recommend``
  mirrors ``action_advisor`` (Vision §28): it *suggests* acquisition only when the need is
  confident and the capability is not yet held; it withholds when contracted; otherwise it
  asks first. It only recommends, it acquires nothing.
- Acquiring (`CapabilityStatus.ACQUIRED`) and rejecting (`REJECTED`) are deliberate, separate
  steps -- autonomy is earned (Vision §28).
- Curiosity closes the loop: a confidently-needed, unavailable capability raises a
  ``CuriosityImpulse`` naming it, and ``pursue`` marks it acquired (so growth is both earned
  and acted on). ``state_summary`` and the Command Center ``capability`` command expose
  capabilities and needs.
- Gap detection (Phase 4/6) is read-only observation: `capability_gap_observation.detect`
  clusters the episode history by shared subject words and reports each subject Jarvis
  concluded about *ungrounded* more than once (`observe_capability_gaps` /
  `unanswered_subjects`). It only *detects*. `auto_scout_gaps` turns each gap into an
  evidence-grounded need (`recognise_need`) grounded in the failed episodes, scouting
  candidates — the need's confidence is derived, never asserted. It is wired into the
  reflective cycle (`reflect_cycle`, so growth is self-initiated each pass) and surfaced
  through the Command Center ``capability notice`` action (`ReflectiveCycle` reports the
  proposals). Idempotent: a gap already recorded is skipped on the next pass. Like the
  scout, this is shallow keyword matching (D11), deliberately.
- A ``Capability`` is *bookkeeping*; the *live* side is a ``CapabilityProvider`` at the edge
  (D7) -- a registry (`capability_registry.StaticCapabilityRegistry`) maps a capability name
  to the concrete adapter that serves it. `Jarvis.can_do(name)` is true only when a
  capability is *both* acquired and live-backed, so acquisition is real, not decorative: the
  Internet command (`external` read/search) now requires the matching capability to be
  earned, and the persistent edge (agent-reach) backs "search the web"/"read external
  documents" by default. The crawl/backing is the same seam type for the runtime ones:
  `ReasonerCapability` ("reason with a language model") and `SemanticRecallCapability`
  ("recall by meaning") are mutable edge providers Jarvis or a caller flips when the live
  reasoner / embedding recall is active — a silent (offline) reasoner and lexical-only
  recall do *not* count, so `can_do` stays honest.

Storage: `CapabilityRepository` and the need beliefs (`BeliefRepository`) are domain Protocols
with in-memory and JSON stores, wired into `Jarvis.persistent()` as `capabilities.json` and
`needs.json` so acquisitions and recognised needs survive a restart.

## LLM boundary

```text
raw observation
      ↓
PerceptionSource
      ↓
LanguageModel (optional)
      ↓
candidate Evidence
      ↓
Domain cognition
      ↓
Belief / hypothesis / decision
```

The model must not directly set belief confidence or make the core decision.

The `LanguageModel` seam is opt-in and provider-swappable (Increment 153): `PydanticAiModel`
(`infrastructure/pydantic_ai_model.py`) implements it over pydantic-ai 2.40's `FunctionModel`, imported
lazily so the SDK is only a dependency when a live provider is configured (`live` extra). It completes and
streams, rewrites a question when the Proficiency flag says so, extracts structured `TextDatum` (markdown)
from a reply, answers an absent claim with honest "I have no belief" (Vision §37), and accumulates per-call
`Usage`. Next to it, `PydanticAiTaskAgent` (`infrastructure/pydantic_ai_task_agent.py`) is the opted-in
executor behind the `TaskAgent` seam: it runs decided multi-step tool loops, bakes tool schemas via
pydantic's `prepare` hook, refuses blocking instructions, recovers from failed steps, and falls back to
the tool registry on provider failure. `build_task_agent` only selects it when the agent root is set, the
provider is configured as `pydantic` with a model, and the package is installed.

## Recall / reasoning / consult boundary

The three "answer the unknown" seams mirror each other and are strictly candidate-or-context
(D27/D28/D30):

```text
question with no grounded belief
      ↓
MemoryRetriever   → recalled context/stance (never belief-confidence; memory ≠ truth)
KnowledgeSource   → one deliberate edge consult: candidate Evidence (research: EXTERNAL_SOURCE
                   0.4; compare: INFERENCE 0.5) — honest None when empty/failed
Reasoner          → provisional Inference as response context; may be folded in as the
                   weakest INFERENCE evidence (0.2) and matured only via confirm()
      ↓
executive still decides; confidence still derived
```

- Recall is opt-in (offline default lexical), edges are opt-in (un-wired Jarvis never consults), and
  the reasoner is opt-in (`SilentReasoner` when no provider). When the provider exposes a stream seam the
  reasoner streams its reply (`LlmReasoner.infer_stream`), and `Jarvis.reason_stream` records the
  reasoning span only on a completed, non-empty stream — a mid-stream provider failure propagates and is
  never span-recorded (Increment 153).
- A reasoned answer is *remembered* as weak, clearly-sourced `INFERENCE` evidence (learning loop,
  Increment 110); it is grounded only by real evidence or a companion's `confirm()`.

## Persistence boundary

Repositories belong to the domain as protocols. JSON/in-memory/SQLite stores (and the JSONL episode trace)
belong to infrastructure. All writes are crash-safe (atomic temp+rename for files, Increment 111; SQLite
transactions for the DB). No database concept leaks into the domain: the SQLite side implements the same
contracts, not a new storage API.

- `Jarvis.persistent(directory)` composes the crash-safe JSON stores (`beliefs.json`, `episodes.json`, …)
  plus the JSONL trace under one directory (Increment 111+); `Jarvis.database(directory)` is the real
  database twin (Increment 150): `build_sqlite_repositories` opens one `jarvis.db` (single connection,
  `check_same_thread=False` for the threaded server) and lines up `SqliteBeliefStore` (a validated whitelist
  of belief tables: beliefs/companion/actions/reversibility/goals/subgoals/needs), `SqliteEpisodeStore`
  (ordered by an autoincrement `seq`, `record_id` unique), `SqliteCapabilityStore` (name key) and
  `SqliteRefutationStore` (observation+belief key) behind the same Protocols. Both store families share the
  canonical serialisers, so rehydration is identical: confidence/stability are derived from stored evidence,
  never persisted as an assertion, and the weighting policy is not stored.
- The command center's composition root (`create_jarvis`) uses SQLite when a `home` is set (Increment 150),
  so a desktop assistant persists to one transactional database; `Jarvis.persistent()` remains the file-backed
  twin for the JSON stores.
- The edge seams followed (Increment 151): `SqliteCalendarStore` / `SqliteNotesStore` /
  `SqliteTaskScheduler` back the `CalendarStore` / `NotesStore` / `TaskScheduler` Protocols in a
  `jarvis.db` inside their `JARVIS_*_ROOT`, and the environment builders (`build_calendar_store`,
  `build_notes_store`, `build_task_scheduler`) serve them; the io-injectable `Local*` adapters remain
  available for offline tests and direct use, unmodified (D8).
- Decision provenance joined the same database (Increment 152): `SqliteEpisodeTrace` appends each
  cognitive event to a seq-ordered `trace_events` table in the same `jarvis.db` and replays it on startup
  (tolerant of corrupt rows and unknown event types, like the JSONL twin). Under `Jarvis.database()` the
  only files intentionally left on disk are the user's documents (`docs` bytes) and the `.env` LLM config;
  the durable JSONL `JsonEpisodeTrace` and the JSON stores remain the twins under `Jarvis.persistent()`.

## UI boundary

The Command Center is a window onto Jarvis. If a UI feature requires new cognitive behaviour, implement that behaviour in the core first; do not hide cognition in JavaScript or HTTP handlers.

The UI does no perception, recall, or reasoning of its own: `handle`/`route`/`snapshot` call Jarvis's
ordinary methods and render what the core derived. Intent classification lives in the domain
(`domain/conversation/intent.py`), not the UI, so conversation routing is testable socket-free.

## Remediation notes (2026-09-14)

What the audit remediation changed structurally (see `REMEDIATION_REPORT.md`):

- **Same-component seams are public.** The split god object (`jarvis.py` ↔ facades) and the
  split router (`command_center.py` ↔ `_*` modules) communicate through public seams, not
  privates: read-only repository/executive/ledger properties on `Jarvis` (mirroring the
  existing `beliefs`/`episodes` precedent) and per-module `COMMANDS` tables composed into
  the public router table.
- **One energy ledger.** `EnergyLedger` owns costs/spent/budget/available; cognition,
  surface and adaptation share it.
- **Evidence identity.** `domain/services/evidence_identity.py` (`same_observation`) is the
  single duplicate rule for beliefs, hypotheses and semantic memories (D15); distinct
  world-events carry provenance (run ids, episode ids).
- **Learned state.** `LearnedState` (knobs + reason + timestamp) persists behind repository
  contracts (JSON + SQLite); only adaptation writes, the executive notifies, the root
  rehydrates with explicit-wins precedence (D17).
- **Snapshot purity.** Snapshots report wiring, never read remote stores (D16); graph
  traversal reads through `_recall_into` as `MemoryKind.GRAPH_NODE` (depth-2, decaying
  relevance); the reflective cycle gates hypothesise/challenge/learn and reports its path.
- **New durable surfaces.** `learned.json`, `semantic.json`, `graph.json`,
  `conversation.json`, `unresolved.json` (JSON twin); matching tables in `jarvis.db`
  (SQLite twin, extended `SqliteRepositories`).

## Relation-aware recall and strategy selection (2026-09-15)

What the P2-B/C reintegration added structurally, all inside existing seams (D12):

- **Relation-aware graph recall.** `relation_cues_for()` in the executive matches
  trigger tokens against a seed's stored relation types and traverses each cue
  separately (`via <relation>` provenance); no cue keeps the old unfiltered
  traversal. Relations remain recall context, never evidence (D20).
- **Strategy selection consumption.** The executive holds both the lexical
  retriever and (when enabled) the embedding retriever and routes each recall
  through `select_retrieval_strategy()` off a durable, bounded
  `RetrievalStrategyStats` record (`retrieval_strategy.json` + `retrieval_strategy_outcomes`
  table); outcomes record automatically, misses fall back once so both sides stay
  revisable. With no embedding retriever wired the routing is byte-for-byte the
  old lexical-only path and records nothing. Selection routes candidates only;
  confidence is untouched (D21).
