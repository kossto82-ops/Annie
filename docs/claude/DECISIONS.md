# Jarvis — Architectural Decisions

This file is intentionally short. It contains decisions Claude should treat as constraints unless the user explicitly asks to revisit them.

## D1 — Jarvis is not an agent wrapper; the core owns cognition

Do not introduce an outer autonomous-agent framework that calls Jarvis methods to
*simulate cognition*. The reflective cycle and all reasoning/deciding stay inside
Jarvis's core (Delegating any of *that* is forbidden).

Jarvis MAY delegate **material actions** to an edge agent (e.g. Odysseus agent mode)
behind a domain seam (D7): the agent executes concrete tasks with its own tool
catalog (email, notes, calendar, shell, web, …) and returns *outcomes with
provenance*. It never substitutes for Jarvis's judgement (D6) and never writes to
Jarvis's beliefs/memory directly. Delegation is governed by the existing
controlled-autonomy policy (risk + permission + confidence + reversibility →
EXECUTE / ASK / REFUSE) and by the Tool Registry's permission levels (destructive /
external demand approval). The boundaries are earned, observable, reversible, bounded.

## D2 — Cognitive Episode is the unit of cognition

A prompt/response is not the fundamental unit. New cognitive functionality should attach to the episode/state model where appropriate.

## D3 — Evidence precedes belief strength

Belief confidence is derived from evidence. Do not add setters or shortcuts that allow arbitrary confidence assignment.

## D4 — Contradictions are first-class

Contradicting evidence must remain visible and auditable. Do not silently overwrite or discard it.

## D5 — Competing hypotheses remain possible

Do not force one explanation when evidence does not justify choosing it.

## D6 — LLMs are perception components, not judges

An LLM may extract candidate evidence from language. The domain derives confidence and makes decisions.

## D7 — Provider agnostic

No provider SDK should leak into the domain. Provider selection belongs at composition/configuration boundaries.

## D8 — Offline deterministic core

The default test suite must not require network access or API keys. Live integrations are opt-in.

## D9 — UI is not cognition

The Command Center renders and routes state. It must not become a second brain.

## D10 — Repository abstraction before database choice

The domain defines repository contracts. Persistence technology can change behind them. Do not introduce PostgreSQL/SQLite/graph DB merely because a feature sounds like memory.

## D11 — Shallow matching is deliberate outside identity

Belief identity is **canonical-topic-anchored** since Increment 163 (episodes group by concept
signature, never by raw trigger) and recall reaches the same memory by meaning since Increment 168
(`relatedness = max(surface_overlap, concept_relevance)` over a bilingual concept map). Deliberately
*shallow* keyword matching may still be used in surfaces that only *propose* options (capability scout,
gap detection) — never to decide identity, evidence, or confidence. Embeddings are an opt-in recall
channel, not an identity mechanism.

## D12 — Prefer domain concepts over generic abstractions

Avoid generic `Manager`, `Engine`, `AIService`, `Orchestrator`, or wrapper abstractions unless they represent a real responsibility that cannot live in an existing domain/infrastructure component.

## D13 — Configuration over hard-coded providers/tunables

When adding provider selection or runtime tuning, prefer injected/configured values over module-level constants.

## D14 — Graphify is a dev-time tool, not Jarvis memory

Graphify indexes source code into a local code graph for Claude Code navigation
(`.mcp.json`, `docs/graphify.md`). It is not imported by Jarvis, not in
`pyproject.toml`, and not a substitute for episodic/semantic/belief memory. Only
the deterministic `graphify update` (AST, no LLM) path is used — consistent with
D8. If Jarvis ever needs graph *retrieval* inside cognition, it goes behind a
domain-owned `GraphRetriever` Protocol with Graphify as one swappable adapter
(cf. D7/D10/D12) — never a direct dependency. Do not wire that interface into
`src/` until a real consumer exists.

## D15 — Evidence identity is default-ON deduplication

