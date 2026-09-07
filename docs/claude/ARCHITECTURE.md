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
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │ Domain / Cognition          │
                    │ Episodes                    │
                    │ Beliefs / Hypotheses        │
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
                    │ JSON / memory stores        │
                    │ Perception                  │
                    │ Language models             │
                    │ Provider registry           │
                    └─────────────────────────────┘
```

## Repository map

```text
src/jarvis/
├── jarvis.py                 Jarvis composition root (public API + persistent() wiring)
├── domain/
│   ├── aggregates/           CognitiveEpisode, HypothesisSet, CompanionModel
│   ├── conversation/         IntentClassifier (bilingual) + ConversationContext
│   ├── entities/             Belief, Hypothesis
│   ├── enums/                episode / evidence / attention / action / capability / memory / permission kinds
│   ├── events/               domain + episode + evidence + belief + hypothesis + action + tool events
│   ├── perception/           PerceptionSource, CompanionPerceptionSource, SpeechPerceptionSource
│   ├── reasoning/            Reasoner Protocol + Inference
│   ├── repositories/         Belief / Episode / Refutation / Capability protocols
│   ├── retrieval/            MemoryRetriever, ExternalSource, ResearchSource, NotesStore,
│   │                         CalendarStore, TaskScheduler, MailBox, TaskAgent, DocumentStore
│   ├── services/             weighting, self-observation, curiosity, action advisor, goal reflection,
│   │                         reflection, hypothesis generation, association, capability scout/evaluator/
│   │                         gap-observer, knowledge source, model compare
│   ├── tools/                Tool Protocol, ToolRegistry, ToolPolicy
│   └── value_objects/        evidence, confidence, goals, actions, capabilities, notes, email,
│                             calendar events, scheduled tasks, tool specs/calls/results, recalled
│                             memory, inference, retrieved documents, research reports, model runs…
├── executive/                ExecutiveController (recall / consult / reason seams before deciding)
├── infrastructure/           JSON + in-memory stores, trace (JSONL), perceivers, language models,
│                             provider registry, embedder, edge adapters (Agent-Reach, SearXNG, notes,
│                             mail IMAP/SMTP, calendar local/Google, task scheduler, task agent,
│                             LocalDocumentStore, DocumentMemoryRetriever), tools
├── interface/                command_center.py (pure handle/route/snapshot) + server.py + console.html
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
recall       (memory seam: stance/context, never belief-conf — D35)
consult      (knowledge-source seam: one deliberate edge visit — D38)
reason       (reasoner seam: optional provisional inference — D36)
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

The conversational flow (command center `say`, Increment 114) routes by intent first:

```text
utterance
   ↓
classify intent (GREETING/SMALLTALK/…/REMEMBER/STATEMENT)
   ↓
conversation turn  OR  perceive (world + companion) → recall (memory + documents)
                                                  → consult → reason (with recent turns) → reply
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

## Market-edge capabilities & seams

Every concrete capability sits behind a **domain Protocol** in `domain/retrieval` (or `domain/tools`)
with an **infrastructure adapter** at the edge (injectable io/net, offline default, `build_*() -> None`
when unconfigured — D7/D8). Jarvis exposes delegated methods; a `CapabilityProvider` in the registry
reports readiness, so `can_do` is honest (D37).

```text
capability name                    seam (Protocol)                      adapter at the edge
──────────────────────────────────────────────────────────────────────────────────────────────
search the web / read documents    ExternalSource                       AgentReachSource
deep research                      ResearchSource                       SearXNG adapter
compare language models            ModelComparator                      RegistryModelComparator
reason with a language model       Reasoner                             LlmReasoner / SilentReasoner
recall by meaning                  MemoryRetriever                      EmbeddingMemoryRetriever
manage notes                       NotesStore                           LocalNotesStore
send/read email                    MailBox                              IMAPSMTPMailBox
manage calendar                    CalendarStore                        LocalCalendarStore + Google
manage tasks                       TaskScheduler                        LocalTaskScheduler
delegate to an agent               TaskAgent                            ToolRegistryTaskAgent (or edge)
perceive speech                    SpeechPerceptionSource               browser STT (seam, no backer yet)
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
under folders without ever escaping the sandbox (Increment 142). Documents also
feed **recall**: `DocumentMemoryRetriever` wraps any base retriever and appends lexical `DocumentHit`s
(`MemoryKind.DOCUMENT`, procedure `"document: <name>"`). The wrap is source-aware — the retriever keeps a
callable to the current store, so swapping `set_documents_store` at runtime is honoured without rewiring.
`say` separates document hits from memory and renders them as chips; snippets never quote opaque binary
bytes (binary findable by name only).

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

## Odysseus (capability acquisition)

Odysseus is the mechanism by which Jarvis recognises and grows new *capabilities* --
extensions of its ability to act (Vision §34). Phase 1 delivered the core model + scout
(discovery); Phase 2 grounds recognition in evidence and wires acquisition into curiosity
and the surfaces; Phase 3 put the *live* capability at the edge behind a provider registry;
Phase 4 added the self-initiated half: Jarvis noticing recurring subjects it failed to
answer, as the seed of a need; Phase 5 backed the remaining seams -- reasoning and
meaning-recall -- so every catalog capability except speech now reports live when its
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

## Recall / reasoning / consult boundary

The three "answer the unknown" seams mirror each other and are strictly candidate-or-context
(D35/D36/D38):

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
  the reasoner is opt-in (`SilentReasoner` when no provider).
- A reasoned answer is *remembered* as weak, clearly-sourced `INFERENCE` evidence (learning loop,
  Increment 110); it is grounded only by real evidence or a companion's `confirm()`.

## Persistence boundary

Repositories belong to the domain as protocols. JSON/in-memory stores (and the JSONL episode trace)
belong to infrastructure. All writes are crash-safe (atomic temp+rename, Increment 111).

A future database should implement the same repository contracts rather than moving database concepts into the domain.

## UI boundary

The Command Center is a window onto Jarvis. If a UI feature requires new cognitive behaviour, implement that behaviour in the core first; do not hide cognition in JavaScript or HTTP handlers.

The UI does no perception, recall, or reasoning of its own: `handle`/`route`/`snapshot` call Jarvis's
ordinary methods and render what the core derived. Intent classification lives in the domain
(`domain/conversation/intent.py`), not the UI, so conversation routing is testable socket-free.