The same observation re-injected (same evidence id, or the same claim
fingerprint on the same UTC day) is skipped by Beliefs, Hypotheses and
SemanticMemories through one shared `same_observation` policy. Independent
confirmations (different source, provenance, or day) still count. Production
code that models distinct world-events must carry distinguishing provenance
(action run ids, episode ids); manufacturing distinctness to evade the
policy is forbidden. See `domain/services/evidence_identity.py`.

## D16 — Snapshots never perform live network reads

The command-center snapshot reports what is wired (source/connected), never
fetches through a remote store. On-demand commands (`calendar list`, …) do
the reading. A test that wires a remote store must never stall the suite.

## D17 — One authoritative copy of runtime-tunable state

CognitiveKnobs live in the executive; the composition root reads through and
never keeps a second copy. Learned adaptations persist as LearnedState
(knobs + reason + timestamp) behind repository contracts; operator tuning
never writes there. Meta-knowledge stays derived from persisted history.

## D18 — Semantic abstraction is deterministic and offline

Semantic generalization (paraphrase/analogy/cross-domain ties and ES↔EN) is implemented as an explicit,
testable domain service over a hand-maintained bilingual concept vocabulary (stemmed + lemmatised
tokens, `CONCEPT_MAP` ES↔EN) — not an LLM call and not embeddings (D6, D8). LLMs remain perception
providers that may extract evidence behind the provider seams; they must never be smuggled into the
abstraction layer as a shortcut. The vocabulary is extended in `domain/services/abstraction.py` with
tests, never rewritten per-use. The retriever ranks every durable candidate with the one
`relatedness` scorer (D8); `SEMANTIC` is a tie-break only, never a separate scoring path (Increment 168).

## D19 — Attention priorities are derived, never stored

Attention development is a *read-side ranking*: recurrence/unresolved/revision/recency
signals are re-derived from the bounded recent episode history on every call
(`Jarvis.attention_priorities()`, `Jarvis.wake()`), bounded by a window and capped to
[0,1], so no second authoritative learning state and no unbounded score accumulation
exist. The `feel_curious()` cascade keeps its static class order; ranked attention is
a parallel honest surface, and nothing in it may mutate episode/belief state.

## D20 — Relations are retrieval context, never authority

A stored graph relation may route recall (relation-aware traversal) but may
never ground, raise, or transfer belief confidence. Poisoned or mistaken edges
surface as labelled context the same as any other memory.

## D21 — Strategy preferences are revisable routing evidence

Retrieval-strategy statistics decide which retriever surfaces candidates, not
what Jarvis concludes. A preference forms only on well-sampled, meaningful
gaps, defaults to lexical otherwise, and must always be reversible by later
counter-evidence. Flooding the record is bounded by the cap and undone by
honest use.

## D22 — Belief identity is canonical-topic-anchored

Episodes group by canonical concept signature, never by raw trigger; empty
signatures never fuse (`∅==∅` is a merge bug) and single-concept topics never
absorb. The most recent trigger survives as display-only `representative`; the
`topic_id = " > ".join(sorted(signature))` is the identity (Increment 163, refined
by topic identity v3).

## D23 — Consolidation is COMPANION-only and valence-neutral

Semantic abstraction/consolidation feeds on `COMPANION`-origin episodes only, and
valence-less episodes contribute *neutral* evidence (`Evidence.is_neutral`) that
`derive_confidence`/`derive_stability` skip and that emits neither
`SemanticMemoryReinforced` nor `Contested`. The semantic layer must never build
valence or contradiction out of episodes that carried none (Increment 164).

## D24 — Turns are context; statements are memory

`MemoryKind.CONVERSATION` entries stay surface-only candidates in recall — matched
lexically, never recited as answers. Long-term recall is what meaning should reach.
Statements cross into memory deliberately: an everyday ≥3-word non-question sentence
is stored as `USER_STATEMENT` evidence (weight 1.0, persisted; companion channel when
first-person) — turning conversation into memory is explicit, never ambient
(Increment 167).

## D25 — A changed mind resolves, never stacks

`Belief.revise()` supersedes the earlier stance, moves it into the belief's
`precedents` archive, and never recalls it as current. A corrected decision is a
first-class revision (a first-class timeline), not a new contradiction that must be
argued down. `revise_companion` applies the same rule to the companion model
(Increment 169).

## D26 — Evidence-request writing is epistemically inert

An evidence-request write is gated (COMPANION-origin, FULL-attention,
question-shaped, evidence-less), writes no evidence and no belief, and is a
transient trace so curiosity can return to an unanswered question. It must never
influence confidence, stability, or ranking (Increment 170).

## D27 — Recall is a candidate, never a belief

A `MemoryRetriever` supplies *recalled context* on the episode (never belief-evidence;
memory is not truth, Vision §22) and a *stance* (Memory / partial_memory) for the surface.
The seam is a domain Protocol with a deterministic lexical adapter as the offline default;
semantic/embedding retrieval swaps in behind the same Protocol. A question-shaped memory is
never recalled as knowledge. (Consolidated from the legacy STATUS log; Increment 172.)

## D28 — Reasoning is inference, not judgement

A `Reasoner` proposes a provisional answer as response context — never belief-evidence, never
confidence. Its output may be folded in as the *weakest* `EvidenceSource.INFERENCE` evidence
(weight 0.2, Increment 110) so an unconfirmed answer is held faintly and a later confirmation
matures it via `confirm()`. The executive is the decider (Vision §37, §38; D6). (Consolidated
from the legacy STATUS log.)

## D29 — Edge capabilities are earned and live-backed

`can_do(name)` is true only when a capability is *acquired* (a deliberate step, Vision §28) and
backed by a ready `CapabilityProvider`. Research/compare/reason/semantic-recall register providers
like the web seams, so one gate applies to every catalog capability — speech included (a silent
reasoner or lexical-only recall never reports `can_do`). (Consolidated from the legacy STATUS log.)

## D30 — Edge consultation is a deliberate, gated step

A `KnowledgeSource` edge (research → weaker `EXTERNAL_SOURCE`; compare → weakest `INFERENCE`) is
consulted only when the episode lacks real support and strong recall, at most once, and recorded in
the episode (`consulted`/`record_consult`). It gathers candidate evidence; empty/failed is honest
`None` (D6). Opt-in: an un-wired Jarvis never consults. (Consolidated from the legacy STATUS log.)

## D31 — Material-edge capabilities follow one seam

A domain Protocol at the edge + an infrastructure adapter (injectable io/net → offline tests,
env-gated root, `build_*() -> None` when unconfigured, D7/D8) + delegated `Jarvis` methods + a
`CapabilityProvider` in the registry. Calendar/tasks/notes/mail/speech/agent all follow it;
`can_do` reflects acquisition AND provider availability. (Consolidated from the legacy STATUS log.)

## D32 — Temporal stability is a distinct axis from confidence

`TemporalStability` never collapses into `Confidence` (Vision §10): both are [0,1] magnitudes but
different axes. Stability is span-based (`span / (span + reference)`, `STABILITY_REFERENCE = 30d`,
`LOW_STABILITY_THRESHOLD = 0.2`, tunable); the classical span term is always on. Count/recency
weighting on the *stability* axis was deferred to the opt-in decay policy at D32 time — that
deferral now covers only the *confidence* axis (`DecayingWeightingPolicy`, Vision §10, §22) and is
superseded for stability by **D36** (Increment 185), which adds the same two enrichments behind an
opt-in `TemporalStabilityProfile`. (Consolidated from the legacy STATUS log.)

## D33 — The decision registry is the single decision authority

`DECISIONS.md` is the only authoritative registry of load-bearing constraints. The legacy `STATUS.md`
adr-lite log is superseded — it stays as a mapping appendix with the obsolete numbering, never a
parallel registry. (Roadmap F1.) `scripts/check_decision_refs.py` enforces the corollary offline: every
`D\d+` token in live docs and `src/` resolves to an entry here; only `STATUS.md`, `INDEX.md` and the
self-describing `audits/` are exempt. New policy decisions land here, never in a second log.

## D34 — Documentation truth is machine-checked

Live docs must stay truthful and a machine must be able to verify it (roadmap F7):

- **Counts house rule** — no live doc may cite a suite total below the last published one
  (`scripts/check_docs_truth.py`, floor = last published total). The total is re-published on every
  increment; docs never sink it.
- **Symbols must exist** — every backticked name in `SYSTEM_TODAY.md` resolves in `src/`.
- **One HISTORICAL manifest** — `INDEX.md` lists historical docs; the manifest is machine-checked.
- **The broad-`except` audit is committed** — `scripts/check_broad_excepts.py` admits only honest,
  non-silent `except Exception` sites in `src/` (zero in domain/executive cognition); the swallow
  regression pins the two faces of honesty: a provider *failure* is loud on purpose (`provider_error`,
  never an emptied reply), a provider *refusal* is honest silence (`""`, Increment 157 guardrail).

Each gate runs offline in CI without a single third-party dependency (stdlib only).

## D35 — A fired task occurrence advances once, never re-fires

Decided tasks execute *by occurrence*: the `TaskScheduler` stores *what* to run
and *when*, and `run_due_tasks` (the `scheduled_execution` driver) sweeps every
currently-due enabled task exactly once through the same `approved=False`
earned-agency executor `tasks run` uses (D31 boundary). The store owns the
recurrence and the driver never sleeps or loops on its own:

- **Advance on record** — `record_run` (both the file and SQLite adapters) moves
  a cron task's `next_run` with `next_run_after(cron, run_at)`: strictly after
  the fire time, missed windows skipped, no catch-up backfill. After `tasks fire`
  a task is *not* due again until its next real window.
- **A one-shot fires exactly once** — a task without a cron never auto-due's after
  its fire; it stays enabled (re-armable via `update`/`enable`) but its
  `next_run` is cleared so the same occurrence can never be picked up twice.
- **An impossible schedule stops honestly** — if `next_run_after` finds no next
  occurrence (e.g. Feb 31), `record_run` clears `next_run` *and* disables the
  task, rather than fabricating a due window forever.
- **Snapshots, not streams** — the sweep captures `due_tasks()` once at the start,
  so each task runs at most once per call; one task failing (an `ok=False` result
  or a raised executor error) is recorded on that task and the sweep keeps going,
  with every honest outcome in the returned `ScheduledRun` report.
- **On-demand cadence** — the sweep is invoked (`tasks fire`) whenever a sweep is
  wanted; there is still no background thread or proactive wake loop (D8,
  AI_CONTEXT.md deferral).

## D36 — Temporal stability weighs count and recency behind an opt-in profile

The *stability* axis gains the two enrichments D32 deferred, opt-in and
default-behaviour-preserving (Increment 185):

- **One tunable knot** — `TemporalStabilityProfile` (`reference`, `low_threshold`,
  `count_sensitivity`, `recency_half_life`, and an injectable real-UTC clock)
  drives `derive_stability`. Its defaults (`count_sensitivity = 0.0`,
  `recency_half_life = None`) reproduce the classic span-only answer
  byte-for-byte, so a bare Jarvis computes identical stability numbers to before.
- **Count lift, asymptotic** — repeated support beyond the two observations
  needed for a span closes `count_sensitivity` of the remaining distance to 1 per
  extra observation (`1 − (1 − s)**(n − 2)`): a habit reads steadier than two
  isolated moments, never certain.
- **Recency fade, half-life** — a stale latest observation fades the whole term by
  `0.5 ** (age / half_life)`; just-observed or future-dated evidence (clock skew)
  does not fade. The clock is injected, so the domain stays deterministic and
  offline-testable.
- **Root-injectable, like the weighting policy** — `Jarvis(stability_profile=…)`,
  `set_stability_profile`, and `Jarvis.persistent/database` mirror
  `default_belief_policy`; the running executive's working beliefs, goal/action
  beliefs and companion traits all inherit it. Beliefs keep the profile they were
  formed with; nothing already derived is silently re-derived.
- **Read-time, never persisted** — the profile carries a clock, so it is not
  serialised into any store; reconstructed beliefs fall back to the classic
  span-only estimator unless re-injected at boot. D32's deferral still covers the
  confidence axis only.

## D37 — Delegation scopes bound a task's tools at the executor

Delegation (revised D1) runs a decided material task through the `TaskAgent`
seam. A **delegation scope** (Increment 186) narrows that hand-off to an explicit
toolset, so one scoped task can never wander into tools the caller did not
sanction:

- **Name-based, pure value** — `DelegationScope` is a frozen set of tool names
  (empty = allows nothing). The permission-ceiling factory `scope_at_most`
  derives a scope from a tool→permission map; `registered_scope_at_most` reads a
  live `ToolRegistry` for the caller.
- **Enforced at the executor, in both modes** — the decided-script
  `ToolRegistryTaskAgent.run_scoped` refuses an out-of-scope line truthfully; the
  model-driven `PydanticAiTaskAgent.run_scoped` removes out-of-scope tools from
  the toolset a model may choose (their absence is the honest enforcement). Both
  results are plain `TaskResult` accounts: an out-of-scope call is never folded
  into a fabricated success.
- **One seam, opt-in** — the scope rides `run_scoped`, an optional per-call
  argument of the existing `TaskAgent` seam, not a second delegation path. The
  protocol itself is untouched (`run_scoped` is a seam helper the scope-aware
  executors override); an agent that cannot scope simply runs the task. `scope_at_most`
  is a *convenience floor*, never a bypass: the registry's permission gate and `approved`
  keep their authority, and `approved=False` (earned agency) is unchanged.
- **Per-call, no shared state** — a scoped model-driven run builds its own agent
  over exactly the in-scope specs, so serving threads never mutate shared agent
  state; `run_scoped` is `None`-defaulted, so `delegate(task)` and `execute(task)`
  behave exactly as before.

## D38 — The lexical recall layer grows by vocabulary and policy, never by prompt

The bilingual concept vocabulary (Increment 187) is the *material* of offline
meaning recall (D18): it must keep growing with everyday language, and it must
grow without ever widening the false-positive surface that the matter-
preservation repairs (Increment 169) closed:

- **Deliberate, documented additions only** — every lemma, inflected form and
  synonym cluster is a hand-written vocabulary/policy decision with a test that
  pins it. Nothing is generated by an LLM, extracted from a corpus, or seeded
  from a prompt: the epistemic invariant (`a belief must never be stronger than
  the evidence`) applies to vocabulary too — a word maps to a concept because
  the policy says so, not because a model guessed it.
- **Spanish morphology is fold + explicit lexicon, not a stemmer** — accents
  fold (one entry covers "decisión"/"decision", "decidió"/"decidio"), and each
  inflected surface resolves to a *lemma that CONCEPT_MAP already carries*, so
  the concept assignment still comes from CONCEPT_MAP alone (ontology-neutral,
  like `_E_DROP_LEMMAS`). A Spanish stemmer is deliberately avoided: its
  `-ar`/`-er`/`-ir` ambiguity and stem-vowel yield would reopen matter-
  preservation surface for a marginal recall gain. Stem-changing roots
  (`pido`/`pide`, `consigo`/`consigue`, `elijo`/`elige`, `cuesta`/`cuestan`)
  are written out exactly.
- **The synonym channel is same-language, surface-only, never ontological** —
  `relatedness` gained a third channel of curated same-language clusters
  ("glad" meets "happy"); clusters never touch `CONCEPT_MAP`, `_signature`,
  topic identity or `valence`. Cross-language meeting happens only at the
  concept level. `relatedness` stays `max(surface, concept, synonym)`, each
  channel in `[0, 1]` — no cross-channel weighting or leakage.
- **Matter preservation stays supreme** — the repaired exclusions
  (create/estimate/receive/give) remain unmapped, and a newly-demonstrable
  false positive is deliberately excluded on sight: `creo` ("I believe") never
  resolves to BUILD even though `crear` does. A future vocabulary addition is
  the evidence that D38 is still being followed: every entry has a test proving
  it, and every exclusion has a test proving it stays out.
