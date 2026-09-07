# Jarvis — Implementation Status

Living document. Updated at the end of every increment. Single source of truth for
"where are we / what's next". No other progress docs — extend this one.

**North star:** `JARVIS_VISION.md` (repo root) is the objective every increment must move
toward. STATUS.md tracks *where we are*; JARVIS_VISION.md defines *where we are going*.
Every implementation decision must preserve the possibility of reaching that architecture
(Vision §41). Current code has no contradictions with the vision (verified 2026-09-04).

Last updated: 2026-09-07 (Increment 149)

---

## Git / commits

- Remote is the source of truth: `github.com/kossto82-ops/Annie` (branch `main`). Every increment
  ends with a commit **pushed** to that remote (local-only commits are not "done").
- Identity for this repo (local config only): `ksst <kossto82@gmail.com>`.
- Convention: **one commit per increment**, message in English, ending with the
  `Co-Authored-By: Claude Opus 4.8` trailer. The foundation (increments 1–5) is a single commit
  (`484fd49`); increments 6–103 are one commit each.
- **Numbering note (resolved 2026-09-04):** increments 104–110 (git, 2026-08-27/28 — memory
  recall, reasoning, embeddings, learning loop) were never logged here, and the calendar/tasks
  work was at first *misnumbered* as "Increment 104". This log now matches git for 104–110 and
  renumbers the post-110 capability sweep (notes/mail/calendar/tasks/speech/odysseus edges) as
  **Increments 111–134**, in chronological commit order. From 111 onward the "one labelled
  increment per commit" rule was relaxed: several related commits form one increment, listed
  below with their hashes.

## How to run

```bash
python -m pytest -q        # tests  (pythonpath=src is configured)
python -m ruff check .     # lint
python -m pyright          # type check (strict)
```

Entry point:

```python
from jarvis import Jarvis
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.enums.evidence_source import EvidenceSource

j = Jarvis()                       # ephemeral (in-memory)
# j = Jarvis.persistent("~/jarvis")  # durable: all memory on disk under one dir

# No evidence -> honest non-conclusion (Vision §37), not a fabricated answer:
j.think("Does my companion prefer simplicity?").result
#   "Insufficient evidence to conclude about: ... (confidence 0.00)."

# Grounded in evidence -> the decision reflects derived confidence:
ev = Evidence(content="chose the simpler design",
              source=EvidenceSource.USER_STATEMENT, weight=Confidence(0.9))
ep = j.think("Does my companion prefer simplicity?", evidence=[ev])
ep.result                          # "Concluded ... (confidence ...), grounded in N piece(s)..."
ep.working_belief.explain()        # provenance: why it concluded (Vision §8)
```

---

## Architecture map (what exists on disk)

```
src/jarvis/
  jarvis.py                              Jarvis composition root (public API, ~110 methods)
  nervous_system/nervous_system.py       subscribe / publish / dispatch (sync)
  observability/episode_trace.py          EpisodeTrace — cognitive events grouped by episode (Vision §26)
  executive/executive_controller.py      orchestrates one episode's lifecycle + recall/reason/consult seams
  infrastructure/                         stores, perceivers, models, edges, tools, adapters
  interface/                              command_center.py (pure brain) + server.py + console.html (web UI)
  domain/
    aggregates/                            CognitiveEpisode, HypothesisSet, CompanionModel
    conversation/                          intent (bilingual classify) + short-term ConversationContext
    entities/                              Belief, Hypothesis
    enums/                                 episode/evidence/attention/action/capability/permission/memory kinds
    events/                                domain + episode + evidence + belief + hypothesis + action + tool events
    perception/                            PerceptionSource, CompanionPerceptionSource, SpeechPerceptionSource
    reasoning/                             Reasoner Protocol + Inference
    repositories/                          Belief/Episode/Refutation/Capability repository Protocols
    retrieval/                             MemoryRetriever, NotesStore, CalendarStore, TaskScheduler,
                                           MailBox, TaskAgent, ExternalSource, ResearchSource
    services/                              evidence weighting, self-observation, curiosity, action advisor,
                                           goal reflection, reflection, hypothesis generation, association,
                                           capability scout/evaluator/gap-observer, knowledge source, model compare
    tools/                                 Tool Protocol + ToolRegistry + ToolPolicy
    value_objects/                          evidence/confidence/goal/action/… + recalled memory, inference,
                                           capability, note, email, calendar event, scheduled task, tool specs,
                                           retrieved document, research report, model run
  (Jarvis.persistent wires JSON stores: beliefs, episodes, companion, actions, reversibility,
   goals, subgoals, refutations, capabilities, needs + trace.jsonl + capability/edge config)
examples/                                8 runnable tours (main_loop, goal_arc, goal_parts, perceiving,
                                         conversation, resolving, reflecting, command_center)
tests/                                   75 test modules / 1002 tests mirroring the above
                                         (+ public-surface, console-asset & example guards)
```

Conceptual flow implemented:
`trigger (+ evidence) -> CognitiveEpisode -> ExecutiveController -> forms a working Belief,
grounds it in evidence -> decision reflects the belief's derived confidence -> completion`,
with belief + episode events dispatched through the NervousSystem at each step. The executive
can now also **recall** (memory seam), **consult** (knowledge-source edge), and **reason**
(reasoner seam) before deciding — each a candidate-evidence source, never a decision-maker.

---

## Increment log

### Increment 1 — cognitive vertical slice ✅ (2026-08-21)
- Scaffold (pyproject, src layout, tooling), Confidence VO, event hierarchy,
  EpisodeState, CognitiveEpisode aggregate, NervousSystem, ExecutiveController, Jarvis.
- Gates: ruff clean · pyright strict 0 errors · pytest 45 passed.
- Reasoning/reflection/decision are trivial deterministic transforms (placeholders).

### Increment 2 — evidence → belief primitives ✅ (2026-08-21)
- `Evidence` VO (weighted, supports/contradicts, provenance, observed_at),
  `EvidenceSource` enum, `Belief` entity, `derive_confidence`, `BeliefExplanation`,
  belief events (EvidenceAdded/BeliefStrengthened/BeliefWeakened).
- Core invariant is **structural**: a belief has no confidence setter; confidence is
  always `derive_confidence(evidence)` = supporting / (supporting + contradicting + 1).
  A belief can therefore never be stronger than its evidence, and evidence alone never
  reaches certainty (approaches but never equals 1.0). Realises Vision §7–§9, §18, §37.
- `belief.explain()` answers "Why do you believe this?" with the supporting/contradicting
  evidence — decision/belief provenance (Vision §8, §26).
- Gates: ruff clean · pyright strict 0 errors · pytest 63 passed.

### Increment 3 — contradiction as first-class + competing hypotheses ✅ (2026-08-21)
- `ContradictionDetected` event: contradicting evidence against a *held* belief (confidence > 0)
  is now recorded explicitly, not silently absorbed (Vision §18). Emission order on a held belief:
  `EvidenceAdded → ContradictionDetected → BeliefWeakened`.
- `Hypothesis` entity + `HypothesisSet` aggregate: hold multiple explanations for one observation,
  route evidence per hypothesis, `ranked()` by confidence, `leading()` returns None on empty **or a
  tie** — no premature collapse of uncertainty (Vision §17). `HypothesisCreated` event.
- `EvidenceAdded` generalised (`belief_id` → `subject_id`) and moved to `events/evidence_events.py`
  so belief and hypothesis share one event without either owning it.
- Gates: ruff clean · pyright strict 0 errors · pytest 75 passed.

### Increment 4 — epistemology wired into episodes ✅ (2026-08-21)
- `CognitiveEpisode` now owns a **working belief** (Vision §12): `form_working_belief`, `observe`
  (routes evidence to it), `working_belief`; `pull_events` also drains the belief's events.
- `Jarvis.think(trigger, evidence=())` and the executive form the working belief, ground it in the
  supplied evidence, and make the **decision depend on derived confidence**:
  none → "Insufficient evidence" (Vision §37); low → "Tentative"; ≥ threshold → "Concluded ...
  grounded in N piece(s)". `episode.working_belief.explain()` gives the decision's provenance.
- Belief events now flow through the same NervousSystem as the episode.
- Gates: ruff clean · pyright strict 0 errors · pytest 86 passed.

### Increment 5 — memory: beliefs persist across episodes ✅ (2026-08-21)
- `BeliefRepository` protocol (domain) + `InMemoryBeliefStore` (infrastructure) — first
  `repositories/` and `infrastructure/` modules (D8: real collaborator now exists).
- The executive **retrieves** a belief already held about a trigger and evolves it with new
  evidence (`episode.adopt_working_belief`), instead of forming a fresh one each time. Same
  trigger across episodes → same belief identity → accumulating evidence → rising confidence.
  This is continuity (Vision §3) — Jarvis no longer starts from zero.
- Memory ≠ truth (Vision §22): the store holds beliefs *with their evidence*; confidence is
  still always derived, never stored as an assertion. `Jarvis(beliefs=...)` is injectable;
  `jarvis.beliefs` is exposed.
- Gates: ruff clean · pyright strict 0 errors · pytest 93 passed.
- Commit `484fd49` (foundation, increments 1–5) pushed to `origin/main`.

### Increment 6 — temporal dimension: confidence vs. stability ✅ (2026-08-21)
- `TemporalStability` value object (distinct from `Confidence` — the two are different axes,
  Vision §10) + `derive_stability(evidence)` + `belief.stability`. Stability = supporting-evidence
  time-span / (span + `STABILITY_REFERENCE` of 30 days); < 2 supporting or simultaneous → 0.
- The executive now flags **overfitting** (Vision §11): a grounded conclusion whose stability is
  below `LOW_STABILITY_THRESHOLD` (0.2) carries a caution ("narrow time window — possible
  overfitting"). Same confidence + different time spread → different behaviour.
- Gates: ruff clean · pyright strict 0 errors · pytest 110 passed.
- Commit `4fbb2be` pushed to `origin/main`.

### Increment 7 — source-based evidence weighting ✅ (2026-08-21)
- `EvidenceWeightingPolicy` protocol + `SourceWeightingPolicy` (domain **service**, first `services/`).
  Turns an evidence's *raw* weight into an *effective* weight via a per-source factor, without
  mutating the evidence (provenance intact). Enacts Vision §11: explicit confirmation
  (`USER_STATEMENT` ×1.0) > repeated behaviour (`REPEATED_BEHAVIOR` ×0.8) > lone observation
  (`DIRECT_OBSERVATION` ×0.5).
- `derive_confidence(evidence, policy=DEFAULT_WEIGHTING)` uses effective weights; `Belief` carries an
  injectable `weighting_policy` (default keeps `USER_STATEMENT` behaviour unchanged). Same raw weight,
  different source → different confidence.
- Gates: ruff clean · pyright strict 0 errors · pytest 118 passed.
- Commit `35c7790` pushed to `origin/main`.

### Increment 8 — "why do you believe this?" narration ✅ (2026-08-21)
- `BeliefExplanation` now carries `stability` and a `narrate()` that renders the structured
  provenance into a plain-language self-explanation (Vision §26, §40): statement, confidence label
  + value, stability phrasing, the strongest supporting evidence *with its source*, any
  contradictions ("I may be wrong"), and an honest uncertainty note.
- `CognitiveEpisode.explain()` surfaces it, so `Jarvis().think(...).explain().narrate()` makes an
  episode explain its own decision; an ungrounded belief says it has no evidence (Vision §37).
- Gates: ruff clean · pyright strict 0 errors · pytest 123 passed.
- Commit `37cc371` pushed to `origin/main`.

### Increment 9 — episodic memory ✅ (2026-08-21)
- `EpisodeRecord` value object (episode_id, trigger, decision, working_belief_id, outcome,
  recorded_at) + `EpisodeRepository` protocol + `InMemoryEpisodeStore`. The executive records each
  completed episode; `jarvis.episodes.history()` exposes them in order.
- This is *memory of what happened*, distinct from beliefs (*epistemology*) — Vision §22. Groundwork
  for later self-modeling over past cognition (Vision §6, §31).
- Gates: ruff clean · pyright strict 0 errors · pytest 127 passed.
- Commit `7286c34` pushed to `origin/main`.

### Increment 10 — self-observation: a model of Jarvis itself ✅ (2026-08-21)
- `EpisodeRecord` gained `conclusion_confidence` (the working belief's confidence at completion) —
  a structured signal so self-observation measures history, not decision text.
- `observe_evidence_habit(history)` (domain service) forms a **belief about Jarvis** —
  "I tend to conclude without sufficient evidence" — grounded in one piece of evidence per past
  episode (ungrounded episodes support it, grounded ones contradict it). It **emerges from
  measurable history**, not fake personality, and is revisable like any belief (Vision §6, §31).
- `jarvis.observe_self()` surfaces it (None below a 3-episode minimum). `self_belief.explain().narrate()`
  makes Jarvis explain its own tendency.
- Gates: ruff clean · pyright strict 0 errors · pytest 134 passed.
- Commit `20455ec` pushed to `origin/main`.

### Increment 11 — curiosity: the first self-triggered episode ✅ (2026-08-21)
- `TriggerOrigin` enum (COMPANION | CURIOSITY) on `CognitiveEpisode` and `EpisodeRecord`. Episodes
  now know who started them (Vision §12).
- `wonder(self_belief)` (curiosity service) turns a confident self-belief into a `CuriosityImpulse`
  (a *recommendation* — an internal trigger + rationale, not an action; Vision §16, §28).
- `jarvis.feel_curious()` yields the impulse (None when healthy); `jarvis.pursue(impulse)` runs the
  first episode Jarvis initiates **on its own** (CURIOSITY origin), through the normal executive.
- Feedback loop broken: `observe_evidence_habit` judges only COMPANION episodes, so self-triggered
  curiosity episodes never inflate the very tendency they answer.
- Gates: ruff clean · pyright strict 0 errors · pytest 142 passed.
- Commit `06127c2` pushed to `origin/main`.

### Increment 12 — learning: a recognised tendency changes future behaviour ✅ (2026-08-21)
- Vision §20 ("if it does not change future behaviour, it has not learned"): when the executive
  produces an ungrounded conclusion, it consults its own self-model (`observe_evidence_habit` over
  prior COMPANION episodes). If Jarvis confidently believes it under-evidences its conclusions
  (≥ `LEARNED_HABIT_THRESHOLD` 0.5), the decision changes from a flat non-conclusion to an explicit
  "I have learned … I am asking for evidence before concluding".
- **Evidence-driven and reversible**, not a mode: it appears only while the self-belief is confident
  and fades as grounded episodes accumulate (verified: 3 ungrounded → learns; +3 grounded → reverts).
  Computed from history each decision, so the current episode never self-references.
- Gates: ruff clean · pyright strict 0 errors · pytest 145 passed.
- Commit `b77ac9b` pushed to `origin/main`.

### Increment 13 — a model of the companion ✅ (2026-08-21)
- `CompanionModel` aggregate: beliefs *about the companion* keyed by trait, each an ordinary `Belief`
  (confidence derived, revisable). `observe(trait, evidence)` evolves the matching belief;
  `belief_about`, `beliefs`, `summarise()` (plain-language account of each, Vision §5/§40).
- Never absolute truth (Vision §5, §18): a contradicting observation from the companion **weakens**
  the belief and keeps the prior evidence — it is not silently overwritten, and Jarvis says "I may
  be wrong". Reuses the whole belief/evidence/contradiction machinery.
- `jarvis.companion` exposed; `jarvis.observe_companion(trait, evidence)` records and dispatches the
  belief's events through the NervousSystem (D4: aggregate collects, orchestrator dispatches).
- Gates: ruff clean · pyright strict 0 errors · pytest 154 passed.
- Commit `45f6e17` pushed to `origin/main`.

### Increment 14 — the companion model informs cognition ✅ (2026-08-21)
- `CompanionModel.relevant_to(trigger)` returns a confidently-held companion belief whose trait
  appears in the trigger (≥ `_RELEVANCE_CONFIDENCE` 0.5; substring match — semantic matching deferred).
- The executive seeds the working belief from it: a confident companion belief enters `think()` as
  **standing evidence** (SYSTEM_OBSERVATION, weight = the belief's confidence, provenance kept) — never
  an override; caller evidence in the episode can still outweigh it (Vision §3, §5).
- A question about a trait Jarvis already believes concludes with higher confidence than a blank
  slate; an unrelated trigger or a weakly-held belief leaves cognition unchanged.
- Gates: ruff clean · pyright strict 0 errors · pytest 160 passed.
- Commit `b574652` pushed to `origin/main`.

### Increment 15 — durable persistence: Jarvis survives a restart ✅ (2026-08-21)
- `JsonBeliefStore` + `JsonEpisodeStore` (infrastructure): file-backed implementations of the
  existing `BeliefRepository`/`EpisodeRepository` protocols. Beliefs are serialised **with their
  evidence and provenance**; confidence and stability are re-derived on load, never stored (Vision
  §22). Selectable via `Jarvis(beliefs=..., episodes=...)`; the domain is untouched.
- Verified across two separate Python processes: run 1 records a belief+episode; run 2 (fresh
  interpreter, same files) remembers the episode and the belief keeps growing — real continuity
  (Vision §3, §21). Self-model and episode history also survive the round-trip.
- Belief reconstruction goes through the existing constructor (`_evidence=`), so no domain change;
  the weighting policy is not persisted (a reloaded belief uses the default).
- Gates: ruff clean · pyright strict 0 errors · pytest 167 passed.
- Commit `bfd6e41` pushed to `origin/main`.

### Increment 16 — persist the companion model ✅ (2026-08-21)
- `BeliefRepository` gained `all_beliefs()` (implemented by both in-memory and JSON stores).
  `CompanionModel` now stores its beliefs through an injected `BeliefRepository` (its own store)
  instead of a bare dict — so the model of the person persists with the same machinery (Vision §21),
  and the aggregate stays free of infrastructure (repository injected, no default in the domain).
- `Jarvis(companion_store=...)` selectable (its own file/namespace, distinct from working beliefs);
  default in-memory. Verified across two processes: a trait learned before a restart is still
  believed after it — and still informs cognition (Increment 14) post-restart (Vision §5).
- Gates: ruff clean · pyright strict 0 errors · pytest 168 passed.
- Commit `e042993` pushed to `origin/main`.

### Increment 17 — per-episode decision provenance (trace) ✅ (2026-08-21)
- Within an episode, the working belief's events now correlate to the **episode** (`observe` passes
  `correlation_id=episode.id` to `add_evidence`, which gained an optional `correlation_id`); outside
  an episode a belief still correlates to itself. So one act of cognition is one correlated process.
- `EpisodeTrace` (observability) subscribes to the NervousSystem and groups cognitive events by
  correlation. `jarvis.trace_of(episode)` returns the ordered trace: EpisodeStarted → EvidenceAdded /
  BeliefStrengthened / ContradictionDetected / BeliefWeakened → EpisodeCompleted — internal decision
  provenance (Vision §26), not exposed chain-of-thought.
- Gates: ruff clean · pyright strict 0 errors · pytest 172 passed.
- Commit `bd8320e` pushed to `origin/main`.

### Increment 18 — ask, don't guess: structured evidence requests ✅ (2026-08-21)
- `EvidenceRequest` value object (question, statement, confidence, needed). When the executive
  reaches a conclusion below `GROUNDED_CONFIDENCE_THRESHOLD` (ungrounded or tentative), it attaches
  one to the episode; a grounded conclusion attaches none.
- `episode.evidence_request` exposes the gap as structured, actionable data (Vision §16, §37) —
  not just prose in the decision string. Derived from the real gap, and absent once grounded.
- Gates: ruff clean · pyright strict 0 errors · pytest 175 passed.
- Commit `3490aab` pushed to `origin/main`.

### Increment 19 — reason with competing explanations ✅ (2026-08-21)
- `jarvis.consider(observation, options)` weighs competing explanations via a `HypothesisSet`
  (built in Increment 3, now reached by cognition). It routes each option's evidence, dispatches the
  set's events, and returns a `Deliberation`: the ranking (descending), the leading explanation with
  its derived confidence — or, on a tie / no evidence, **no leader plus an `EvidenceRequest`** for
  what would decide (Vision §17, §37: never collapse uncertainty prematurely).
- Gates: ruff clean · pyright strict 0 errors · pytest 181 passed.
- Commit `95b5e63` pushed to `origin/main`.

### Increment 20 — UnitInterval base (consolidation) ✅ (2026-08-21)
- `UnitInterval` frozen base holds the shared [0,1] validation (reject <0 / >1 / NaN / bool).
  `Confidence` and `TemporalStability` now derive from it but stay **distinct types** with their own
  helpers (`is_stronger_than`, `is_more_stable_than`), so the two axes are never conflated (Vision §10).
- Pure consolidation — no behaviour change: all 181 prior tests stayed green unchanged; 10 new tests
  pin the shared validation and type distinctness. Fulfils the rule-of-three deferral in D12/D18.
- Gates: ruff clean · pyright strict 0 errors · pytest 191 passed.
- Commit `9f59ac4` pushed to `origin/main`.

### Increment 21 — second self-observation: overconfidence ✅ (2026-08-21)
- `EpisodeRecord` gained `conclusion_stability` (the working belief's stability at completion; JSON
  store updated). `observe_overconfidence(history)` forms a belief about Jarvis — "I tend to be
  overconfident on thin evidence" — from *grounded* companion episodes: those concluded on
  temporally narrow (low-stability) evidence support it, well-spread ones contradict it (Vision §6, §11).
- `jarvis.observe_overconfidence()` surfaces it; `jarvis.self_beliefs()` aggregates every self-tendency
  Jarvis has enough history to judge (evidence habit + overconfidence). Reuses the ordinary
  epistemology, so self-beliefs stay provisional (D20).
- Gates: ruff clean · pyright strict 0 errors · pytest 197 passed.
- Commit `473c058` pushed to `origin/main`.

### Increment 22 — curiosity spans the whole self-model ✅ (2026-08-21)
- `feel_curious()` now considers every tendency in `self_beliefs()` (evidence habit + overconfidence),
  applies `wonder` to each, and raises an impulse for the **most confident** weakness above the
  curiosity threshold — or None (Vision §16, §28). Curiosity is no longer tied to a single tendency.
- Verified: an ungrounded-habit Jarvis is curious about under-evidencing; a grounded-but-thin Jarvis
  is curious about overconfidence; a genuinely healthy (grounded + time-spread) Jarvis feels none.
- Gates: ruff clean · pyright strict 0 errors · pytest 198 passed.
- Commit `1ff8706` pushed to `origin/main`.

### Increment 23 — temper overconfident conclusions from the self-model ✅ (2026-08-21)
- Symmetric with Increment 12: when the executive reaches a grounded-but-low-stability conclusion, it
  consults `observe_overconfidence` over prior COMPANION episodes. If Jarvis confidently believes it
  over-trusts thin evidence (≥ `LEARNED_HABIT_THRESHOLD`), the generic overfitting caution is reframed
  as learned self-correction ("I have learned I tend to be overconfident … holding this more
  tentatively"); otherwise the plain caution stands.
- Evidence-driven and reversible (D22): appears only while the overconfidence self-belief is confident,
  fades as grounded conclusions become better spread. Read over prior episodes only (no self-reference).
- Gates: ruff clean · pyright strict 0 errors · pytest 201 passed.
- Commit `9b7ba4d` pushed to `origin/main`.

### Increment 24 — deliberations are first-class episodes ✅ (2026-08-21)
- `EpisodeKind` enum (CONCLUSION | DELIBERATION) added to `EpisodeRecord` (JSON store updated).
  `executive.deliberate(observation, options)` now runs `consider` through the full episode lifecycle:
  EpisodeStarted…EpisodeCompleted, hypothesis events **correlated to the episode** (new `correlation_id`
  params on `HypothesisSet.propose`/`add_evidence` and `Hypothesis.add_evidence`), an episodic-memory
  record (kind DELIBERATION), and a `Deliberation.episode_id`.
- `jarvis.trace(correlation_id)` exposes a deliberation's ordered trace. Self-observation now filters to
  `kind == CONCLUSION`, so deliberations never pollute the belief-centric tendencies. Resolves D26.
- Gates: ruff clean · pyright strict 0 errors · pytest 204 passed.
- Commit `61f13fc` pushed to `origin/main`.

### Increment 25 — actions: thinking vs acting, outcome → learning ✅ (2026-08-21)
- `Action` value object (description, expected, confidence, reversible) — a declared intention with no
  side effect (Vision §27, §28: records only). `jarvis.act(...)` returns one.
- `jarvis.record_outcome(action, actual, met_expectation)` turns expected-vs-actual into `Evidence`
  (source ACTION_OUTCOME) feeding a belief *about actions of that kind* (its own `actions` store), so
  repeated matches build confidence and mismatches erode it (Vision §20). `belief_about_action(desc)`
  retrieves it with full provenance; an `ActionOutcomeRecorded` event is emitted.
- Gates: ruff clean · pyright strict 0 errors · pytest 211 passed.
- Commit `67e291c` pushed to `origin/main`.

### Increment 26 — graded autonomy: recommend a stance, never act ✅ (2026-08-21)
- `ActionStance` enum (SUGGEST | ASK_FIRST | WITHHOLD) + `ActionRecommendation` VO + `action_advisor`
  service. `jarvis.recommend_action(action)` derives a stance from the *learned* belief about that
  action kind (its track record) and reversibility: a confidently-learned reversible action →
  SUGGEST; the same learning but irreversible, or an unproven one → ASK_FIRST; one the record
  contradicts → WITHHOLD. It recommends only — performs nothing (Vision §28: autonomy is earned).
- Improves as Jarvis learns (Increment 25); reuses the epistemology (confidence + contradiction).
- Gates: ruff clean · pyright strict 0 errors · pytest 220 passed.
- Commit `2fd8ef4` pushed to `origin/main`.

### Increment 27 — persist action-outcome learning across restarts ✅ (2026-08-21)
- `Jarvis(actions_store=JsonBeliefStore(...))` now round-trips: action-outcome beliefs persist with
  their evidence, confidence re-derived on load (Vision §21, §22, §27). No domain or infra change —
  pure reuse of the existing `JsonBeliefStore` behind the `BeliefRepository` protocol.
- Verified across two processes: an action learned to work before a restart keeps the same
  `belief_about_action` confidence and the same `recommend_action` stance (SUGGEST) after it.
- Gates: ruff clean · pyright strict 0 errors · pytest 221 passed.
- Commit `495f620` pushed to `origin/main`.

### Increment 28 — one durable home: Jarvis.persistent(directory) ✅ (2026-08-21)
- `Jarvis.persistent(directory)` classmethod wires all four stores — beliefs, episodes, companion
  model, action learning — to JSON files under one directory in a single call, so a long-term
  companion is durable by default (Vision §3, §21). Pure composition over the existing JSON stores;
  the in-memory default constructor stays for tests and ephemeral use.
- Verified across two processes: everything (episodes, companion, action learning) survives a restart
  from one `Jarvis.persistent(dir)` call; a fresh directory starts empty.
- Gates: ruff clean · pyright strict 0 errors · pytest 223 passed.
- Commit `cb94f7a` pushed to `origin/main`.

### Increment 29 — third self-observation: prediction accuracy ✅ (2026-08-21)
- Refined the plan: **recency over-weighting was dropped** — Jarvis's confidence derivation is
  time-order-independent (only stability uses time), so there is no recency mechanism to detect;
  measuring it would be fake (D27). Instead added a genuinely distinct, measurable tendency from a
  different source: **predictive reliability** (Vision §31 "poor predictions").
- `observe_prediction_accuracy(action_beliefs)` reads the *action-outcome* beliefs (Increment 25):
  a kind whose predictions failed (confidence < grounded, contradicted) supports the belief "my
  predictions about my actions tend to be wrong"; a reliably-predicted kind contradicts it. Surfaced
  via `jarvis.observe_prediction_accuracy()` and folded into `self_beliefs()`, so curiosity weighs it
  for free (Increment 22).
- Gates: ruff clean · pyright strict 0 errors · pytest 228 passed.
- Commit `02734d5` pushed to `origin/main`.

### Increment 30 — introspection: Jarvis narrates itself from real state ✅ (2026-08-21)
- `jarvis.introspect()` returns a plain-language self-account assembled purely from existing state:
  its recognised self-tendencies (`self_beliefs()` narrated, strongest first), what it believes about
  its companion (`companion.summarise()`), and an honest note on how little it may still know
  (episode count). Personality **emerges from state, not a prompt** (Vision §29, §30, §40).
- Grounded: a fresh Jarvis says "I have not yet noticed any consistent tendencies" and "0 past
  episode(s)"; a seasoned one surfaces its strongest tendency + companion beliefs; nothing is asserted
  that isn't in the state. Pure read-model — no new state, no domain change.
- Gates: ruff clean · pyright strict 0 errors · pytest 232 passed.
- Commit `0bfc817` pushed to `origin/main`.

### Increment 31 — "why do you believe that about me?" ✅ (2026-08-21)
- `jarvis.explain_companion(trait)` returns the narrated provenance of one companion belief —
  supporting/contradicting evidence, confidence, and an honest "I may be wrong" when contested
  (Vision §5, §8, §26) — or a plain "I don't hold a view on that yet" for an unknown trait (Vision §37).
  Pure read-model over `companion.belief_about(...).explain().narrate()`; no new state.
- Gates: ruff clean · pyright strict 0 errors · pytest 235 passed.
- Commit `08a6fcf` pushed to `origin/main`.

### Increment 32 — documented public surface + runnable example ✅ (2026-08-21)
- README gained a **Vocabulary** section grouping Jarvis's public API by cognitive role
  (construct / perceive & reason / act & learn / self-model / companion / memory & provenance),
  every line copied from the real signatures (global Rule 24), nothing aspirational.
- `examples/main_loop.py` runs the whole loop end to end (reason → model companion → deliberate →
  act & learn → introspect); verified it executes (exit 0) and type-checks. Consolidation only —
  no behaviour change.
- Gates: ruff clean · pyright strict 0 errors · pytest 235 passed.
- Commit `cc5db3d` pushed to `origin/main`.

### Increment 33 — attention: not every trigger deserves full reasoning ✅ (2026-08-21)
- `Attention` enum (FULL | BRIEF) on `CognitiveEpisode`. Before the deep work, the executive assesses
  the trigger against what it already knows (`_assess_attention`): a working belief already confident
  (≥ grounded threshold) *and* no new evidence → **BRIEF** (answer from it, skip companion seeding /
  evidence integration / reflection); otherwise **FULL** (Vision §14). A real routing decision from
  real signals — not a simulated "energy".
- Side benefit: BRIEF avoids re-seeding a known trigger, so repeated identical questions no longer
  accrete spurious evidence. `episode.attention` exposes the choice. Existing behaviour unchanged
  (novel/evidence-bearing triggers still FULL).
- Gates: ruff clean · pyright strict 0 errors · pytest 238 passed.
- Commit `ddbeb78` pushed to `origin/main`.

### Increment 34 — a brief answer reads as brief ✅ (2026-08-21)
- A BRIEF episode's decision now reflects the routing: "From what I already understand about: … — I
  hold this with confidence X." derived from `episode.attention` (Vision §14, §40). FULL episodes are
  unchanged. Truthful: only a genuinely BRIEF (already-confident, no-new-evidence) episode gets the
  phrasing. No new mechanism — just surfacing Increment 33's routing in the answer.
- Gates: ruff clean · pyright strict 0 errors · pytest 240 passed.
- Commit `696e73a` pushed to `origin/main`.

### Increment 35 — contradiction the companion can see ✅ (2026-08-21)
- `jarvis.acknowledge_companion(trait, evidence)` records the observation and returns a conversational
  acknowledgement: when it contradicts a belief Jarvis actually *held*, "You have contradicted what I
  believed about … I may be wrong, so I am holding it less firmly now."; a first or consistent
  observation is just "Noted." The signal is the real `ContradictionDetected` event (Vision §18),
  which only fires when confidence was > 0 before — so a contradicting *first* observation is honestly
  not called a contradiction.
- Companion recording refactored to one path (`_record_companion` → belief + contradicted flag);
  `observe_companion` (returns belief) and `acknowledge_companion` (returns the message) are two views.
- Gates: ruff clean · pyright strict 0 errors · pytest 243 passed.
- Commit `4412328` pushed to `origin/main`.

### Increment 36 — contradiction becomes curiosity ✅ (2026-08-21)
- `feel_curious()` now, after weighing self-model tendencies, raises an impulse for a **contested**
  companion belief — one holding both supporting *and* contradicting evidence (Vision §16, §18). The
  tension itself is the signal, whatever the exact confidence, so a balanced (genuinely uncertain)
  belief is the most worth resolving. Self-tendencies keep priority; the impulse is a recommendation,
  not an action (Vision §28).
- A consistent (one-sided) companion belief raises none. Verified: consistent → no curiosity; after a
  contradiction → curiosity to "find out whether my companion really …".
- Gates: ruff clean · pyright strict 0 errors · pytest 245 passed.
- Commit `94c87ae` pushed to `origin/main`.

### Increment 37 — a single state snapshot ✅ (2026-08-21)
- `StateSummary` value object + `jarvis.state_summary()`: one immutable snapshot assembled from the
  existing read surfaces — episode count, confident self-tendencies, companion traits, action-outcome
  beliefs — each as `(statement, confidence)` (confidence always derived, Vision §22). Fresh Jarvis →
  all empty. Consolidation only; no new state.
- Refined the plan: action *stance* was dropped from the summary — a stance needs an `Action`'s
  reversibility, which is not persisted on the action-outcome belief, so it isn't derivable from the
  store; the summary reports the action beliefs' `(statement, confidence)` instead (D28).
- Gates: ruff clean · pyright strict 0 errors · pytest 249 passed.
- Commit `4ed92da` pushed to `origin/main`.

### Increment 38 — persist action reversibility; remembered stance ✅ (2026-08-21)
- Reversibility is now modelled as a **belief** ("The action 'X' is reversible") in its own store
  (`reversibility_store`, wired into `Jarvis.persistent` as `reversibility.json`), recorded on each
  `record_outcome`. So it persists like everything else and stays revisable (Vision §22).
- `jarvis.recommend_action_by_description(description)` derives a stance for a *remembered* action kind
  with **no live `Action`** — reading the learned outcome belief + reversibility belief — so a stance
  survives a restart (unblocks D28). Reversibility unknown → conservative (not reversible → ask first).
  Verified across two processes: a learned reversible action → SUGGEST after restart; unknown → ASK_FIRST.
- Gates: ruff clean · pyright strict 0 errors · pytest 252 passed.
- Commit `394eef1` pushed to `origin/main`.

### Increment 39 — remembered stance in the state snapshot ✅ (2026-08-21)
- `StateSummary.action_beliefs` replaced by `learned_actions: tuple[LearnedAction, ...]` where each
  `LearnedAction` carries description, derived confidence, and the recommended `stance` (from
  `recommend_action_by_description`, Increment 38). Finishes the D28 story: a stance for every learned
  action is now in the snapshot, and survives a restart.
- Description recovered by inverting the controlled `_action_statement` template (`_action_description`),
  not by parsing free text. Fresh Jarvis → empty. Consolidation only.
- Gates: ruff clean · pyright strict 0 errors · pytest 252 passed.
- Commit `2bb4962` pushed to `origin/main`.

### Increment 40 — goals: an episode has something it is toward ✅ (2026-08-21)
- `Goal` value object (statement + optional success criterion). `CognitiveEpisode.goal`;
  `jarvis.think(trigger, evidence=(), goal=None)` attaches it. When present, the decision names it
  ("Toward '…': …") as first-class provenance (Vision §12, §26: Goal → … → Decision). A recorded
  intent, not a planner/decomposition.
- Truthful: an episode without a goal has `goal is None` and an unchanged decision string.
- Gates: ruff clean · pyright strict 0 errors · pytest 258 passed.

### Increment 41 — the goal is remembered: provenance survives in episodic memory ✅ (2026-08-24)
- Increment 40 gave an episode a `goal`, but `EpisodeRecord` didn't capture it, so the purpose
  vanished from history. Now `EpisodeRecord` has an optional `goal: str | None` (the goal statement,
  or None); the executive records it from `episode.goal` when concluding. Provenance is now
  *remembered*, not just produced (Vision §26 Goal → … → Decision, §21 episodic memory).
- The JSON episode store (de)serialises `goal`; `_deserialise_record` uses `data.get("goal")` so
  older episode files without the key load as `None` (backward compatible). Verified: a goal-directed
  `think(...)` round-trips its goal across a `Jarvis.persistent(dir)` restart.
- Truthful & narrow: deliberation records (DELIBERATION kind) carry no goal — `consider()` takes none,
  so they record `None` via the field default. Only companion conclusions attach it today.
- Gates: ruff clean · pyright strict 0 errors · pytest 260 passed.

### Increment 42 — noticing a recurring goal: the first look back over its own purposes ✅ (2026-08-24)
- New domain service `goal_reflection.recurring_goals(history, *, minimum=3)` — a **count over episodic
  memory**, not a belief or a plan (Vision §26, §31 "what do I keep returning to?"). Counts goal
  statements across **companion-origin** episodes that carried a goal; returns `(goal, count)` pairs
  ordered by descending count (ties keep first-seen order), limited to goals seen ≥ `minimum`.
- `jarvis.recurring_goals()` exposes it read-only over `episodes.history()`. Because the goal now lives
  in episodic memory (Increment 41), Jarvis can, for the first time, look back over its own purposes.
- Truthful & non-asserting: it names what Jarvis has returned to — nothing about whether that is wise;
  judgement is a later, separate step. Reads existing records only (no new persistence). Curiosity
  (self-directed) episodes and goal-less ones are skipped. Exact-string match on the statement (D17
  simplification; semantic clustering deferred). `_MINIMUM_RECURRENCE = 3` mirrors the self-observation
  history floor (D20) so both read-models demand comparable evidence before naming a pattern.
- Gates: ruff clean · pyright strict 0 errors · pytest 265 passed.

### Increment 43 — a recurring goal becomes curiosity: the pattern moves Jarvis ✅ (2026-08-24)
- `feel_curious()` gained a third source, after self-tendencies and companion tension: when
  `recurring_goals()` surfaces a goal, it raises a `CuriosityImpulse` to turn inward on it
  ("Why do I keep returning to: {goal}?"), naming the recurrence count as its rationale (Vision §16,
  §26, §31). Same recognised-signal→impulse pattern as Increments 22 (self-tendencies) and 36
  (companion contradiction). Recommends only; `pursue()` runs it as a CURIOSITY-origin episode (§28).
- Priority order is truthful and settled (see D29): own reliability first, then companion tension,
  then recurring purpose — the goal impulse fires only when the earlier two are quiet.
- `CuriosityImpulse.prompted_by_belief_id` is now **optional** (`str | None = None`): this impulse
  arises from a pattern in memory, not a single belief, so it carries no belief id — the rationale
  still explains the why. (Same spirit as D9: not all cognition binds to one entity.)
- Gates: ruff clean · pyright strict 0 errors · pytest 267 passed.

### Increment 44 — recurring goals show up in the self-account ✅ (2026-08-24)
- `introspect()` now adds a "What I keep returning to:" section listing `recurring_goals()` with counts
  ("ship the parser (3 times)") after the self-tendency and companion lines; absent when none recur
  (Vision §29, §30). So a companion asking "what are you about?" hears Jarvis's own recurring purposes.
- `StateSummary` gained a `recurring_goals: tuple[tuple[str, int], ...]` field, populated from
  `recurring_goals()`; a fresh Jarvis's snapshot has an empty tuple (Vision §21). The machine-readable
  snapshot now carries the same fact as the narrated account.
- Pure read-model over existing state: nothing invented, nothing asserted as good — it names what
  Jarvis has returned to, and how often.
- Gates: ruff clean · pyright strict 0 errors · pytest 270 passed.

### Increment 45 — a goal can be reached: learning whether purposes are attainable ✅ (2026-08-24)
- `jarvis.mark_goal_reached(goal, reached=True)` records the outcome as evidence for a belief
  "The goal 'X' is reachable" in a new `goals` store — reused the action-outcome learning shape
  (Increment 25): reaches support, failures contradict, confidence derived and revisable (Vision §26,
  §27, §20). The goal's `success_criterion` (previously stored but never read) rides along as evidence
  context. The companion asserts the outcome; Jarvis does not evaluate the criterion itself yet.
- `jarvis.belief_about_goal(goal | statement)` queries it (None until an outcome is known).
  `Jarvis(goals_store=…)` is injectable; `Jarvis.persistent(dir)` now wires a 6th file `goals.json`.
  Verified: reachability confidence rises with reaches, falls with a failure, and survives a restart.
- Gates: ruff clean · pyright strict 0 errors · pytest 275 passed.

### Increment 46 — introspection distinguishes an unmet goal from a reachable one ✅ (2026-08-24)
- `introspect()`'s "What I keep returning to:" lines now annotate each recurring goal with what Jarvis
  has learned about reaching it (Increment 45): "— I have learned I can reach this (confidence 0.58)"
  when the reachability belief is grounded (≥0.5, mirrors D14), "— I have not reliably reached this yet
  (confidence …)" when it isn't, and no annotation when no outcome is known (Vision §26, §29, §30).
- The two goal facets now talk: a goal Jarvis keeps returning to *and* has learned it can reach reads
  as a different self-fact from one it returns to and keeps failing. Pure read-model over
  `recurring_goals()` + `belief_about_goal()`; nothing invented, confidence never overstated.
- Gates: ruff clean · pyright strict 0 errors · pytest 278 passed.

### Increment 47 — curiosity prefers a goal it keeps failing to reach ✅ (2026-08-24)
- `feel_curious()`'s recurring-goal branch (the third source, D29) now picks the sharpest tension: a
  goal Jarvis keeps returning to *and* has learned it keeps failing to reach (reachability belief
  known and confidence < 0.5) is chosen over one already learned reachable (Vision §16, §26, §31). The
  trigger names the tension — "Why do I keep returning to X without reaching it?".
- Since `recurring_goals()` is count-ordered, the first known-unreached goal is also the most recurrent
  among the unreached. Falls back to the most-recurrent goal when none are known-unreachable, so the
  Increment-43 behaviour is unchanged when no reachability has been learned.
- D29's overall priority order (self-tendencies → companion tension → recurring purpose) is untouched;
  this only refines *which* recurring goal is chosen inside the third slot.
- Gates: ruff clean · pyright strict 0 errors · pytest 280 passed.

### Increment 48 — pursuing a goal-curiosity is recorded toward that goal ✅ (2026-08-24)
- `CuriosityImpulse` gained an optional `goal: str | None`, set when the impulse is raised from a
  recurring goal (both the unreached-tension and the fallback branches). `pursue()` now attaches that
  goal to the self-directed episode's `Goal`, so wondering about a stuck goal leaves a trace *toward*
  it in episodic memory (Vision §16, §26, §27) — reusing the Increment 40–41 goal machinery, no new store.
- Truthful: this records that Jarvis *reflected* on the goal, not that it reached it — reachability
  still changes only via `mark_goal_reached`. And `recurring_goals()` counts only COMPANION episodes,
  so a self-directed pursuit does not inflate the recurrence count it was prompted by. A curiosity
  impulse about a self-tendency or the companion attaches no goal (`goal=None`).
- Gates: ruff clean · pyright strict 0 errors · pytest 282 passed.

### Increment 49 — self-directed reflection effort is visible per goal ✅ (2026-08-24)
- New domain read-model `goal_reflection.reflection_effort(history, goal_statement)` counts
  CURIOSITY-origin episodes recorded toward a goal — the mirror of `recurring_goals()` (which counts
  the COMPANION side). Exposed as `jarvis.reflection_effort(goal_statement)` (Vision §26, §31).
- `introspect()`'s unmet-goal line now appends "… and have turned it over N times" when the effort is
  non-zero, so Jarvis distinguishes a goal it keeps failing *and* keeps wrestling with from a neglected
  one. Effort ≠ progress: a high count beside low reachability is an honest picture, not a boast.
- Pure count over existing episodic memory; no new persistence. Companion `think(..., goal=…)` episodes
  are not counted as reflection effort (they are the recurrence side, not the self-directed side).
- Gates: ruff clean · pyright strict 0 errors · pytest 286 passed.

### Increment 50 — knowing when to stop: giving up on a stuck goal (for now) ✅ (2026-08-24)
- `feel_curious()`'s recurring-goal branch now suppresses a goal it has turned over to exhaustion
  without progress: an "open stuck" goal (learned unreachable, confidence < 0.5) is only raised while
  `reflection_effort()` < `_MAX_GOAL_REFLECTIONS` (=3). Once exhausted it yields to a less-wrestled
  stuck goal; if it is the only one, curiosity moves on (returns None or an earlier source)
  (Vision §16, §28, §37). See D30.
- Reversible "not right now", never "never": the fallback also skips exhausted stuck goals, but reaching
  the goal later (`mark_goal_reached` → reachability ≥ 0.5, no longer stuck) or — by design — a fresh
  recurrence clears the suppression and the goal can surface again. Verified end-to-end.
- Pure selection policy over existing read-models (`recurring_goals` + `belief_about_goal` +
  `reflection_effort`); no belief asserted, no new state, no persistence.
- Gates: ruff clean · pyright strict 0 errors · pytest 289 passed.

### Increment 51 — asking for help: the companion turns outward after honest self-effort ✅ (2026-08-24)
- `jarvis.stuck_goals()` lists the goals curiosity has given up on alone — learned-unreachable *and*
  reflected on to exhaustion (`_is_exhausted_stuck_goal`), ordered by recurrence (most-returned-to
  first). `jarvis.ask_for_help()` turns the most stuck one into a spoken request ("I keep returning to
  X but haven't found how to reach it on my own — can you help?"), or None when there is none.
- This is the natural counterpart to Increment 50: when `feel_curious()` falls silent on an exhausted
  stuck goal, silence is not the whole honest answer — a companion says so and asks (Vision §16, §18,
  §37). It only asks: asserts nothing, takes no action, sends nothing.
- Pure read-model over existing predicates; a goal under the effort threshold is not asked about, and a
  goal later learned reachable drops out of both `stuck_goals()` and `ask_for_help()`. Verified.
- Gates: ruff clean · pyright strict 0 errors · pytest 292 passed.

### Increment 52 — companion help moves reachability: closing the ask→answer→learn loop ✅ (2026-08-24)
- `jarvis.receive_help(goal, helpful=True)` takes the companion's guidance in as strong-provenance
  evidence (`USER_STATEMENT`, the highest source weight) on the goal's reachability belief, closing the
  loop `ask_for_help` opened (Vision §18, §26, §20). Genuinely helpful guidance can lift a goal Jarvis
  had given up on above the reachable threshold and so clear the suppression; the companion appears as
  the source in `explain().narrate()`.
- Truthful: help is evidence, not a guarantee. One answer is not proof (an exhausted stuck goal carries
  a prior failure, so a single help reaches only ~0.37; two lift it to ~0.54); `helpful=False` records a
  contradiction and does not lift it. Reachability stays derived, never set.
- Reuses the goals store and belief machinery — no new state, no persistence beyond the existing
  `goals.json`. Verified: sustained help clears `stuck_goals()`/`ask_for_help()`, unhelpful does not.
- Gates: ruff clean · pyright strict 0 errors · pytest 295 passed.

### Increment 53 — help that worked strengthens the companion model ✅ (2026-08-24)
- `receive_help(goal, helpful=…)` now also records a companion observation on the trait
  `HELPFUL_COMPANION_TRAIT` ("is helpful when I am stuck") via the existing `_record_companion` path —
  an ordinary, derived, revisable belief about the companion (Vision §5, §20). One helpful act now
  teaches two independent things: the goal is more reachable (about the goal) *and* the companion is
  helpful (about the companion). `helpful=False` contradicts the companion belief, exactly as any
  companion contradiction does (Increment 35).
- Not programmed gratitude — provenance-grounded relationship learning: the companion appears as the
  `USER_STATEMENT` source in `explain_companion(...)`/`introspect()`, confidence is derived, and a goal
  reached without any companion help leaves the companion model untouched.
- Gates: ruff clean · pyright strict 0 errors · pytest 298 passed.

### Increment 54 — a proven-helpful companion warms the ask ✅ (2026-08-24)
- `ask_for_help()` now consults `companion.belief_about(HELPFUL_COMPANION_TRAIT)`: when Jarvis
  confidently (≥0.5) believes this companion helps when it is stuck, the request is warmer ("You've
  helped me get unstuck before — … can you help again?"); otherwise it keeps the neutral phrasing
  (Vision §5, §18). Wording only — it still just asks, asserts nothing, takes no action.
- Earned, not assumed: the warmth comes from a confident *derived* companion belief built from real help
  received (Increment 53). No/low belief → neutral ask; reversible — if unhelpful guidance later weakens
  that belief, the ask cools back down. The goal named is still the most stuck one.
- Gates: ruff clean · pyright strict 0 errors · pytest 300 passed.

### Increment 55 — continuity checkpoint: a warmed relationship survives a restart ✅ (2026-08-24)
- Verified the companion-helpfulness belief (Increment 53) and the warmed ask (Increment 54) round-trip
  through `Jarvis.persistent(dir)` — the companion store is already wired to `companion.json`, so no
  code change was needed; this increment locks the guarantee with a regression test (Vision §3, §5, §21).
- The test builds the full chain in one persistent process (receive help → confident companion belief;
  grounded episodes + failure + exhausting pursuits → an exhausted stuck goal), asserts the warm ask,
  then opens a *fresh* `Jarvis.persistent` on the same directory and asserts the companion belief is
  still confident, the stuck goal still reconstructs from disk, and `ask_for_help()` is still warm.
- The relationship Jarvis has built now provably outlasts a process, exactly as its beliefs, episodes,
  actions, reversibility and goals already do. No new state; a continuity guarantee made explicit.
- Gates: ruff clean · pyright strict 0 errors · pytest 301 passed.

### Increment 56 — the goal arc, end to end: a runnable story + README ✅ (2026-08-24)
- New `examples/goal_arc.py`: one persistent Jarvis walks the whole Increment 40-55 arc — take on a goal,
  keep returning to it, learn it is stuck, wonder about it to exhaustion, ask for help, receive it, end
  reachable, and (on a fresh stuck goal) show the ask warmed once the companion has proven helpful —
  printing each turn. Deterministic (fixed evidence timestamps, no wall-clock branching); runs exit 0
  and type-checks clean (Vision §26, §40).
- README "Vocabulary" extended with the goal/relationship surface added since Increment 40
  (`think(..., goal=)`, `recurring_goals`, `mark_goal_reached`/`belief_about_goal`, `reflection_effort`,
  `stuck_goals`, `ask_for_help`, `receive_help`), copied from the real signatures (Rule 24); `persistent`
  now lists all six stores. Consolidation only — no behaviour change, all prior tests green.
- Gates: ruff clean · pyright strict 0 errors · pytest 301 passed.

### Increment 57 — a goal made of parts: decomposition as recorded structure ✅ (2026-08-24)
- `Goal` gained an optional `part_of: str | None` (the statement of a larger goal it is a part of;
  validated non-empty and not self-referential). Recorded structure, not a plan — no ordering, no
  execution (Vision §12, §26).
- `mark_goal_reached(child)` now, when the child names a parent, also credits the *parent's*
  reachability belief via `_credit_parent` — but *softly*: a `DIRECT_OBSERVATION` (weaker than reaching
  the whole directly, an `ACTION_OUTCOME`). Progress on a part is honest evidence about the whole; a
  parent is never "done" because a child is — its reachability stays derived from all its evidence
  (verified: three parts reached accrue 0.33 → 0.5 → 0.6, never jumping to certainty).
- Truthful & backward compatible: an unmet sub-goal contradicts the parent (does not raise it), a
  parentless goal creates no parent belief, and the parent credit persists in `goals.json` across a
  restart. No new store.
- Gates: ruff clean · pyright strict 0 errors · pytest 308 passed.

### Increment 58 — a goal's parts and how far along it is, made visible ✅ (2026-08-24)
- Sub-goal links are now queryable: `mark_goal_reached(child)` records the parent→child link in a new
  `_subgoals` store (a bookkeeping belief per link, template `_subgoal_statement`, parsed back the way
  `_action_statement`/`_action_description` already do). `jarvis.sub_goals(parent)` lists the recorded
  parts; `jarvis.goal_progress(parent) -> (reached, known)` counts parts reached at least once over all
  known parts (Vision §26, §30).
- `introspect()`'s recurring-goal line appends "(2 of 3 parts reached)" when a goal has known parts, so
  the decomposition (Increment 57) is finally visible in the self-account, not just felt in the parent's
  reachability. A goal with no parts carries no annotation.
- Truthful & continuous: "reached at least once" (a part reached then failed still counts), a count over
  recorded structure — not progress toward "done". `Jarvis.persistent` now wires a 7th file
  `subgoals.json`; progress and parts round-trip across a restart.
- Gates: ruff clean · pyright strict 0 errors · pytest 312 passed.

### Increment 59 — curiosity focuses on the specific part that blocks the whole ✅ (2026-08-24)
- When `feel_curious()` would raise an open stuck parent that has recorded parts, it now names the
  specific unreached part instead of the whole: "I've reached 1 of 2 parts of X; why can't I reach
  'Y'?" (Vision §16, §26, §31). `_first_unreached_part(parent)` finds the first part with no supporting
  evidence (consistent with `goal_progress`); falls back to the whole-goal phrasing when no part is
  identifiably unreached.
- The impulse still carries the **parent** `goal`, so pursuit and reflection-effort accounting accrue to
  the whole exactly as before — only *which stuck thing is named* sharpens. D29 priority, D30 give-up,
  and ask-for-help are all untouched.
- Gates: ruff clean · pyright strict 0 errors · pytest 314 passed.

### Increment 60 — asking for help names the blocking part ✅ (2026-08-24)
- `ask_for_help()` now names the specific unreached part when the most-stuck goal has one ("I keep
  returning to X — I've reached 1 of 2 parts but can't get past 'Y' …"), the same `_first_unreached_part`
  predicate curiosity uses (Increment 59). Falls back to the whole-goal wording when there is no such
  part (Vision §18, §26, §37). The narrower the ask, the more actionable the help.
- The warm/neutral variants (Increments 51/54) are preserved and composed with the part detail: a
  proven-helpful companion still gets the warmer opener, now with the precise blocker named. Still only
  asks — asserts nothing, takes no action; `receive_help` remains whole-goal (helping the part helps the
  whole).
- Gates: ruff clean · pyright strict 0 errors · pytest 316 passed.

### Increment 61 — help received on a blocking part credits that part directly ✅ (2026-08-24)
- `receive_help(goal, helpful=True)` now, when the goal has an identifiable unreached part (the same
  `_first_unreached_part` the ask named in Increment 60), credits *that part* too via
  `_credit_helped_part`: a `USER_STATEMENT` reach on the child's own reachability belief plus a reached
  entry on the sub-goal link, so the helped part stops being the blocker (Vision §18, §26, §20).
- `goal_progress` advances (e.g. 1/3 → 2/3) and `_first_unreached_part` moves on to the next part, so
  curiosity and the ask automatically retarget the *new* blocker. Verified end-to-end: help advances the
  part and, because the companion just proved helpful, the next ask is warm and names the next part.
- Truthful & narrow: only real help (`helpful=True`) advances a part, only the one part actually named,
  nothing asserted "done" (the parent's reachability stays derived, credited softly as before). A
  part-less goal is unchanged; unhelpful guidance advances nothing.
- Gates: ruff clean · pyright strict 0 errors · pytest 319 passed.

### Increment 62 — the decomposition arc, end to end: a runnable story + README ✅ (2026-08-24)
- New `examples/goal_parts.py`: one persistent Jarvis takes on a goal made of parts (one already done),
  curiosity fixes on the *specific* blocking part, the ask names it, and each `receive_help` advances
  exactly that part — `goal_progress` climbing 1/3 → 2/3 → 3/3 while the ask retargets the next blocker
  and warms as the companion proves helpful. Deterministic (fixed timestamps), runs exit 0, type-checks
  (Vision §26, §40). A truthful touch it surfaces: 3/3 parts reached yet the whole still reads "not
  reliably reached" because it was directly marked unreached — parts done ≠ whole done (§26).
- README "Vocabulary" extended with `sub_goals`/`goal_progress`, `part_of`, the part-naming ask and the
  part-advancing help; the examples list now points at all three tours. Consolidation only — no behaviour
  change, all prior tests green.
- Gates: ruff clean · pyright strict 0 errors · pytest 319 passed.

### Increment 63 — the first perception seam: raw observation → evidence ✅ (2026-08-24)
- New `PerceptionSource` Protocol (`domain/perception/`) — `perceive(observation: str) -> tuple[Evidence,
  ...]` — the boundary named in Vision §32: a capability provider *produces evidence* from the world but
  never decides. A deliberately dumb `KeywordPerception` (infrastructure, **NO LLM**) recognises a few
  certainty cues ("definitely" → weight 1.0, "maybe" → 0.3), flips polarity on a negation word, and turns
  the observation into one `USER_STATEMENT` evidence; an observation with no recognised cue produces
  nothing (honest silence, Vision §37).
- `jarvis.perceive(observation, trigger=None, goal=None)` runs the injected source and feeds the evidence
  into `think(...)`. `Jarvis(perception=…)` is injectable, so an LLM-backed perceiver drops in behind the
  same Protocol without touching the cognitive core (Vision §38). Verified end-to-end: a cue grounds a
  belief, a negated cue yields an honest insufficient conclusion, and unknown text stays silent. See D31.
- Boundary held strictly: the adapter only makes evidence; confidence is still derived, the executive
  still decides. This is the seam, not the intelligence — the first, smallest step toward closing the
  perception gap (the ~20–30% assessment's biggest missing piece).
- Gates: ruff clean · pyright strict 0 errors · pytest 328 passed.

### Increment 64 — perceived utterances shape the companion model ✅ (2026-08-24)
- `jarvis.perceive_about_companion(trait, observation)` bridges the Increment-63 perception seam to the
  companion model (Increment 13): the observation is turned into evidence by the `PerceptionSource`, and
  each piece is folded into `observe_companion(trait, …)` — so perceived praise builds a derived,
  revisable companion belief and a perceived (cued) denial contradicts it, exactly like hand-built
  evidence (Vision §5, §32). Returns the belief, or None when nothing is perceived.
- The lasting relationship knowledge now grows from language, not only from hand-constructed `Evidence`.
  Verified: cued praise raises the belief (0.66), a cued denial contradicts it (→0.49), and a cue-less
  observation leaves the model untouched (honest silence, §37).
- Boundary still strict (D31): perception only makes evidence; the companion model still derives
  confidence and can be contradicted. No new state, no persistence beyond the existing companion store.
- Gates: ruff clean · pyright strict 0 errors · pytest 331 passed.

### Increment 65 — a perception tour + README: language in, cognition out ✅ (2026-08-24)
- New `examples/perceiving.py`: one Jarvis `perceive(...)`s a grounding cue, a negated cue (honest
  insufficient conclusion), and a cue-less line (silence); `perceive_about_companion` accretes a
  companion belief then has it contradicted ("I may be wrong"); and a tiny custom `UppercaseIsCertain`
  `PerceptionSource` is injected to show a different perceiver drops in behind the same Protocol without
  the core changing (Vision §32, §38). Deterministic, runs exit 0, type-checks.
- README gains a "Perceive" group (`perceive`, `perceive_about_companion`, `Jarvis(perception=…)`),
  renames the old block to "Reason", and the examples list now points at all four tours. Consolidation
  only — no behaviour change, all prior tests green.
- Gates: ruff clean · pyright strict 0 errors · pytest 331 passed.

### Increment 66 — perception carries its provenance: auditable, not magic ✅ (2026-08-24)
- `KeywordPerception` now stamps the recognised cue into the `Evidence.context` it makes ("perceived via
  the cue 'definitely'"), and `narrate()` surfaces context on every evidence line ("… (user statement;
  perceived via the cue 'definitely')") via a shared `_render_evidence` helper. So a belief can explain
  *why* its perceived evidence carries the weight it does — perception becomes auditable (Vision §8, §9).
- Boundary unchanged (D31): still just evidence, confidence still derived. This makes the future
  LLM-adapter's contract explicit — a perceiver must report calibrated weight *and* provenance, never a
  decision. Reuses the existing `Evidence.context` field; no new type, no new state.
- Verified: perceived evidence carries a cue-naming context, it shows in the belief narration, and a
  cue-less observation still yields nothing.
- Gates: ruff clean · pyright strict 0 errors · pytest 333 passed.

### Increment 67 — a perceiver that yields several readings from one observation ✅ (2026-08-24)
- `KeywordPerception` now emits one `Evidence` per recognised cue (in order), each with its own weight,
  its own polarity from a nearby negation (a ±3-word window via `_negated_near`), and its own cue
  provenance — so "definitely right but maybe not ready" yields two readings (supporting 1.0 + contradicting
  0.3) that the belief honestly balances to ~0.43, instead of being flattened to one (Vision §8, §17).
- Tokenises on words (punctuation-stripped) so cue and negation matching is word-level, not substring;
  single-cue and cue-less behaviour is unchanged. Subjects are still not parsed — every reading bears on
  the one belief the episode is about; separating subjects is a smarter (LLM) perceiver's later job.
- The `PerceptionSource` contract already returned a tuple, so the seam needed no change — only the rule
  grew richer. Boundary still strict (D31): still just evidence, confidence still derived.
- Gates: ruff clean · pyright strict 0 errors · pytest 334 passed.

### Increment 68 — perceiving a stream: a short exchange grounds one belief ✅ (2026-08-24)
- `jarvis.perceive_all(observations, trigger=None, goal=None)` runs the `PerceptionSource` over each line
  of a stream, gathers all the evidence, and reasons over it in one `think(...)` — so a multi-line
  exchange grounds a single belief, weaker/contradicting lines pulling against stronger ones (Vision §3,
  §8). Cue-less lines contribute nothing; the trigger defaults to the first observation; an empty stream
  concludes honestly insufficient (§37).
- `jarvis.perceive_all_about_companion(trait, observations)` folds a stream about the companion into the
  lasting model, accumulating across lines. Verified: more cued utterances build more confidence, cue-less
  lines are skipped, and a mixed supporting/contradicting stream balances honestly (~0.59 on 2:1).
- Continuity is free (Increment 5): same-trigger perception reuses one belief. Boundary still strict
  (D31) — still only evidence, confidence still derived over the whole stream.
- Gates: ruff clean · pyright strict 0 errors · pytest 339 passed.

### Increment 69 — a conversation tour + README: an exchange grounds a belief that survives a restart ✅ (2026-08-24)
- New `examples/conversation.py`: a persistent Jarvis perceives a short multi-line exchange with
  `perceive_all(...)` — two supporting cues, a weaker doubt, and a cue-less line that is skipped —
  grounding one belief at ~0.59 with narrated per-cue provenance, plus a companion stream via
  `perceive_all_about_companion`. A *second session* (fresh `Jarvis.persistent` on the same dir) reopens
  the belief at 0.59 and a further exchange strengthens it to 0.69 — perception and continuity together
  across a restart (Vision §3, §40). Deterministic, runs exit 0, type-checks.
- README "Perceive" group gains `perceive_all`/`perceive_all_about_companion`; the examples list now
  points at all five tours. Consolidation only — no behaviour change, all prior tests green.
- Gates: ruff clean · pyright strict 0 errors · pytest 339 passed.

### Increment 70 — a perceived contradiction raises curiosity ✅ (2026-08-24)
- `feel_curious()` gained a fourth source (after self-tendencies and companion tension, before recurring
  goals — respecting D29): a *contested working belief* — one in the beliefs store carrying both
  supporting and contradicting evidence, e.g. from a mixed thing Jarvis perceived — raises an impulse to
  resolve the tension ("Resolve the tension in what I concluded about: X"), reusing the contested-belief
  curiosity shape (Increment 36) (Vision §16, §18, §32). `_contested_working_belief()` finds it.
- Perceived contradiction now *moves* Jarvis: a mixed exchange grounds a tentative belief and the tension
  pulls it to investigate; a purely-supporting exchange does not. The belief persists under its trigger,
  so the impulse survives the episode; `pursue()` runs it as a CURIOSITY episode. Verified end-to-end.
- No regressions: existing curiosity tests use support-only working beliefs (not contested), so the new
  check is transparent to them. Boundary unchanged — recommendation only, confidence still derived.
- Gates: ruff clean · pyright strict 0 errors · pytest 341 passed.

### Increment 71 — asking the companion to settle a contested belief, and resolving it ✅ (2026-08-24)
- `jarvis.ask_about(topic)` voices a genuine tension — when the working belief for `topic` is contested,
  it names both sides it has heard and asks which holds ("I have heard both X and not-X — which is it?"),
  or stays silent otherwise. `jarvis.resolve(topic, guidance, supports=True)` feeds the companion's answer
  as `USER_STATEMENT` evidence into that working belief, tipping it — derived, never set (Vision §18, §37).
- "Contested" is now a *live tension*: both supporting and contradicting evidence **and** confidence
  below the grounded threshold (`_is_contested`, shared by the curiosity check and `ask_about`). So enough
  guidance moves a contested belief past 0.5 and it is no longer contested — closing the loop
  hear-contradiction → curious → ask → resolve. Verified end-to-end; Increment-70 behaviour preserved
  (a 1:1 perceived belief sits at 0.33 < 0.5, still contested).
- Boundary held: `resolve` only adds evidence; confidence is re-derived. Reuses the beliefs store and
  the executive's `working_statement` (no format duplication).
- Gates: ruff clean · pyright strict 0 errors · pytest 345 passed.

### Increment 72 — a resolving tour + README: hear → curious → ask → resolve ✅ (2026-08-24)
- New `examples/resolving.py`: Jarvis perceives a self-contradicting exchange (grounds a contested belief
  at 0.33), the tension makes it curious, `ask_about(topic)` voices both sides it heard, the companion
  answers, `resolve(topic, …)` folds that in and tips the belief to 0.5, and a final `feel_curious`/
  `ask_about` shows the tension gone — printing each turn (Vision §18, §40). Deterministic, runs exit 0,
  type-checks.
- README "Perceive" group gains `ask_about`/`resolve`; the examples list now points at all six tours.
  Consolidation only — no behaviour change, all prior tests green.
- Gates: ruff clean · pyright strict 0 errors · pytest 345 passed.

### Increment 73 — consolidation checkpoint: the map matches the territory ✅ (2026-08-24)
- Audited the public surface: every documented `Jarvis` method is now listed in the README Vocabulary
  (added the one drift, `state_summary`); the architecture map in this file gained the files added since
  the perception/goals work (`perception/`, `keyword_perception`, `goal_reflection`, `part_of`, the extra
  persistent stores, the `examples/` dir) so it describes what is actually on disk (Vision §40, §42).
- Two regression guards, no new behaviour: `tests/test_examples.py` runs all six example tours as
  `__main__` (they can no longer rot silently), and `tests/test_public_surface.py` asserts every
  documented public method exists and is callable (a tripwire against silent signature drift).
- Truthful bookkeeping only — all prior tests stay green. The next big area is now a deliberate choice:
  an LLM adapter behind `PerceptionSource` (§32 — moves the "usable companion" needle most) or cognitive
  energy/cost budgeting (§15).
- Gates: ruff clean · pyright strict 0 errors · pytest 353 passed.

### Increment 74 — Connect: beliefs linked by shared evidence ✅ (2026-08-24)
- **First stage of the reflective cycle** (Remember → **Connect** → Reflect → Hypothesise → Challenge →
  Learn → Act), built *inside* Jarvis as its own capability, not a wrapper (Vision §1/§38 respected; D32).
  Beliefs were islands (exact-trigger keyed, D17); now `Connection` (a VO) records that two beliefs
  *rest on the same observation* — they share evidence by content (Vision §4, §31).
- `association.find_connections(beliefs)` (domain service) derives every pair sharing ≥1 evidence content,
  strongest (most shared) first; a belief grounded in no evidence connects to nothing. `jarvis.connections()`
  runs it over the beliefs store; `jarvis.related_beliefs(trigger)` filters to one belief's links.
- Purely derived, stores nothing, asserts nothing — `strength` is just the count of shared observations.
  Semantic association (same *subject* without literal shared evidence) is a deliberate later, richer step.
  This is the raw material Reflect/Hypothesise (next increments) will work on.
- Gates: ruff clean · pyright strict 0 errors · pytest 358 passed.

### Increment 75 — Reflect: noticing a load-bearing observation ✅ (2026-08-24)
- **Cycle stage 2** (Remember → Connect → **Reflect** → Hypothesise → …). Where Connect links two beliefs
  that share an observation, Reflect looks across the whole web and names a *pattern*: an observation that
  is **load-bearing** — one piece of evidence that two or more beliefs all rest on (Vision §19, §31).
- `Reflection` VO (observation + the beliefs it grounds + `load` + `describe()`); domain service
  `reflection.find_reflections(beliefs)` groups beliefs by shared evidence content and surfaces each
  observation grounding ≥2 beliefs, most load-bearing first. `jarvis.reflect()` runs it over the beliefs
  store. This is the genuine review the executive's §19 placeholder never did.
- Purely derived — it *notices*, never concludes: a finding is a structured pointer to the shared
  observation and the beliefs under it, asserting nothing. Empty when no observation grounds >1 belief.
  Verified: "the client moved the deadline up" surfaces as load-bearing for 3 beliefs; a one-off does not.
  Feeds autonomous Hypothesise (stage 3). Why it matters: if a load-bearing observation is wrong, every
  belief on it is in doubt at once — the natural input to Challenge (later).
- Gates: ruff clean · pyright strict 0 errors · pytest 363 passed.

### Increment 76 — Hypothesise: brewing an explanation from reflection ✅ (2026-08-24)
- **Cycle stage 3** (… → Reflect → **Hypothesise** → Challenge → …). Turns Reflect's *noticing* into a
  *proposed explanation*: the most load-bearing observation may be a **common cause** of the beliefs
  resting on it, against the null that it grounds them only by coincidence (Vision §17, §31).
- `hypothesis_generation.generate_hypotheses(reflections)` builds a `HypothesisSet` (reuses the §17
  machinery) over the top finding: seeds the common-cause hypothesis with one piece of evidence per
  belief resting on the observation (so its derived confidence rises with load), and stands the
  independence/coincidence null beside it with none. `jarvis.hypothesise()` runs it over `reflect()`,
  draining events (read-model, not dispatched).
- **Autonomous**: unlike `consider()` (companion-triggered), this brews from Jarvis's own reflection —
  the first time it forms an explanation of its *own* belief web unprompted. Proposed, never asserted;
  confidence derived; None when nothing is load-bearing. Verified: 3 beliefs on one observation → a
  common-cause hypothesis at 0.64 leading over the 0.00 coincidence null. Names what Challenge will test.
- Gates: ruff clean · pyright strict 0 errors · pytest 367 passed.

### Increment 77 — Challenge: naming (and acting on) what would refute the hypothesis ✅ (2026-08-24)
- **Cycle stage 4** (… → Hypothesise → **Challenge** → Learn/Act). A mind that only confirms its guesses
  is not thinking. `jarvis.challenge()` states the concrete falsifier of the leading hypothesis — "if
  '{belief}' would still hold without '{observation}', it is not the common cause" — as a `Challenge` VO
  (hypothesis, observation, falsifier, beliefs, `describe()`); None when there is no hypothesis to test
  (Vision §11, §17, §37).
- `jarvis.refute(observation, belief_statement)` records a counterexample: that belief would hold without
  the observation, so it **stops resting on it**. `find_reflections` now takes a `refuted` set and drops
  those pairs, so a refuted belief no longer counts toward the load. Refute enough and the load falls
  below two → `reflect()`/`hypothesise()`/`challenge()` all go empty: the common cause is **dethroned**,
  honestly, by removing what it claimed to explain. Verified end-to-end.
- Truthful & self-adversarial: Challenge asserts nothing false; refutation changes nothing about the
  belief itself, only that it no longer counts toward this pattern; everything stays derived and revisable.
  (Limitation: refutations are in-memory this increment — not yet persisted across restart.)
- Gates: ruff clean · pyright strict 0 errors · pytest 371 passed.

### Increment 78 — Learn: a surviving insight becomes a belief, and the loop closes ✅ (2026-08-24)
- **Cycle stage 5** (… → Challenge → **Learn** → Act). `jarvis.learn_from_reflection()` adopts a
  reflective insight that survived challenge: when `hypothesise()` still leads with a common-cause
  explanation confidently (≥ `_INSIGHT_CONFIDENCE` 0.5, i.e. not dethroned by `refute`), Jarvis `think(...)`s
  a new belief stating that common cause, grounded in the same per-belief evidence (Vision §20, §31).
- **The loop closes on itself.** The adopted belief enters the beliefs store like any conclusion —
  ordinary, derived, revisable — so the next Connect/Reflect/Hypothesise/Challenge can build on it, and it
  can itself be challenged later. Verified: 3 beliefs on one observation → Jarvis discovers their common
  cause and adopts it as a 4th belief (0.64); a dethroned or absent hypothesis learns nothing.
- Truthful: it adopts only what survived the self-adversarial step; no fabrication; the new belief's
  evidence content is distinct from the original observation, so it does not spuriously re-merge into the
  same cluster (no runaway feedback). The cycle Remember→Connect→Reflect→Hypothesise→Challenge→Learn is
  now a genuine loop; Act (graded autonomy, already built) wires in next.
- Gates: ruff clean · pyright strict 0 errors · pytest 375 passed.

### Increment 79 — reflect_cycle(): the whole loop in one honest action ✅ (2026-08-24)
- `jarvis.reflect_cycle()` runs Connect → Reflect → Hypothesise → Challenge → Learn end to end and returns
  a `ReflectiveCycle` summary VO (top reflection, leading hypothesis statement, challenge, learned belief
  statement — each None where the cycle stopped; `produced_insight`). It *calls* the existing stage
  methods in order — it does not re-implement them (Vision §31, §19).
- One method now expresses "Jarvis thinks about what it knows". Not purely a read-model: the Learn stage
  adopts a surviving insight as a belief (documented). On an isolated web every field is None and
  `produced_insight` is False; a dethroned hypothesis reports no learning. Verified end-to-end.
- This is the **seam for autonomy**: a future trigger (a curiosity source, or scheduled self-reflection)
  makes running the cycle a one-liner — the last ⬜ in Track A. The cycle itself is complete and green.
- Gates: ruff clean · pyright strict 0 errors · pytest 378 passed.

### Increment 80 — curiosity wants to reflect: the cycle becomes self-triggered ✅ (2026-08-24)
- **Track A complete.** `feel_curious()` gained a slot (after contested-working-belief, before recurring
  goals — D29 order preserved): an *un-mined* load-bearing observation — one `reflect()` surfaces that has
  no `"…is a common cause…"` belief yet — raises a `CuriosityImpulse` (`reflect_on` = the observation) to
  reflect on it (Vision §16, §31). `pursue()` runs `reflect_cycle()` first for such an impulse, so pursuing
  curiosity actually makes Jarvis think about what it knows.
- **Self-triggered**: Jarvis now notices *on its own* that several beliefs rest on one observation it has
  not understood, and wants to reflect — no companion prompt. Once the pattern is mined into a belief it
  goes quiet (no runaway loop; the learned belief's evidence is distinct, so no new pattern). Verified
  end-to-end: an unprompted reflect impulse → pursue → common-cause belief learned → curiosity silent.
- Truthful: only genuinely un-mined patterns raise it; still a recommendation; no LLM. Test-fixture
  cleanup: `_grounded_evidence` (test_goals) and one test_jarvis case shared evidence *content* across
  distinct beliefs by accident, which Reflect rightly noticed — made their content unique to restore intent.
- Gates: ruff clean · pyright strict 0 errors · pytest 381 passed.

### Increment 81 — a reflective-cycle tour + README ✅ (2026-08-24)
- New `examples/reflecting.py`: a Jarvis grounds three (grounded, well-spread) beliefs on one shared
  observation, then — unprompted — `feel_curious()` returns a reflect impulse, `pursue()` runs the whole
  cycle, and it adopts the common cause as a belief (0.64); curiosity then falls silent (mined). A second
  run shows `challenge()` naming the falsifier and two `refute()`s dethroning the hypothesis (Vision §31,
  §40). Deterministic (fixed timestamps), runs exit 0, type-checks; guarded by `tests/test_examples.py`.
- README gains a "Reflect (the cognitive cycle)" group (`connections`/`related_beliefs`/`reflect`/
  `hypothesise`/`challenge`/`refute`/`learn_from_reflection`/`reflect_cycle`); the examples list now points
  at all seven tours. Consolidation only — no behaviour change, all prior tests green.
- Gates: ruff clean · pyright strict 0 errors · pytest 381 passed.

### Increment 82 — Act: a learned insight reaches behaviour, the cycle is whole ✅ (2026-08-25)
- **Cycle stage 6, the last** (… → Learn → **Act**). `jarvis.act_on_insight()` connects the reflective
  cycle's output to behaviour: when Jarvis has confidently learned a common-cause insight, it proposes a
  graded action — "verify that '{observation}' still holds", reversible — and returns the stance from the
  existing `recommend_action` machinery, or None when there is no learned insight (Vision §27, §28, §31).
- Honest & earned: a brand-new verify action is **ASK_FIRST** (no track record yet); experience with it
  can later earn a SUGGEST. It only recommends — performs nothing (§28). An un-mined pattern (not yet
  learned) is not yet actionable → None; a dethroned/absent insight recommends nothing. Verified.
- Refactor: shared `_insight_trigger(observation)` used by both `learn_from_reflection` (to form the
  belief) and `act_on_insight` (to find it), so the insight's identity stays in one place.
- **Track A is now complete end to end: Remember → Connect → Reflect → Hypothesise → Challenge → Learn →
  Act, self-triggered by curiosity, every stage derived/revisable/auditable, no LLM.**
- Gates: ruff clean · pyright strict 0 errors · pytest 384 passed.

### Increment 83 — the reflective cycle's refutations persist ✅ (2026-08-25)
- Closes the Increment-77 limitation: `refute()` counterexamples were in-memory, so a dethroned
  hypothesis revived on restart while the beliefs it explained persisted. New `RefutationRepository`
  Protocol (domain) with `InMemoryRefutationStore` (ephemeral default) and `JsonRefutationStore` (8th
  persistent file `refutations.json`); `Jarvis.persistent` wires it (Vision §3, §21).
- `reflect()` reads `self._refutations.all()` exactly as before; `refute()` writes through the store. No
  change to the derivation. Verified: a hypothesis dethroned by two refutations stays dethroned across a
  `Jarvis.persistent` restart; a separate ephemeral Jarvis does not inherit another's refutations.
- Track D finish-off — everything Jarvis learns, including what it has *ruled out*, now survives a restart.
- Gates: ruff clean · pyright strict 0 errors · pytest 386 passed.

### Increment 84 — cognitive energy: an episode has a cost (Track C, §15) ✅ (2026-08-25)
- **Track C opened.** Thinking is no longer free: a new `EnergyCosts` VO (`full=3`, `brief=1`, method
  `for_attention`) charges each episode by its attention level (Increment 33's FULL/BRIEF). A private
  `Jarvis._run(episode, evidence)` runs the executive *and* charges the cost, so every episode-running
  path (`think`, `perceive`/`perceive_all`, `resolve`, `learn_from_reflection`, `pursue`) is counted.
- `jarvis.energy_spent()` reports the accumulated cost (0 for a fresh Jarvis); `StateSummary` gained an
  `energy_spent` field. Verified: a FULL episode costs 3, a BRIEF one 1, and the tally accumulates.
- **Config-driven, per the command-center requirement (Track E):** `EnergyCosts` is injectable at
  `Jarvis(energy_costs=…)`, not a buried constant — so a later command center can tune it at runtime.
- Made *visible* only — no budget yet. Next §15 step: a budget that makes attention *choose* BRIEF (or
  decline) under load. Deliberations (`consider`) are not charged yet (documented).
- Gates: ruff clean · pyright strict 0 errors · pytest 391 passed.

### Increment 85 — a cognitive-energy budget: a tired mind economises (Track C, §15) ✅ (2026-08-25)
- Cost is no longer just visible — it *constrains*. `Jarvis(energy_budget=…)` (config-driven, Track E) is
  a recoverable current-capacity meter. When it drops below the FULL cost, `is_conserving()` is true and a
  would-be FULL episode is answered **BRIEF** — the executive's `run(..., conserve=True)` downgrades it,
  but *only* when the episode carries no new evidence (dropping to BRIEF with evidence present would
  discard it; economise, never lose input) (Vision §15, §14).
- `energy_remaining()` reports the meter (None when no budget); `rest()` restores it (fatigue, not a hard
  cap); `introspect()` says "I am low on energy … thinking briefly to conserve" when conserving. With no
  budget set (default) behaviour is **identical to before**. Verified: budget 5 → FULL (−3) → conserving
  → BRIEF, BRIEF → `rest()` → full again; an evidence-bearing episode stays FULL even at budget 1.
- Honest, config-driven, no LLM. Next §15/Track-D steps optional; the strategic fork (Track B LLM vs more
  Track C/D) is below.
- Gates: ruff clean · pyright strict 0 errors · pytest 397 passed.

### Increment 86 — Track B design: the LLM→perception seam (no live API) ✅ (2026-08-25)
- **Track B opened as a design increment** — the seam, not a live call. Three pieces (all infrastructure):
  `LanguageModel` Protocol (`complete(prompt) -> str` — the single provider-swappable interface),
  `LlmPerception` (a `PerceptionSource` that asks a model to read an observation into claims and turns each
  into `Evidence`), and `ScriptedLanguageModel` (a canned-response stub proving the whole thing without a
  network). No new dependency; nothing above the seam knows which model it is (Vision §32).
- **§38 boundary enforced in `LlmPerception` (D33):** the model only *extracts candidate evidence* — the
  claims a text makes and how strongly it asserts each (not truth). Confidence-of-belief is still derived
  downstream; the executive still decides. Bad/empty/malformed output → honest silence (§37), never a
  fabricated reading; out-of-range weights are skipped, never clamped (mirrors D7).
- **Provider-swappable by injection (user requirement):** any real provider (OpenAI/Anthropic/Ollama)
  wraps its SDK behind `LanguageModel` and drops into `LlmPerception` unchanged; `Jarvis(perception=…)`
  is the only wiring. Verified end-to-end via the stub: two claims → a tentative belief at 0.26 with
  "perceived via language model" provenance; swapping the model flips supporting↔contradicting with no
  core change.
- Next Track B step: a config-driven registry/factory to pick the provider by name; then a real adapter.
- Gates: ruff clean · pyright strict 0 errors · pytest 406 passed.

### Increment 87 — an open provider registry: many LLMs + local SLMs, by config ✅ (2026-08-25)
- **Not limited to the big three (user requirement).** Key insight: nearly every provider — cloud and
  local — speaks the OpenAI chat API, so one generic `OpenAiCompatibleModel` (a `LanguageModel`) plus an
  extensible endpoint table covers them all. Adding a provider is a config entry, not code (Vision §32).
- `ProviderSettings` (provider, model, base_url, api_key, timeout, temperature) + a
  `language_model_registry`: `build_language_model(settings)`, `available()`, `register_endpoint`,
  `register_factory`. 16 providers out of the box — OpenAI, Groq, xAI/Grok, DeepSeek, Moonshot/Kimi,
  Mistral, Perplexity, OpenRouter, Together, **local Ollama, local LM Studio** — plus "openai-compatible"
  for any endpoint by `base_url`, and "scripted"/"stub" (the offline default). Unknown provider → clear
  error, never a silent fallback.
- **No network in code paths under test, no dependency:** the HTTP send is an injectable `Transport`; the
  default uses stdlib `urllib`, tests inject a fake and verify request shape (URL, Bearer header, model,
  messages) and reply parsing. Local SLMs send no auth header when keyless. §38 boundary unchanged (D33):
  the model still only returns text; `LlmPerception` turns it into evidence. Verified end-to-end via a
  fake transport → `LlmPerception` → a grounded belief, with zero network.
- Next Track B step: the FIRST real adapter is now just wiring the default `urllib` transport to a live
  endpoint — the increment that decides the concrete provider + where the secret lives + the CI story.
- Gates: ruff clean · pyright strict 0 errors · pytest 417 passed.

### Increment 88 — the first LIVE adapter: config from env, Groq-ready, CI-safe ✅ (2026-08-25)
- `env_settings`: `settings_from_env(environ=None)` reads `JARVIS_LLM_*` into `ProviderSettings`, and
  `language_model_from_env()` builds the model. The API secret lives ONLY in `JARVIS_LLM_API_KEY` (env),
  never in code/repo. **Default provider is `scripted`**, so with nothing set behaviour is unchanged
  (offline stub). A real provider without `JARVIS_LLM_MODEL` → clear error; local SLMs need no key.
- **Live smoke test is opt-in** (`tests/test_live_llm.py`, `skipif` unless `JARVIS_LLM_*` names a real
  provider + model): CI/offline stay green with **zero network** (verified: 422 passed, 2 skipped). When
  configured it does one real `complete()` round-trip and one `perceive` through `LlmPerception`.
- **First live provider = Groq** (user choice); env names = `JARVIS_LLM_*` (user choice). The generic
  `OpenAiCompatibleModel` + stdlib `urllib` transport actually reach it — no new dependency. §38 (D33) intact.
- **How to run it live (developer):**
  ```
  # Groq (cloud): get a key at console.groq.com, then
  JARVIS_LLM_PROVIDER=groq JARVIS_LLM_MODEL=llama-3.3-70b-versatile \
  JARVIS_LLM_API_KEY=gsk_... python -m pytest tests/test_live_llm.py -q
  # Local SLM (no key): with Ollama running,
  JARVIS_LLM_PROVIDER=ollama JARVIS_LLM_MODEL=llama3 python -m pytest tests/test_live_llm.py -q
  ```
- Gates: ruff clean · pyright strict 0 errors · pytest 422 passed, 2 skipped.

### Increment 89 — the Command Center: a local web control surface (voice + 3D face + live state) ✅ (2026-08-26)
- **Track E opens for real.** The developer wanted not a console but a *total* control center — talk to
  Jarvis, hear it speak, watch a 3D face while it does, tune it live. Decision **D34**: the core stays
  stdlib-only, so the rich surface lives where it costs nothing — a browser. A stdlib `http.server` serves
  one self-contained page + a JSON bridge; the browser supplies `speechSynthesis` (Jarvis speaks),
  `SpeechRecognition` (Jarvis listens), and a `<canvas>` point-cloud face (the 3D dots that move as it talks).
- `src/jarvis/interface/command_center.py` — the **pure brain**: `handle(jarvis, command, payload)` maps a
  command (`say`/`reflect`/`introspect`/`wonder`/`rest`/`energy_budget`/`state`) to a JSON reply by calling
  Jarvis's ordinary methods (it invents nothing — casual free-text with the keyword perceiver honestly
  answers "no evidence yet"; the LLM perceiver enriches it). `snapshot(jarvis)` is the live state. `route()`
  maps HTTP method+path+body → `Response` with **no socket**, so the whole contract is unit-testable.
- `src/jarvis/interface/server.py` — a **thin** `ThreadingHTTPServer` that only moves bytes; `create_jarvis`
  wires persistence (JARVIS_HOME) + the env-selected perceiver (LLM if `JARVIS_LLM_*` set, else keyword).
  `python -m jarvis.interface` (or `examples/command_center.py`) launches it. `console.html` is the UI.
- **One small core addition:** `Jarvis.set_energy_budget(budget|None)` — a real runtime parameter the
  control center tunes (Vision §15, §40), added to the public-surface guard.
- **Verified in a real browser** against the running server (Vision §7 gate): page served, point-cloud face
  painted (10k+ lit canvas pixels, zero JS console errors), `say` ran a real episode (episodes→1),
  `energy_budget` tuned remaining→4 live, `reflect` returned its cycle; `speechSynthesis` + mic present.
- Tests hermetic: `test_command_center.py` exercises `handle`/`route`/`snapshot` socket-free;
  `test_command_center_server.py` binds a loopback port only under `JARVIS_UI_SMOKE=1` (like the live-LLM
  test), so CI/offline stay green with zero network. §38 (D33) intact: no LLM in judgment.
- **How to run it:**
  ```
  python -m jarvis.interface           # then open the printed http://127.0.0.1:8765
  # with a real perceiver + persistent memory:
  JARVIS_LLM_PROVIDER=groq JARVIS_LLM_MODEL=llama-3.3-70b-versatile JARVIS_LLM_API_KEY=gsk_... \
  JARVIS_HOME=./.jarvis python -m jarvis.interface
  ```
- Gates: ruff clean · pyright strict 0 errors · pytest 442 passed, 3 skipped.

### Increment 90 — the face speaks: mouth synced to real word boundaries ✅ (2026-08-26)
- **Honest correction, then the real thing.** The plan said "route TTS through Web Audio (AnalyserNode)",
  but `speechSynthesis` output is **not capturable** by Web Audio in browsers — an analyser there reads
  silence. The truthful amplitude source is the utterance's own events: `SpeechSynthesisUtterance.onboundary`
  fires as each **word** is spoken. So the mouth now opens on real words (bumped per boundary, decaying
  between), gated by `onstart`/`onend` — genuine speech sync, not the old free-running jitter.
- All in `console.html` (no Python change to the running core): an `articulation` value bumped by
  `pulseWord()` on each boundary, a `pulsed` flag, and honest degradation — if a browser delivers no
  boundary events, the mouth falls back to a gentle continuous "talking" motion so it still animates.
  A `window.__face` hook (`pulseWord`/`setSpeaking`/`mouthEnv`) exposes the mechanism for verification.
- **Verified in a real browser** against the running server: mouth **closed at rest (0)**, **articulating
  0.37–0.50 while words fire** (`pulsed=true`, boundary path live), **decaying back to 0 on silence** —
  the mouth moves *with the words*. Zero JS console errors.
- **Tripwire test** (`tests/test_console_asset.py`): the JS mouth logic can't be pytest-run, so a guard
  asserts the console asset ships and keeps its speech-sync wiring (`onboundary`/`pulseWord`/`setSpeaking`/
  `articulation`/`window.__face`) — the analogue of the public-surface guard for the one browser asset.
- Gates: ruff clean · pyright strict 0 errors · pytest 444 passed, 3 skipped.

### Increment 91 — show the mind: a reasoning panel (provenance + step trace + reflective cycle) ✅ (2026-08-26)
- **The counter-weight to the voice and face: the surface now shows *grounds*, not vibes.** `say` carries
  the reasoning behind its reply — the working belief's provenance (`_provenance`: statement, derived
  confidence, and the evidence *for* and *against* with source + weight) and the episode's step trace
  (`_trace_steps`: started → weighed evidence for/against → belief strengthened/weakened → contradiction
  noted → concluded, from the real `CognitiveEvent`s via `trace_of`). A new **`explain` command** answers a
  stateless "why do you believe X?" over the held working belief. Both are pure `handle` branches, invent
  nothing, and are unit-tested socket-free.
- `console.html` gains a **reasoning panel**: after `say`/`explain` it renders the claim + a confidence bar,
  a "Grounds for" list and (when present) an "Against" list, and the step trace as a pill chain; after
  `reflect` it draws the Connect→Reflect→Hypothesise→Challenge→Learn chain, lighting the stages the cycle
  actually produced. A `window.__reason` hook exposes `renderReasoning`/`renderCycle` for verification.
- **Verified in a real browser** against the running server: a real cue phrase ("… definitely succeeded")
  filled the panel — Why / Grounds (1 evidence row) / step trace with started+weighed+concluded; a populated
  cycle lit all five stages; a for/against provenance rendered the confidence bar (62%), the "Against" row,
  and four step pills. Zero JS console errors. (An honest note: two `say`s of the *same* text update one
  belief, so Reflect correctly found nothing load-bearing — the panel truthfully showed all stages off.)
- **Tripwire** extended (`tests/test_console_asset.py`): guards `renderReasoning`/`renderCycle`/`Grounds
  for`/`window.__reason` so the panel wiring can't silently rot. §38 intact — the panel renders *derived
  state*, it adds no cognition.
- Gates: ruff clean · pyright strict 0 errors · pytest 449 passed, 3 skipped.

### Increment 92 — a perceiver switcher in the command center: see and change the live LLM ✅ (2026-08-26)
- **The join between the open registry (Increment 87) and the UI: the surface now shows *which* perceiver
  is reading the world, and lets you point it at any registered provider at runtime.** Jarvis gained a
  read-only `perception` property and a `set_perception()` seam (runtime swap of the capability provider —
  Track B; §32/§38). The perceivers self-report: `KeywordPerception.describe()` and
  `LlmPerception.describe()` (identity is optional metadata, never used in judgment).
- New `infrastructure/perceiver_factory.py` is the one place that maps a provider name → `PerceptionSource`
  and back (`describe` / `available_providers` / `perceiver_from_settings` / `build_perceiver`). The secret
  stays in the environment: `build_perceiver` (what the UI calls) takes only provider/model/base_url; the
  API key is read from `JARVIS_LLM_API_KEY`, never from the page. Building only constructs — no network.
- `command_center` snapshot now carries the live `perceiver` (`kind`/`provider`/`model` + the `available`
  list), and a new **`perceiver` command** switches it; a real provider without a model is a clear error,
  not a crash. `server.py` builds the initial perceiver through the factory so the readout reflects
  `JARVIS_LLM_*`. `console.html` shows the live perceiver in the header and adds a switcher card.
- **Verified in a real browser:** boot = keyword (header + populated select); switch to `groq`/`llama-3.3-70b`
  updated the header pill, the reply, and the snapshot; a real provider with no model showed a graceful
  error with no swap; switching back to `keyword` restored it. Zero JS console errors.
- Gates: ruff clean · pytest 462 passed, 3 skipped (added `tests/test_perceiver_factory.py` + `TestPerceiver`).

### Increment 93 — hand over the key: live Track B from the panel, secret to .env ✅ (2026-08-26)
- **The last mile to real language: the panel now takes an API key and runs the center against a live LLM.**
  The `perceiver` command accepts an optional `api_key`; new `infrastructure/llm_config_store.py` `stage`s it
  into the live process env (so the very next `build_perceiver` uses it) and `persist`s it to `.env`
  (atomic temp+replace, upsert-in-place, other lines untouched) so a restart resumes. `.env` and `.jarvis/`
  are git-ignored.
- **Write-only secret (§40 discipline):** the key flows page → local server → `.env` + process env and is
  **never** read back — not in the reply, not in any snapshot. `console.html` uses a masked `type=password`
  field that is cleared right after submit; the reply only confirms "Key saved", never the value.
- **Track B is now exercised end-to-end, not simulated.** With a real provider + key set from the panel,
  `say` runs the observation through `LlmPerception` (the model *extracts candidate evidence*, §38), those
  claims become `Evidence` (source `EXTERNAL_SOURCE`, "perceived via language model"), and the reasoning
  panel shows the LLM-extracted grounds behind a real belief. The keyword rule remains the offline default.
- **Verified in a real browser:** the masked key field switched to `groq`/`llama-3.3-70b`, the field cleared,
  the reply confirmed the save, the (temp) `.env` held `PROVIDER`/`MODEL`/`API_KEY`, and `/api/state` did
  **not** contain the key. (Offline validation used a dummy key; the live model call is the developer's to
  run with a real credential.)
- Gates: ruff clean · pytest 468 passed, 3 skipped (added `tests/test_llm_config_store.py` + key-path tests).

### Increment 94 — see Jarvis whole: a Tools & configuration drawer, unobscured face ✅ (2026-08-26)
- **The control cards no longer sit on top of the face.** The four overlay panels (Self-tendencies,
  Companion, Tune, Perceiver) moved out of the stage into a separate slide-in **Tools & configuration**
  drawer, toggled by a header ⚙ button (close via the ✕, the backdrop scrim, or Escape). The point-cloud
  face is now fully visible — "seeing Jarvis" is the default view; configuration is one click away.
- The chat column was narrowed ~8% (`main` columns `1.15fr 0.85fr` → `1.24fr 0.76fr`) to give the stage
  more room. The API-key field's CSS now includes `input[type=password]` so it sits flush with the other
  inputs. HTML/CSS/JS only — no core or command changes; the asset tripwire (`test_console_asset.py`) still
  guards the face/speech/reasoning wiring.
- **Verified in a real browser:** boot shows the unobscured face + narrower chat, header pill `keyword`,
  15 providers in the select; the drawer slides in with all four cards and a contained masked key field;
  toggling open/close works. Zero JS console errors.

### Increment 95 — stop leaking the machine label; honest reply for a claimless input ✅ (2026-08-26)
- **Bug: the internal working-belief identity ("Working conclusion about: …") leaked into every chat reply
  and the provenance panel** — a greeting came back as *I don't hold a view on "Working conclusion about:
  Hola Jarvis" yet*. The prefix is machine bookkeeping (D17 identity), never for the companion's eyes.
- Fix at the seam: `executive_controller` gets a `subject_of()` (inverse of `working_statement`, sharing one
  `_WORKING_PREFIX` constant); `BeliefExplanation.narrate(subject=…)` takes an optional display subject
  (default unchanged). The command center passes the natural subject in `_say`/`_explain` and cleans
  `_provenance.statement`, so no reply or snapshot ever shows the internal label.
- **Honest, not robotic:** an input with no extractable evidence (a bare "Hola Jarvis") now replies around
  the user's own words — *I can't ground a view on "Hola Jarvis" yet — there's nothing in it I can take as
  evidence. Tell me something with a claim in it and I'll reason from it* — still §37 honest silence, no
  invented view, and NOT scripted small-talk (the engine stays evidence-first, not a chatbot).
- **Verified (HTTP + browser):** greeting reply is clean and label-free; a grounded cue ("… definitely
  succeeded") narrates the natural subject with real grounds; `"Working conclusion about"` appears in no
  reply or provenance. New guard test `test_the_internal_working_label_never_leaks_to_the_user`.
- Gates: ruff clean · pytest 469 passed, 3 skipped.

### Increment 96 — the face reacts when you talk to it, with or without audio ✅ (2026-08-26)
- **Bug: the mouth only moved if `speechSynthesis` fired `onstart`/`onboundary`.** In a browser/context
  with no audible speech (common), `speaking` never turned on → the face sat static while Jarvis replied,
  reading as "it didn't react to me".
- Fix: a timer-driven `articulate(text)` owns the visible "talking" state for the length of a reply
  (word-count → duration, per-word pulses), called on every reply in `converse()` and `command()`. Real
  speech, when available, still layers exact word-sync on top via `onboundary` — but the reaction no longer
  depends on it. `speak()` no longer gates the visual on audio callbacks.
- **Verified in a real browser:** sending "Hola Jarvis" flips `window.__face.speaking` to true with
  `mouthEnv ≈ 0.36` during the reply, then settles — the mouth articulates whether or not audio plays.
- HTML/JS only; the console asset tripwire still guards the speech-sync wiring.

### Increment 97 — the relational channel: talking to Jarvis teaches it about *you* ✅ (2026-08-26)
- **The real gap behind "it doesn't know me": the chat only used ONE channel** (utterance → belief about a
  *topic*) and never touched the companion model, so conversation taught Jarvis nothing about the person.
  Now a turn feeds two channels — the epistemic one (world claims → beliefs) AND the **relational** one
  (what the utterance reveals about *you* → the companion model), Vision §5.
- New seam `domain/perception/companion_perception.py`: `CompanionPerceptionSource.read_companion(utterance)
  → (CompanionObservation{trait, evidence}, …)`. Infra: `SilentCompanionPerception` (offline default — no
  fabricated traits, §37) and `LlmCompanionPerception` (an LLM reads an utterance into stable facts about
  the person; §38 boundary held — it *extracts*, confidence is still derived and the belief stays
  contradictable). `Jarvis.note_companion()` folds each observation into the existing companion model
  (`_record_companion`), so it's an ordinary revisable belief.
- Wiring: `perceiver_factory` builds the companion perceiver from the same provider/model (secret from env);
  the `perceiver` command and `server.py` set BOTH perceivers together; `_say` runs both channels and, when
  it learned something, acknowledges it ("I'll remember this about you: …") and the Companion panel updates
  from the snapshot. Requires an LLM perceiver — with the keyword rule the relational channel stays silent.
- **Verified:** offline default learns nothing (honest); with a fake model, `note_companion` creates a real
  companion belief and the command center surfaces it in the reply + snapshot. New tests
  `tests/test_companion_perception.py` + `TestCompanionChannel`.
- Gates: ruff clean · pytest 479 passed, 3 skipped.

### Increment 98 — live LLM works end-to-end, and Jarvis speaks the companion's language ✅ (2026-08-26)
- **Track B goes truly live (real Groq), and three real bugs that blocked it are fixed:**
  1. **`.env` was written but never read** — a saved provider/model/key never resumed; every restart fell
     back to keyword. Added `llm_config_store.load_env_file()` (dependency-free; real env vars still win),
     called in `server.run()`. **This was the "it won't configure" root cause.**
  2. **No `User-Agent`** — Cloudflare-fronted providers (Groq) returned `403` (error 1010). The generic
     adapter now sends `User-Agent: Jarvis/1.0`.
  3. **The switch only persisted when a key was passed** — a bare model fix (or keyless Ollama) was lost on
     restart. `perceiver` now stages + persists on every switch (key still only-from-env).
- **Resilience:** an LLM/provider failure in `say` no longer 500s — it returns a clear, actionable message
  ("couldn't reach the language model … check provider/model/key in Tools"). `_parse` also tolerates a
  non-UTF-8 request body instead of crashing.
- **The voice speaks the companion's language (Vision §40, §38):** new `ResponseRenderer` seam —
  `IdentityRenderer` (offline: canonical reply unchanged) and `LlmResponseRenderer` (rephrases a *decided*
  reply in the language of the user's message, preserving every fact; model error → original reply). Built
  from the same provider, set on `Jarvis.voice` alongside the perceivers; `_say`/`_explain` voice their reply.
- **Verified live against Groq (openai/gpt-oss-20b):** *"Hola Jarvis, me llamo Roberto y me encanta la
  montaña"* → understood in Spanish, replied in Spanish (*"Recordaré esto sobre ti: se llama Roberto; le
  gusta la montaña"*), and learned `is named Roberto` / `likes the mountain`. Both channels + the voice work
  end-to-end.
- Gates: ruff clean · pytest 491 passed, 3 skipped (new `tests/test_response_renderer.py` + loader/UA/voice
  tests). Note: reply *scaffolding* is now localized; stored companion traits remain canonical English (panel
  shows English traits, chat is in-language) — a later polish.

### Increment 99 — teach Jarvis about you: profile ingestion, warm greeting, robust extraction ✅ (2026-08-27)
- **A deliberate way to "teach" Jarvis who you are** — the `learn` command reads a pasted profile through
  the relational channel in ONE pass into the companion model (Vision §5). The memory it builds lives in
  Jarvis (`companion.json`), NOT the model — the LLM only *extracts*; beliefs are revisable and survive a
  provider switch (verified: 58 beliefs persisted). New "Teach Jarvis about you" card in Tools.
- **Conversation feels like a companion, not a verdict engine:** `_say` now leads with what it learned about
  you ("Got it — I'll remember: …") for self-disclosure, narrates a grounded world-belief otherwise, and —
  when there's nothing to weigh — invites warmly instead of "I can't ground a view".
- **A warm, memory-grounded opening** replaces the robotic banner: the `greeting` command phrases a
  personalized hello from the companion model (by name, offering to resume a project) in the user's language;
  friendly default when offline. Verified live: *"¡Hola …! ¿Listo para seguir …?"*.
- **Robust LLM extraction (real Groq bugs fixed):** tolerant JSON parsing (strips ```json fences / prose);
  `max_tokens` (3072 default) so reasoning models don't return empty content on long inputs; optional
  `reasoning_effort` (`JARVIS_LLM_REASONING_EFFORT`, e.g. gpt-oss "low") for reliable content + far fewer
  tokens; a clear rate-limit (429) message. Ollama is supported/swappable but `qwen3:4b` is ~3 min/call on
  this CPU box — not viable interactively yet; `JARVIS_LLM_TIMEOUT` is configurable for slower local models.
- Gates: ruff clean · pytest 497 passed, 3 skipped.

### Increment 100 — NVIDIA NIM as a registered provider ✅ (2026-08-27)
- Added `nvidia` → `https://integrate.api.nvidia.com/v1` to the open registry, so NVIDIA NIM models (e.g.
  `nvidia/nemotron-3.5-lightning-30b-a3b`) are selectable like any other provider — key entered in the
  panel, never in code. One-line registry entry; the generic OpenAI-compatible adapter handles the rest.

### Increment 101 — polish: streaming replies, push-to-talk, persistent by default ✅ (2026-08-27)
- **Streaming replies.** The reply now arrives token by token instead of all at once. New seam:
  `LanguageModel.stream()` (OpenAiCompatibleModel parses SSE `data:` deltas — correctly skipping gpt-oss
  `reasoning` deltas and taking `content`), `ResponseRenderer.phrase_stream()` (Identity yields once; the
  LLM voice streams the translated reply, falling back to a single phrasing, then to the original — §37/§38).
  `command_center.stream_say()` yields `meta` (provenance/trace/learned/state) then `chunk`s then `done`;
  `server` serves it at `POST /api/stream/say` as newline-delimited JSON, flushed as it arrives. The UI
  reads the stream and fills the bubble live, with a non-streaming fallback. Verified live vs Groq: the
  bubble fills with the translated Spanish reply.
- **Push to talk.** The mic is now hold-to-talk (pointerdown starts, release sends), following the browser
  language (`navigator.language`) instead of hard-coded en-US.
- **Persistent by default.** `run()` defaults `home="./.jarvis"` so memory survives restarts unless
  `JARVIS_HOME` is explicitly empty (in-memory).
- Gates: ruff clean · pytest 505 passed, 3 skipped (new stream tests for the model, renderer, and
  `stream_say`); console asset tripwire intact; zero JS console errors in-browser.

### Increment 102 — per-provider API keys (no re-entry on switch) ✅ (2026-08-27)
- **Each provider's key is stored in its own slot** — `JARVIS_LLM_KEY_<PROVIDER>` (e.g. `JARVIS_LLM_KEY_GROQ`,
  `JARVIS_LLM_KEY_NVIDIA`) — so switching Groq → NVIDIA → local and back reuses each saved key without
  re-entering it. `llm_config_store.key_var()` / `resolve_api_key()` own the scheme; `env_settings` and the
  perceiver factory resolve the active provider's key (falling back to the legacy single `JARVIS_LLM_API_KEY`
  for old `.env` files). The panel still only ever writes the key server-side, never reads it back.
- Verified: staging a Groq key then an NVIDIA key keeps both; switching back resolves the stored key with no
  prompt. (The dev `.env` groq key was migrated to `JARVIS_LLM_KEY_GROQ`.)
- **Local Ollama left running for testing:** switched the active perceiver to `ollama` / `qwen3:8b` with a
  raised `JARVIS_LLM_TIMEOUT=300`. It works end-to-end (extracts traits incl. the name, replies in Spanish)
  but is ~50 s/call (~2.5 min/message) on this CPU — usable for testing; Groq is one click away in Tools
  (its key is saved) for speed.
- Gates: ruff clean · pytest 509 passed, 3 skipped (new per-provider-key tests).

### Increment 103 — per-provider model memory + fix Groq switch (untranslated replies) ✅ (2026-08-27)
- **Switching to Groq "didn't work": two causes, both fixed.** (1) The reply came back untranslated
  (English) because `reasoning_effort=low` had been dropped when testing Ollama — gpt-oss then spends its
  budget on hidden reasoning and returns empty content, so the voice fell back to the canonical English.
  Restored it (verified Ollama tolerates/ignores the param, so it can stay global). (2) The model field kept
  the previous provider's model (e.g. `qwen3:8b`) → Groq 404.
- **Model is now remembered PER provider** (`JARVIS_LLM_MODEL_<PROVIDER>`), mirroring the per-provider keys:
  `resolve_model()` + `model_var()`; the `perceiver` command recalls a provider's model when none is typed;
  `saved_models()` rides in the snapshot so the UI **auto-fills the model field when you pick a provider**.
  Switching Groq ↔ Ollama now restores each one's key AND model with no retyping.
- Verified live: `models: {groq: openai/gpt-oss-20b, ollama: qwen3:8b}`; a Groq turn replies in Spanish;
  switching back to a provider recalls its saved model. (The intermittent English seen while testing was
  Groq free-tier TPM under heavy probing, not a bug — `reasoning_effort=low` also lowers token use.)
- Gates: ruff clean · pytest 512 passed, 3 skipped (per-provider model tests + recall-on-switch).

### Increment 104 — long-term memory recall: MemoryRetriever seam + Memory/partial stances ✅ (2026-08-27)
- **The felt problem:** every question collapsed to "insufficient evidence" because the say path
  never retrieved relevant memory. New domain retrieval seam: `MemoryRetriever` Protocol +
  `RecalledMemory` VO + `MemoryKind` enum, with a deterministic offline `LexicalMemoryRetriever`
  (token overlap over beliefs/episodes/companion/goals). `CognitiveEpisode` carries recalled
  memories as *recalled context* (never belief-evidence — memory is not truth, Vision §22).
- The executive takes an optional `memory_retriever`; `_recall_into` applies a relevance floor,
  dedupes, and filters the current-topic belief. `Jarvis(enable_recall=)` composes a retriever over
  its own stores (opt-in; offline default unchanged, D8); the command center gains `Memory` /
  `partial_memory` stances before the ignorance fallback; `server.create_jarvis` turns recall on.
- Docs: `docs/claude/MEMORY_AND_REASONING_ANALYSIS.md` (diagnosis + evolution design).
- Gates: ruff clean · pyright strict 0 errors · pytest 539 passed.
- Commit `68cd901` pushed to `origin/main`.

### Increment 105 — "does it know me?" fixed: identity/companion recall ✅ (2026-08-27)
- Three real defects found by reproducing the name question end to end (commit `e90a09d`):
  1. The retriever matched only a belief's *statement*, ignoring the evidence that formed it — a
     trait worded "is named Raúl" was unreachable from "me llamo Raúl". Now matches statement +
     evidence contents.
  2. Past *questions* were recalled as if they were knowledge ("cual es mi nombre?" surfacing a
     prior "sabes mi nombre?"). Question-shaped memories are now skipped.
  3. Surface-token recall cannot bridge "quien soy?" → "is named Raúl". A self-referential question
     now consults the companion model directly (bounded, tunable heuristic; superseded by semantic
     recall, Increment 108).
- All identity phrasings now surface the name; a non-self world question does not dump companion
  traits. Full suite 539 passed; ruff + pyright clean.

### Increment 106 — reasoning: provisional answers for novel questions ✅ (2026-08-27)
- New domain reasoning seam: `Reasoner` Protocol + `Inference` value object (commit `f890ad9`).
  Infra: `SilentReasoner` (offline default, no inference) and `LlmReasoner` (opt-in; proposes a
  provisional answer via the `LanguageModel`; empty/failed → none).
- `CognitiveEpisode` carries an optional inference as response context (never evidence, never belief
  confidence). The executive `_reason_into` fires only when the belief is ungrounded AND no strong
  memory already answers. `Jarvis(reasoner=)` + `set_reasoner`; the command center adds an
  `inference` stance (clearly framed as provisional) with priority memory > inference >
  partial-memory > ignorance.
- Why: lexical recall cannot answer a genuinely novel question. The reasoner lets Jarvis think and
  answer, honestly labelled as inference, without the LLM becoming the epistemic judge (Vision §37,
  §38, D6). Offline default unchanged.
- Gates: ruff clean · pyright strict 0 errors · pytest passed.

### Increment 107 — fix perceiver switcher desync: the model now persists correctly ✅ (2026-08-27)
- Bug (commit `8bd39eb`): `renderPerceiver` reset the provider dropdown on every state render but
  left the model field untouched, so after picking a provider the (provider, model) pair desynced
  and a Switch overwrote the persisted per-provider model. Fix: reflect the live perceiver only when
  the user is NOT editing the switcher, and keep dropdown + model field in lockstep. Verified live.

### Increment 108 — semantic recall via embeddings: recall by meaning ✅ (2026-08-27)
- `TextEmbedder` Protocol + `OpenAiCompatibleEmbedder` (POST /v1/embeddings, injectable urllib
  transport) + `EmbeddingMemoryRetriever` behind the existing `MemoryRetriever` Protocol:
  embeds query + candidates, ranks by cosine, per-session vector cache, similarity floor, and a
  lexical fallback when the embedder is unreachable (degrade, don't break) (commit `126f48f`).
- Shared candidate gathering (`memory_candidates.gather_candidates`) keeps lexical and embedding
  retrievers in lockstep (evidence-aware, skips questions). `Jarvis.enable_embedding_recall` +
  `ExecutiveController.set_memory_retriever`; `build_embedder` reads `JARVIS_EMBED_*` (endpoint
  defaults to a local Ollama), independent of the chat provider.
- Why: lexical recall cannot bridge "¿quién soy?" → "is named Raúl" (no shared words). Embeddings
  recall by meaning — the fix for "I told it once and it can't find it". Still a candidate provider
  behind the same seam; the domain still decides (Vision §3, §38, D11).

### Increment 108b — calibrate the embedding similarity floor for bge-m3 ✅ (2026-08-27)
- Measured real bge-m3 cosines (identity queries ~0.46–0.67, unrelated ~0.29–0.37) and lowered
  `_MIN_SIMILARITY` 0.5 → 0.45 (commit `65e7ceb`). Verified live against local Ollama:
  "identidad del usuario" now recalls the name trait; "cómo cocinar pasta" recalls nothing.

### Increment 109 — self-diagnosing provider errors (status + hint) ✅ (2026-08-27)
- A provider failure showed only "HTTPError" (commit `1e173f2`). Now surfaces the HTTP status and
  what it usually means: 401/403 → key not accepted / model not enabled; 404 → wrong model id
  (NVIDIA ids need the `nvidia/` prefix); others → the status. Turned a real NVIDIA misconfig into
  an actionable message instead of an opaque one.

### Increment 110 — learning loop: remember reasoned answers, mature on confirmation ✅ (2026-08-28)
- **The felt problem: "it answers but forgets"** — every novel question was re-reasoned (commit
  `7961093`). Now: `EvidenceSource.INFERENCE` (weakest weight, 0.2): a reasoned answer is remembered
  as the weakest, clearly-sourced evidence on the working belief — held faintly ("the model says X,
  unconfirmed"), confidence still derived.
- `_reason_into` folds the inference as evidence and does NOT re-ask the model when an answer is
  already remembered; recall no longer echoes a prior identical-question episode back as "memory".
- `Jarvis.confirm(trigger, affirm)`: a companion confirmation adds strong `USER_STATEMENT` support
  (matures the answer to a grounded belief) or correction (weakens it) — derived, never set.
- Command center: a short "sí/no" confirms/corrects the last answer (confirmation stance);
  `grounded` now means real (non-inference) evidence. Verified offline end to end: reason →
  confirm → repeat is recalled as a grounded belief with provenance, without re-asking the model.
- Gates: ruff clean · pyright strict 0 errors · pytest 574 passed.

### Increment 111 — P0: complete the reflective cycle + crash-safe JSON persistence ✅ (2026-08-28)
- Audit (`docs/claude/audits/2026-08-28_auditoria_arquitectonica.md`) flagged two P0 issues; fixed
  (commit `570f24d`).
- **P0(a)** — `reflect_cycle()` ran only 4 of the 7 vision stages, contradicting its own docstring.
  It now runs Connect and Act end to end (Act after Learn, so it acts on the just-learned insight).
  `ReflectiveCycle` gains `connections` + `action` fields and `reached_action`.
- **P0(b)** — belief/episode/refutation stores rewrote their whole file with a truncating
  `write_text`, so a crash mid-write could corrupt memory. New `atomic_write_text` helper
  (temp + `os.replace`) makes every store flush crash-safe.
- Gates: ruff clean · pyright clean on touched files · pytest 579 passed.

### Increment 112 — P1: genuine Reflect stage + EpisodeFailed + durable EpisodeTrace ✅ (2026-08-28)
- `_reflect` was a no-op stub; it now reviews the working belief and records an `EpisodeReflected`
  event noting whether the conclusion is contested, well grounded, or thinly grounded — it notices
  only, belief and decision unchanged (commit `c7669c0`). `fail()` records `EpisodeFailed(reason)`,
  so a failed episode leaves a traceable mark.
- **Durable trace:** `EpisodeTrace` was in-memory only, so decision provenance vanished on process
  exit. `json_event_serialization` (de)serialises every CognitiveEvent per type (write strict, read
  tolerant); `JsonEpisodeTrace` is an append-only JSONL log replayed on startup; `EpisodeTraceSink`
  protocol lets the in-memory and JSON traces be swapped like the repositories; `persistent()`
  wires it as `base/trace.jsonl` (commit `680e507`).
- Gates: ruff clean · pyright strict · pytest 603 passed.

### Increment 113 — P2: forgetting — DecayingWeightingPolicy (opt-in, injectable clock) ✅ (2026-08-28)
- Top missing item from the audit: evidence should not count forever (Vision §10, §22). Implemented
  as an evidence-weighting policy — the same injectable seam that scales by source — so the
  epistemic core is untouched (commit `610037c`).
- `DecayingWeightingPolicy` composes over a base (source) policy and multiplies contribution by a
  recency factor that halves every half_life. Evidence itself is never mutated; the clock is
  injected (domain stays deterministic/offline); future-dated evidence is never boosted.
- `DEFAULT_WEIGHTING` does not decay, so nothing forgets unless a decaying policy is explicitly
  wired in. Wiring covers the world-belief line (`Jarvis(weighting_policy=…)` →
  `ExecutiveController` → `form_working_belief` + `Jarvis.persistent(dir, weighting_policy=…)`).
  Deliberate scope boundary: companion/goal/action/self-observation beliefs still use the default.
- Gates: ruff clean · pyright strict · pytest 613 passed.
- (Supporting, 2026-08-28: `fix(types)` cleared 8 pre-existing pyright errors in LLM adapters; the
  OpenAI-compatible adapter sends `stream:false` explicitly; docs added for OmniRoute infra + the
  Jarvis capability prompt/roadmap set under `docs/claude/prompts/`.)

### Increment 114 — conversation-first turn: not every message is knowledge ✅ (2026-08-31)
- **Bug:** Jarvis treated every user message as knowledge — greetings and small talk came back as
  belief narration, feedback became a belief, an instruction was stored as a trait. Root cause: no
  intent layer (commits `68d04a9`, `cd647f9`).
- New `domain/conversation/intent.py`: deterministic, offline, bilingual `classify()` into
  GREETING / SMALLTALK / FEEDBACK / INSTRUCTION / REMEMBER / STATEMENT. `_say_core` routes on
  intent: greetings, small talk, feedback and instructions are answered as conversation and never
  touch perception/memory/beliefs; only an explicit "remember that …" stores memory; a real
  statement/question keeps the full perceive+recall+reason path but replies like a person — no
  confidence/evidence/source narrated back (the belief still forms, inspectable via `explain`).
- A short-term `ConversationContext` on Jarvis records recent turns (separate from long-term
  memory, for follow-ups/pronouns); `_confirmation` narrowed to a *bare* yes/no so feedback is no
  longer a "correction". Verified live; `test_intent` + `test_conversation` added.
- Pending (honest): the LLM reasoner does not yet consume the short-term context; real instruction
  execution is unimplemented (earned agency) — instructions are acknowledged honestly, not acted on.
- Gates: ruff clean · pyright strict · pytest 636 passed.

### Increment 115 — the Internet capability: Agent-Reach behind ExternalSource ✅ (2026-09-01)
- `ExternalSource` capability so Jarvis can read/search the web when it decides external information
  is needed (commit `0bbb725`). Agent-Reach stays a capability: it only **retrieves** documents with
  provenance; Jarvis still reasons and never lets it write to memory/beliefs directly.
- Domain: `RetrievedDocument` VO + `ExternalSource` Protocol/ChannelStatus. Infra:
  `AgentReachSource` adapter (injectable transport → offline tests); `build_agent_reach_source()`
  returns None (offline) without the package. `jarvis.py`: `read_external` / `search_external` /
  `internet_channels` / `set_external_source`, auto-wired in `persistent()`. Command center
  `external` command. Docs: `INTERNET_AGENT_REACH.md`.
- Gates: ruff clean · pyright src clean · pytest 664 passed, 3 skipped.

### Increment 116-119 — Odysseus: capability acquisition, evidence-grounded needs, live edges, self-initiated growth ✅ (2026-09-01/02)
- **116** `capability acquisition — core model + scout` (`06cff25`): the domain `Capability` model,
  `CapabilityRepository`, and the deterministic `capability_scout` catalog.
- **117** `evidence-grounded needs and curiosity-driven acquisition` (`9f705fd`): `recognise_need`
  makes a need an ordinary belief whose confidence is derived from evidence (never asserted, Vision
  §8); `capability_evaluator` derives the stance (suggest / ask first / withhold, §28); curiosity
  raises a `CuriosityImpulse` and `pursue` turns it into acquisition — growth is earned, not assumed.
- **118** `live capability providers at the edge` (`eae5e4d`): a `CapabilityProvider` registry
  (`StaticCapabilityRegistry`) maps a capability name to the concrete adapter; `Jarvis.can_do(name)`
  is true only when a capability is acquired *and* live-backed — acquisition is real, not decorative.
- **119** `self-initiated capability gap discovery` (`b67a016`): `capability_gap_observation.detect`
  clusters the episode history by shared subject words and reports subjects Jarvis concluded about
  *ungrounded* more than once; `auto_scout_gaps` turns each gap into an evidence-grounded need and
  scouts candidates — wired into `reflect_cycle` (auto) and the `capability notice` command.
- Gates: ruff clean · pyright strict · pytest grew to ~720+.

### Increment 120 — seam support: reasoning and meaning-recall backed by the registry ✅ (2026-09-02)
- `ReasonerCapability` ("reason with a language model") and `SemanticRecallCapability` ("recall by
  meaning") are now mutable edge providers Jarvis flips when the live reasoner / embedding recall is
  active (commit `1d3c4f6`). A silent (offline) reasoner and lexical-only recall do **not** count,
  so `can_do` stays honest.

### Increment 121-122 — Tool Registry + deep research seam; blind model comparison ✅ (2026-09-02)
- **121** `tool registry and deep-research seam (Fases 0-1)` (`e48701d`): domain ToolSpec/ToolCall/
  ToolCallResult, `PermissionLevel`, `ToolPolicy` gating risky calls, `ToolRegistry` with
  `ToolCallRecorded` events, and sandboxed filesystem/echo tools. `ResearchSource` Protocol +
  `ResearchReport` VO, and a SearXNG research adapter (injectable transport, AGPL protocol reuse)
  as a self-contained edge source. Command center gains a `research` command.
- **122** `blind model comparison capability (Fase 2)` (`dc13042`): `ModelRun` VO + `ModelComparator`
  Protocol; a `RegistryModelComparator` over the existing provider registry gathers each model's
  blind reply to one prompt as candidate evidence (it never ranks, verdicts, or synthesises; a
  failing model raises honestly). Command center `compare` command, offline by default.

### Increment 123 — uniform earned-capability gate + a tool command ✅ (2026-09-02)
- Fases 0-2 audit follow-up (commits `fd4df6c`, `8b71135`): deep research and compare now register
  edge providers in the default registry, so `can_do`/`usable_capabilities` apply the same earned
  gate (acquired + live-backed, Vision §28) as the web capabilities. Scout templates complete the
  scout→acquire→use flow. Command center distinguishes not-wired from not-earned and gains a `tool`
  command (list/run) behind the permission gate. Clean-up: research `depth` bounded
  (`_MAX_DEPTH = 10`), `capability notice` gaps labelled `SYSTEM_OBSERVATION`, `FileSystemTool`
  validates `operation`.

### Increment 124 — the core decides when to consult Odysseus edges (Fase 3) ✅ (2026-09-02)
- New `KnowledgeSource` deliberate-consult seam (commit `2ceefa1`): when an episode cannot conclude
  from what Jarvis knows, remembers, or reasons, the executive may deliberately ask an edge to
  gather candidate evidence about the trigger. Adapters wrap deep research (`EXTERNAL_SOURCE`, 0.4)
  and blind model comparison (`INFERENCE`, 0.5). Runs before reasoning with the same guards as the
  reasoner (no real support, no strong recall, **one** consult per episode); the episode records
  consulted provenance (`consulted` / `record_consult`).
- Only gathers, never concludes (D6): confidence stays derived, an empty/failed edge is honest None.
  Opt-in: an un-wired Jarvis never consults; `persistent()` stays unwired.

### Increment 125-126 — explicit remember + auto-scouting from capability gaps ✅ (2026-09-03)
- **125** `an explicit remember grounds a full episode` (`fcb01a4`): "remember that …" runs a full
  episode (world belief + episode + confirmation loop), not just a companion trait.
- **126** `auto-scouting from capability gaps` (`5cb9a44`): the reflective cycle now auto-scouts
  capability gaps as part of its own pass; idempotent (a gap already recorded is skipped).

### Increment 127 — expand the capability catalog + revise D1 for edge delegation ✅ (2026-09-03)
- Catalog templates added for email, notes, calendar, tasks, agent (`13201e4`). **D1 revised:**
  Jarvis is still not an agent wrapper and cognition stays in the core, but it MAY now delegate
  **material actions** to an edge agent behind a domain seam — the agent executes concrete tasks and
  returns outcomes with provenance, never Jarvis's judgement (D6), never writing to beliefs/memory
  directly; governed by the controlled-autonomy policy + Tool Registry permission levels.

### Increment 128 — mail capability: seam + real IMAP/SMTP adapter ✅ (2026-09-03)
- `MailBox` Protocol + `EmailMessage` VO + `MailCapability` (`6b21151`), and the real
  `IMAPSMTPMailBox` adapter (list/read/send, injectable net → offline tests, env-gated)
  (`edd880d`). `Jarvis` gains the mail surface (`list_emails`, `read_email`, `send_email`).

### Increment 129 — delegate-to-agent capability + in-Jarvis task agent ✅ (2026-09-03)
- `TaskAgent` Protocol + `TaskResult` VO + `AgentCapability` (`e361c63`), plus an in-Jarvis
  adapter `ToolRegistryTaskAgent` that exposes Jarvis's own tool registry to the agent seam
  (`009854d`). `Jarvis.delegate` runs a bounded agent task and returns the outcome with provenance.

### Increment 130 — notes capability ✅ (2026-09-03)
- `NotesStore` Protocol + `Note` VO + `LocalNotesStore` adapter (list/get/create/update/delete/
  search, file-backed, injectable io for offline tests, env-gated via `JARVIS_NOTES_ROOT`)
  (`23e4e21`). `Jarvis` gains the notes surface, wired like the calendar/tasks pattern.

### Increment 131 — calendar capability ✅ (2026-09-04)
- `CalendarEvent` VO + `CalendarStore` domain Protocol + `LocalCalendarStore` (file-backed,
  env-gated via `JARVIS_CALENDAR_ROOT`) + a Google Calendar adapter (injectable transport)
  (`524c584`). `Jarvis` gains the calendar surface (`list/get/create/update/delete/events_in_range`).

### Increment 132 — task scheduler capability ✅ (2026-09-04)
- `ScheduledTask` VO + `TaskScheduler` domain Protocol (list/get/create/update/delete/enable/
  disable/due) + `LocalTaskScheduler` adapter (file-backed, env-gated via `JARVIS_TASKS_ROOT`)
  (`74c1cd1`). `Jarvis` gains the scheduled-tasks surface.

### Increment 133 — speech-perception seam ✅ (2026-09-04)
- `SpeechPerceptionSource` — the input mirror of the mouth: a speech utterance becomes candidate
  evidence the same way text does, behind the same `PerceptionSource` contract (`fd74da6`).
  (In-browser STT stays the command center's mic path; the seam makes it swappable.)

### Increment 134 — command center: dashboard home, sphere, integrated capability surface ✅ (2026-09-04)
- Dashboard redesign: a point-cloud **sphere** stage, separate capability/tool panels, edge sources
  wired and integrated (calendar/tasks/speech/capability/tool) (`cc04875`, `b518df5`); the full
  capability catalog is surfaced in the snapshot annotated with status
  (ready/acquired/proposed/rejected/available) so the panel is never empty (`cac3c43`); the sphere
  stays visible while chatting (`c89d725`); an apostrophe in the reasoning placeholder that broke
  the inline script is escaped (`2ce21d7`); grid overflow fixed (`369a2ca`); professional UX
  overhaul — layout scale, icons, sphere (`61e4214`).
- Gates (HEAD): ruff clean · pyright (errors only in newer tests, see debt below) ·
  pytest 1002 passed, 3 skipped.

### Increment 135 — audit gates reset ✅ (2026-09-06)
- Ruff clean + pyright strict with **0 errors** across `src` and `tests` (`036cc86`): import-order,
  line-length and typing fixes in newer tests, plus a `knowledge_source.py` typing fix. Closes the
  "gates not clean at HEAD" debt from Increment 134.

### Increment 136 — persist capabilities/needs and provision live-backed at boot ✅ (2026-09-06)
- `Jarvis.persistent()` now persists capabilities, capability needs and their stats
  (`JsonCapabilityStore`), and at boot provisions every persisted capability whose provider is live
  (`fa7e935`); the server wires the store in.

### Increment 137 — accept files and edit shared project folders ✅ (2026-09-06)
- `DocumentStore` domain seam over raw bytes (list/read/write/remove) + `LocalDocumentStore`
  (flat names, injectable io, offline default via `build_document_store`) (`06b7c6e`).
- Catalog gains "work with files" and "edit project files"; `DocumentsCapability` /
  `ProjectFilesCapability` registered in `build_default_registry`.
- `Jarvis.list/read/write/remove_document`, `set_documents_store`, `set_project_files`;
  `documents` command (list/read/save/remove, text|b64); snapshot exposes `documents`; UI gets the
  "Documentos" panel; `JARVIS_PROJECT_ROOTS` feeds the `FileSystemTool` as `project:` roots.

### Increment 138 — reason with conversation context and recall stored documents ✅ (2026-09-06)
- Episodes now thread the short-term `ConversationContext` into reasoning:
  `think(… conversation=…)` → `executive run` → `_reason_into` → `infer(trigger, recalled, conversation)`
  (`84e22cf`). Closes the Increment-114 gap: the reasoner receives recent turns in **both** paths
  (`say`/`reason` conversationally and `think`/episode).
- Documents ride **recall**: `MemoryKind.DOCUMENT`, `DocumentHit` VO,
  `DocumentStore.search_documents` (lexical; binary findable by name only, snippet never quotes
  opaque bytes — D37), and `DocumentMemoryRetriever` wrapping any base retriever (keeps the lexical
  offline default; joins the embedding retriever when enabled).

### Increment 139 — documents search command + UI ✅ (2026-09-06)
- `documents search` action (`query` + optional `limit`, structured `hits` in the reply) and a
  search box in the Documentos panel (`7c943c2`).

### Increment 140 — surface companion documents in chat recall ✅ (2026-09-06)
- `say` splits recalled hits into documents vs memory by `MemoryKind.DOCUMENT`; a matching file is
  offered honestly ("I have a file that bears on that — api.md…") (`18ce7e7`). Any reply with
  relevant documents carries a `documents` chip list rendered in the stream and fallback, and the
  chip double-check reads the file.
- Gates (HEAD): ruff clean · pyright strict 0 errors · pytest 1066 passed, 3 skipped.

### Increment 141 — live-tunable cognition thresholds ✅ (2026-09-07)
- A single validated `CognitiveKnobs` value object (`grounded_confidence`, `insight_confidence`,
  `max_goal_reflections`, defaults 0.5/0.5/3) replaces the module constants and their domain mirrors
  (`8392af9`). Injectable at `Jarvis(cognitive_knobs=...)`, swappable at runtime via `knobs()` /
  `set_knobs()`; observers and the capability-gap pass it as `knobs=...`.
- Command center gains a `tunables` action (report/set, unknown knob and out-of-range are honest errors)
  and a "Cognition — thresholds" card with sliders in the settings panel; snapshot exposes `tunables`.
- Discipline: thresholds are now injectable/config-sourced, never a module constant (D7).

### Increment 142 — folder-aware documents store ✅ (2026-09-07)
- `LocalDocumentStore` accepts sandbox-safe nested names (`docs/api.md`) instead of flat-only ones
  (`c7e5d51`): bounded relative paths, backslash normalisation, real-disk `rglob` listing and parent-dir
  creation; every escape (absolute, drive, `.`/`..`, empty segments) stays rejected at the store and the
  surface. The `DocumentStore` seam contract notes the bounded-relative naming.
- `documents save` gains an optional `path` folder (`docs/v2`), and the Documentos panel a folder field;
  upload-basename normalisation for browser paths is unchanged.

### Increment 143 — deterministic cognitive-event registration guard ✅ (2026-09-07)
- The serialisation guard no longer depends on which event modules happened to be imported during
  collection: it enumerates the whole `jarvis.domain.events` package via `pkgutil` (`6443631`). Removes
  the collection-order flake seen during Increment 141's verification and keeps the "every new event type
  gets a registered sample" hazard loudly guarded.

### Increment 144 — root-injectable per-belief default weighting policy ✅ (2026-09-07)
- `Jarvis(default_belief_policy=...)` and `set_belief_policy(...)` override the *source* policy every
  fresh belief is born with — goals, actions, companion traits, self-observed habits — instead of the
  hard-coded `DEFAULT_WEIGHTING` (`a84c4c0`). The decay composition stays the episode path's injectable
  (`weighting_policy`); `Jarvis.persistent()` forwards the root policy too.
- The swap applies to subsequent creations only, so nothing stored is silently re-weighted; the
  companion aggregate and the self-observation observers now take the policy as a default.
- Closes the Track-D "per-belief default not overridable at the root" gap; the knobs family (thresholds +
  source policy) is now fully injectable and runtime-swappable.

### Increment 145 — deep multi-turn reasoning: the session reasoning span ✅ (2026-09-07)
- Each answered question is now a *step* in a bounded, session-scoped `ReasoningSpan`
  (`src/jarvis/domain/reasoning/reasoning_span.py`, `9db5ddc`): the reasoner carries the span's
  threads across turns, so a follow-up continues the discussion instead of being a fresh stateless call.
  The thread lifecycle is driven by **deterministic domain signals only** — a new answered query opens or
  revises a thread and moves the previous one on; `confirm()` seals (grounded by the belief loop, the
  thread then leaves the span) or flags as disputed (never carried as an active proposal again). The LLM
  proposes content; it never decides thread state (Vision §38, D6).
- `LlmReasoner` renders the span into the prompt (`<current_thread>`, `<earlier_threads>`,
  `<corrected_proposals>`) so deep references resolve beyond the recent-dialogue window, and the
  instructions tell it never to repeat a corrected proposal as fact. The `Reasoner` Protocol grew an
  optional `span=` kw (offline/`SilentReasoner` unchanged in behaviour).
- The span is explicitly weaker than a belief: bounded (capacity-evicted), session-scoped, never
  persisted, never evidence, holding no confidence. The command-center snapshot exposes the threads
  (`reasoning`), and replies never leak them.
- Gates (HEAD): ruff clean · pyright strict 0 errors · pytest 1112 passed, 3 skipped.

### Increment 146 — temporal stability for hypotheses ✅ (2026-09-07)
- Hypotheses now derive the *same* span-based `TemporalStability` estimator beliefs use
  (`derive_stability`, `2cfacdf`): how steadily the supporting evidence is spread over time, zero for a
  single support or one moment. Closed the "derived for beliefs, not hypotheses" gap.
- The axis stays separate (Vision §10): stability never re-ranks the `HypothesisSet`, never breaks a
  tie, never alters derived confidence. Its job is the anti-overfit narration — the `Challenge` now
  carries the leading hypothesis's derived `confidence` and `stability` and `describe()` flags a
  narrow-time-window leader as possible overfitting, mirroring the grounded-belief conclusion's caution
  (Vision §11).
- `LOW_STABILITY_THRESHOLD` is centralized in the domain (`belief.py`); the executive and
  self-observation import it instead of three mirrored literals.
- Gates (HEAD): ruff clean · pyright strict 0 errors · pytest 1122 passed, 3 skipped.

### Increment 147 — one CognitiveEpisode shape ✅ (2026-09-07)
- Deliberations previously shunted the `HypothesisSet` around as a local in the executive and painted
  `kind=EpisodeKind.DELIBERATION` onto the record by hand, while conclusions got a genuine slot in the
  aggregate (`_working_belief`). Two implicit shapes, two hand-painted tags (`002c364`).
- The episode now holds ONE conclusion-model — a working `Belief` or a `HypothesisSet` — in a single
  `_conclusion` slot: both ride the same lifecycle, flow their events through the same `pull_events`
  boundary, and record through it. `kind` is derived from which conclusion the episode actually held
  (a `HypothesisSet` deliberates, anything else concludes), so the label can never drift from the
  episode and both hand-painted call sites disappear.
- `observe()` now refuses single evidence on a deliberation (evidence must name a hypothesis — it goes
  through the set), and `WorkingBelief`/`explain` stay None for the deliberation shape. Public surface
  (`working_belief`, lifecycle, events) unchanged.
- Gates (HEAD): ruff clean · pyright strict 0 errors · pytest 1130 passed, 3 skipped.

### Increment 148 — document ownership (recorded provenance) ✅ (2026-09-07)
- A stored document was bytes with a name; nothing answered *"whose is that, and when did I get it?"*
  (Vision §26). Each stored file now carries recorded `DocumentMeta`: `DocumentOwner` attribution
  (COMPANION - shared with Jarvis - vs JARVIS - a generated artifact) plus `stored_at`/`updated_at`/
  `size_bytes`, persisted in a reserved `_jarvis-meta.json` index that ``list``/``search`` never surface.
- `write_document(name, content, *, owner=COMPANION)`; `jarvis.document_meta(name)` passthrough; a file
  with no recorded provenance (pre-tracking) honestly reads `None`, never a guess. Overwrites keep
  ``stored_at`` and refresh ``updated_at``. Deterministic offline tests via an injectable clock (D8).
- Command center: ``documents list`` tags jarvis-generated docs; new ``documents info`` action answers
  owner/size/stored/updated; ``save`` accepts an optional ``owner`` (``companion`` default,
  ``jarvis``). Per-file search ranking remains as-is (each hit is already a whole document, `a62df36`).
- Gates (HEAD): ruff clean · pyright strict 0 errors · pytest 1146 passed, 3 skipped.

### Increment 149 — editing documents via the chat itself ✅ (2026-09-07)
- "Hazle este cambio" to a shared file finally has a seam, built as the same proposal-decided split as
  the reasoner (§38): a domain `DocumentEditor` Protocol *proposes the complete revised text* from a
  free-form instruction; the offline `SilentDocumentEditor` declines honestly (§37); `LlmDocumentEditor`
  backs it over the `LanguageModel` seam (fence-stripping, provider failure -> no proposal).
- `jarvis.edit_document(name, instruction)` applies the proposal through the documents capability,
  **preserving the recorded owner** and framing the change **from the real diff** — never from what the
  model claims (`_describe_document_change`, Vision §26). Binary files are kept intact (refused, never
  rewritten); a rewrite identical to the current text is reported without touching the file.
- Command center: new ``documents edit`` action (needs ``name`` + ``instruction``; honest offline
  message pointing to ``save`` when no live model); the runtime provider swap (`perceiver` action) wires
  the editor alongside perceiver/companion-perceiver/voice/reasoner so edits ride the same model.
- Gates (HEAD): ruff clean · pyright strict 0 errors · pytest 1174 passed, 3 skipped.

---

## Decisions log (ADR-lite — settled, do not revisit)

- **D1** `src/` layout; `pythonpath=["src"]` in pytest so no install step is needed for tests.
- **D2** Python 3.13+ target (dev machine runs 3.14). Modern typing, stdlib-first, no deps yet.
- **D3** Events are frozen, `slots=True`, `kw_only=True` dataclasses. `DomainEvent` carries
  `event_id / occurred_at(UTC) / correlation_id / causation_id`; `CognitiveEvent` adds `episode_id`.
- **D4** The aggregate **collects** events (`pull_events`); the controller **dispatches** them.
  The domain has no dependency on the NervousSystem (no infra coupling in the domain).
- **D5** `NervousSystem` is synchronous: `publish` queues, `dispatch` drains, handlers match by
  `isinstance` (subtypes included). Priority/async/backpressure are explicitly out of scope.
- **D6** Only 6 episode states exist (`CREATED, REASONING, REFLECTING, DECIDING, COMPLETED, FAILED`).
  States are added when a cognitive operation needs them, not upfront.
- **D7** `Confidence` **rejects** invalid input (out-of-range / NaN / bool / non-number); it never
  clamps. Enforces "a belief must never be stronger than its evidence" at the value level.
- **D8** No `services/` or `repositories/` folders yet — created when a real collaborator needs them
  (avoid speculative infrastructure).
- **D9** `CognitiveEvent.episode_id` is **optional** (`str | None = None`). Not all cognition is
  bound to one episode: beliefs persist across episodes (Vision §3, §21), so belief events may be
  emitted without episode context. Episode lifecycle events always set it; `correlation_id` still
  groups the process. (Evolved the Increment-1 contract that required it.)
- **D10** Evidence weight reuses the `Confidence` value object (both are [0,1] magnitudes;
  Vision §9 defines confidence as evidence strength). A separate `EvidenceWeight` VO would be a
  near-duplicate — not created until it earns its place.
- **D11** A belief's confidence is **derived, never assigned** — `derive_confidence` is the only
  path. This makes "a belief must never be stronger than its evidence" a structural guarantee, not
  a check. Estimator: `supporting / (supporting + contradicting + 1)`. Do not add a confidence
  setter to Belief (or Hypothesis).
- **D12** `Belief` and `Hypothesis` share the estimator (`derive_confidence`) — the one thing that
  must never diverge — but NOT a common base class. The thin structural overlap (evidence list +
  confidence property) is left duplicated on purpose; extract a base only when a genuine third
  evidence-grounded entity appears (rule of three). Avoids a fragile slots-dataclass inheritance
  refactor and keeps shipped code stable.
- **D13** `HypothesisSet.leading()` returns None on a tie (top two equal), not an arbitrary winner.
  A tie is genuine uncertainty; refusing to name a leader is the point (Vision §17).
- **D14** `GROUNDED_CONFIDENCE_THRESHOLD = 0.5` in the executive: below it a conclusion is not
  asserted as grounded (reported tentative/insufficient instead). A defensible midpoint, revisited
  when reflection/attention need a smarter policy. Threshold lives in the executive, not the domain.
- **D15** `CognitiveEpisode` is the aggregate that owns the working `Belief` (Vision §12): evidence
  reaches the belief only via `episode.observe`, and the episode aggregates the belief's events into
  its own `pull_events`. The executive stays a thin orchestrator.
- **D16** Repository interface (`BeliefRepository`, a `Protocol`) lives in the **domain**;
  implementations live in **infrastructure** (`InMemoryBeliefStore`). Beliefs are keyed by
  statement; the store keeps live belief objects so retrieval returns the same identity and evidence
  accumulates. The store never records truth — confidence is always re-derived (Vision §22).
- **D17** Belief statement for an episode is `working_statement(trigger)` = deterministic function of
  the trigger, so the same trigger retrieves the same belief across episodes. (Trigger-string identity
  is a deliberate simplification; semantic matching of statements is a later concern.)
- **D18** `TemporalStability` is a **separate** value object from `Confidence` (Vision §10 — different
  axes must not collapse), even though both are [0,1] magnitudes. A shared `UnitInterval` base is a
  candidate only on the third such type (rule of three). Stability scale `STABILITY_REFERENCE = 30d`
  and `LOW_STABILITY_THRESHOLD = 0.2` are tunable; stability is span-based (count-weighting deferred).
- **D20** Self-observation reuses the ordinary epistemology: a self-observation is `Evidence` about
  Jarvis → a `Belief` with derived confidence, so self-beliefs are provisional/revisable (Vision §6),
  never asserted personality. It must be driven by measurable `EpisodeRecord` data (hence
  `conclusion_confidence` on the record), not by parsing decision text. `_GROUNDED_CONFIDENCE = 0.5`
  in the service mirrors the executive's D14 value (kept separate so the domain doesn't import the
  application layer); `_MINIMUM_HISTORY = 3`.
- **D21** Self-observation judges only `COMPANION`-origin episodes; `CURIOSITY`-origin (self-triggered)
  episodes are excluded so curiosity cannot inflate the tendency it responds to (no self-reinforcing
  loop). Curiosity stops at a `CuriosityImpulse` (recommendation); `Jarvis.pursue` runs it as a
  deliberate step, not automatically — autonomy is earned (Vision §28). `CURIOSITY_THRESHOLD = 0.5`.
- **D22** Learning is expressed as a *behaviour change derived from the self-model each decision*
  (`LEARNED_HABIT_THRESHOLD = 0.5`), never a persisted flag/mode. It reverts automatically as the
  self-belief's confidence decays, satisfying Vision §20 (changed future behaviour) while keeping the
  change honest and evidence-driven. The self-model is read over PRIOR episodes only (the current one
  is unrecorded at decision time), so no self-reference.
- **D23** A companion belief informs `think()` as ordinary **evidence** (SYSTEM_OBSERVATION, weight =
  the belief's confidence), seeded before caller evidence — never an override. Relevance is a
  case-insensitive substring match of the trait in the trigger, gated at confidence ≥ 0.5. Semantic
  trigger↔trait matching is deliberately deferred; the honesty (evidence not override, weaken-able
  in-episode) is the part that must not regress.
- **D24** Persistence stores only evidence (not confidence/stability), which are re-derived on load
  (Vision §22 memory ≠ truth). File-backed stores implement the existing repository protocols so the
  domain stays untouched; belief rehydration uses the dataclass `_evidence=` constructor param.
  JSON now (stdlib, human-readable); a real DB is a later swap behind the same interface. The
  weighting policy and the companion model are NOT yet persisted (deferred).
- **D25** Within an episode, belief events correlate to the **episode** (not the belief): `observe`
  passes `correlation_id=episode.id`. correlation_id means "the one logical process this event belongs
  to" (Vision §26); inside an episode that process is the episode. Outside an episode a belief still
  correlates to its own id. The `EpisodeTrace` is a read-only observer (subscriber); it never drives
  cognition. This is internal provenance, not user-facing chain-of-thought.
- **D28** `state_summary()` reports action beliefs as `(statement, confidence)`, not a recommendation
  stance — stance requires an `Action`'s `reversible` flag, which is not persisted on the belief, so it
  cannot be derived from the store alone. Reversibility persistence would be a separate increment.
- **D26** Hypothesis deliberation (`consider`) is a **distinct cognition shape** from a single-belief
  episode; it is NOT forced through the belief-centric `CognitiveEpisode`/`EpisodeRecord`. `consider`
  dispatches its hypothesis events (so subscribers/trace observe them) and returns a `Deliberation`.
  Recording deliberations to episodic memory and per-episode trace-correlation are deferred until
  `EpisodeRecord` is generalised beyond a single working belief. Refined from the Increment-18
  next-step note once the belief-centric record proved a poor fit (anti-vagueness: smallest reversible).
- **D19** Source→weight factors live in one policy (`SourceWeightingPolicy`), not scattered constants,
  and the policy is injectable (`EvidenceWeightingPolicy`). Effective weight = raw × source factor;
  the raw weight/source are never mutated (provenance preserved). `USER_STATEMENT` factor is 1.0 so
  prior USER_STATEMENT-based tests/behaviour are unchanged; other sources scale down.
- **D29** `feel_curious()` checks curiosity sources in a fixed priority: (1) self-tendencies
  (own reliability, strongest weakness first), (2) contested companion beliefs (tension to resolve),
  (3) contested *working* beliefs — something reasoned/perceived that carries both supporting and
  contradicting evidence (Increment 70), (4) recurring goals (a pattern in its own purposes). Later
  sources fire only when earlier ones are quiet. Rationale: a companion should first be honest about its
  own weaknesses, then resolve tensions about the companion and about what it has concluded, before
  turning to its own purposes. Order is settled; new sources slot in with an explicit rank.
- **D30** Within slot (3), curiosity gives up on a stuck goal once `reflection_effort >=
  _MAX_GOAL_REFLECTIONS` (=3) while reachability is still < 0.5 — it stops re-raising a door it has
  pushed enough. This is a *selection policy*, not a belief: nothing is asserted about the goal, and it
  is reversible ("not right now"): learning the goal is reachable (or a future fresh-recurrence rule)
  lifts the suppression. Threshold lives in `jarvis.py`; chosen to match the self-observation history
  floor (3) so "enough evidence to act" is consistent across the system.
- **D31** Perception is a `PerceptionSource` Protocol (domain) whose implementations live in
  infrastructure; it only *produces `Evidence`* (Vision §32/§38). The cognitive core never calls an LLM
  or any capability provider directly — everything reaches cognition as evidence, confidence stays
  derived, the executive stays the decider. A perceiver that makes nothing of an observation returns `()`
  (honest silence, §37), never a fabricated reading. The default `KeywordPerception` is intentionally
  dumb; a smarter (e.g. LLM-backed) perceiver is a drop-in behind the same Protocol and must not require
  any change to the domain/executive.
- **D32** The reflective cycle (Remember → Connect → Reflect → Hypothesise → Challenge → Learn → Act) is
  built **inside** Jarvis — its own autonomous reflective mode, driven by the same episodes / NervousSystem
  / epistemology — NOT a separate orchestration layer that calls Jarvis's methods. A wrapper would be the
  "autonomous agent framework / prompt orchestration" the vision explicitly forbids (§1) and would break
  the core-architecture principle (§38). Each stage is evidence-grounded, derived, revisable, auditable,
  and involves no LLM deciding — that (not the loop shape, which is standard) is what makes it novel.
  Build order: Connect (Increment 74) → Reflect → autonomous Hypothesise → Challenge → wire Learn/Act.
- **D33** The LLM enters ONLY through a `LanguageModel` Protocol (`complete(prompt) -> str`) behind
  `LlmPerception` (a `PerceptionSource`). The model *extracts candidate evidence* from text — the claims a
  text makes and how strongly it asserts each — and NOTHING more: confidence-of-belief stays derived, the
  executive stays the decider (§38). The provider is chosen at the composition root by injecting a
  `LanguageModel` (user requirement: swappable by config), so no real provider is a dependency of the core
  or the tests — a `ScriptedLanguageModel` stub stands in. Unreadable/out-of-range model output is dropped
  (honest silence §37 / no clamping D7), never fabricated. Real provider SDKs live only inside a
  `LanguageModel` implementation.
- **D34** The command center is a **local web app**, not a Python GUI: the core stays stdlib-only, so voice
  (`speechSynthesis`/`SpeechRecognition`) and the 3D dot-face (`<canvas>`) live in the browser where they
  cost nothing. A stdlib `http.server` serves one self-contained `console.html` + a JSON bridge; every
  decision (`handle`/`route`/`snapshot`) is a **pure function** over a Jarvis (socket-free, unit-tested),
  and the server only moves bytes. The bridge calls Jarvis's ordinary methods and invents nothing — it is a
  window onto the core, not a second brain. Binding a socket in tests is opt-in (`JARVIS_UI_SMOKE=1`), so
  CI/offline stay hermetic. The §38 boundary holds: no LLM in judgment; the browser's voice/vision are I/O,
  not cognition.
- **D35** Recall is a **candidate, not belief**: a `MemoryRetriever` supplies *recalled context* on the
  episode (never belief-evidence; memory is not truth, Vision §22) and a *stance* (Memory / partial_memory)
  for the surface. The seam is a domain Protocol with a deterministic lexical adapter (offline default,
  D8); semantic retrieval swaps in behind the same Protocol (Increment 108). A question-shaped memory is
  never recalled as knowledge.
- **D36** Reasoning is **inference, not judgement**: a `Reasoner` proposes a provisional answer as response
  context — never belief-evidence, never confidence. Its output may be folded in as the *weakest*
  `EvidenceSource.INFERENCE` evidence (weight 0.2, Increment 110) so an unconfirmed answer is held faintly
  and a term only matures it via `confirm()`. The executive is the decider (Vision §37, §38, D6).
- **D37** Edge capabilities are **earned and live-backed**: `can_do(name)` is true only when a capability is
  both *acquired* (Odysseus, deliberate step, Vision §28) and backed by a ready `CapabilityProvider`.
  Research/compare/reason/semantic-recall register providers like the web seams, so the same gate applies
  to every catalog capability except speech (kept honest: a silent reasoner or lexical-only recall does not
  report `can_do`).
- **D38** Edge consultation is a **deliberate, gated step**: a `KnowledgeSource` edge (research → weaker
  `EXTERNAL_SOURCE`; compare → weakest `INFERENCE`) is consulted only when the episode lacks real support
  and strong recall, at most once, recorded in the episode (`consulted`/`record_consult`). It gathers
  candidate evidence; empty/failed is honest None (D6). Opt-in: an un-wired Jarvis never consults.
- **D39** Material-edge capabilities follow one pattern: a domain Protocol at the edge + an infrastructure
  adapter (injectable io/net → offline tests, env-gated root, `build_*() -> None` when unconfigured,
  D7/D8) + delegated `Jarvis` methods + a `CapabilityProvider` in the registry. Calendar/tasks/notes/mail/
  speech/agent all follow it; `can_do` reflects acquisition AND provider availability.
- **D40** An agent-bridge may **delegate material actions** (never cognition): the edge agent executes
  concrete tasks and returns outcomes with provenance; it never substitutes Jarvis's judgement, never
  writes to beliefs/memory directly, and is governed by the controlled-autonomy policy + Tool Registry
  permission levels (see the revised D1 in `docs/claude/DECISIONS.md`).

---

## Roadmap — the reflective cycle & outstanding threads  (2026-08-24)

The organising goal now (user-chosen 2026-08-24): build the **reflective cycle**
**Remember → Connect → Reflect → Hypothesise → Challenge → Learn → Act** as Jarvis's own autonomous mode,
*inside* the core (D32 — not a wrapper; §1/§38). What makes it novel is that every stage is
evidence-grounded, derived, revisable, auditable, and involves no LLM — not the loop shape itself.
All prior deferred threads are folded in below so nothing is lost.

### Track A — the reflective cycle (primary)
| Stage | Status | Notes |
|---|---|---|
| Remember | ✅ done | episodic + belief + companion + action memory, persistent |
| **Connect** | ✅ done (Incr 74) | `Connection`, `connections()`, `related_beliefs()` — links by shared evidence |
| **Reflect** | ✅ done (Incr 75) | `Reflection`, `reflect()` — load-bearing observations across the belief web |
| **Hypothesise (autonomous)** | ✅ done (Incr 76) | `hypothesise()` — a common-cause `HypothesisSet` brewed from `reflect()` |
| **Challenge** | ✅ done (Incr 77) | `challenge()` names the falsifier; `refute()` dethrones by removing what it explained |
| **Learn** | ✅ done (Incr 78) | `learn_from_reflection()` — a surviving insight becomes a belief; the loop closes |
| **Act** | ✅ done (Incr 82) | `act_on_insight()` — a learned common cause recommends verifying the observation |
| **`reflect_cycle()` — the whole loop in one call** | ✅ done (Incr 79) | runs Connect→…→Learn, returns `ReflectiveCycle` summary |
| **Trigger the cycle autonomously** | ✅ done (Incr 80) | `feel_curious()` raises a reflect impulse on an un-mined pattern; `pursue()` runs the cycle |

**Track A (the reflective cycle) is complete** — Remember → Connect → Reflect → Hypothesise → Challenge →
Learn, self-triggered by curiosity. Everything derived, revisable, auditable, no LLM. Remaining across all
tracks: wire a learned insight to Act (recommend an action); Track B (LLM adapter, gated); Track C (§15
energy); Track D finish-offs (incl. persisting reflective-cycle refutations).

### Track B — perception → the LLM adapter (highest external impact, separate)
> **UPDATE (Increments 87–93): Track B is landed and live.** Open registry (87), env-config (88), UI
> switcher (92), and panel-entered key → `.env` (93) mean the center runs against a real LLM from the
> browser. The prose below is the historical build-up; the recommendation lines further down are superseded.
- Seam done (Increments 63–68): `PerceptionSource`, streams, provenance, contested-belief resolution.
- **LLM seam done (Increment 86):** `LanguageModel` Protocol + `LlmPerception` (a `PerceptionSource`) +
  `ScriptedLanguageModel` stub — provider-agnostic, §38 boundary held (D33), NO live API.
- **Open registry done (Increment 87):** `ProviderSettings` + `language_model_registry` +
  generic `OpenAiCompatibleModel` (stdlib `urllib`, injectable `Transport`). 16 providers out of the box
  incl. Groq/Grok/DeepSeek/Kimi/Mistral/Perplexity/OpenRouter/Together and **local Ollama/LM Studio**;
  any other endpoint by `base_url`; add more with a one-line `register_endpoint`. USER REQUIREMENT
  (many providers + local SLMs, not just the big three) — **satisfied**.
- **Open next:** the FIRST real adapter — wire the default `urllib` transport to a live endpoint. This is
  the first live-API increment: decides which provider to smoke-test, where the API secret lives (env
  var, never committed), and how CI/offline stays green (default stays "scripted"; live is opt-in).

### Track C — §15 cognitive energy (self-contained, still open — CHOSEN NEXT 2026-08-25)
- Per-episode cost (FULL > BRIEF), accumulate + expose read-only, later a budget that makes attention
  *choose* BRIEF under load. Deepens Increment 33/34 attention. No deps. Starting now (Increment 84).

### Track E — Command Center (chat with Jarvis + tune parameters) — USER REQUIREMENT — BACKBONE DONE (Increment 89)
- **A total control center, in the browser (Increment 89, D34).** Web command center: chat (text + voice),
  Jarvis speaks (`speechSynthesis`) and listens (`SpeechRecognition`), a `<canvas>` point-cloud face that
  moves as it talks, live state (beliefs/companion/goals/energy), and a real runtime tuner (energy budget
  → `set_energy_budget`). Core stays stdlib-only; the browser supplies voice+3D at zero dependency cost.
  Pure `handle`/`route`/`snapshot` (socket-free, tested); thin `http.server` wrapper. Verified live.
- **Mouth synced to real speech (Increment 90):** `speechSynthesis` output isn't capturable by Web Audio,
  so the mouth is driven by the utterance's real word boundaries (`onboundary`), gated by start/end, with a
  gentle fallback where boundaries aren't delivered. Verified in-browser.
- **Reasoning shown live (Increment 91):** a reasoning panel renders belief provenance (grounds for/against
  + confidence), the episode's step trace, and the reflective cycle; an `explain` command answers "why?".
- **Perceiver/provider switcher (Increment 92):** the header shows the live perceiver and a card switches it
  to any registered provider at runtime (`perceiver` command + `perceiver_factory`); the secret stays in the
  env. This closes former open items (1)/(4).
- **Still open (refinements, opportunistic):** (a) expose the remaining knob — the per-belief weighting
  policy (decay is injectable, Increment 113; source policy at the root is not); grounded/insight/
  `max_goal_reflections` thresholds are live (Increment 141); (b) streaming replies. As we add each
  tunable, expose it via constructor/config, not a module constant.

### Track D — smaller finish-offs (fold in opportunistically, not their own phase)
- `TemporalStability` count/recency weighting (currently span-only; hypotheses now derive it too, 146).
- Injectable weighting policy at `Jarvis(...)` level (currently per-belief default).
- Semantic matching for belief/connection identity (beyond exact-string D17) — naturally becomes an
  LLM/embedding job once Track B exists.
- Persist traces; consider a real DB behind the JSON stores; pin ruff/pyright in a lockfile.

**Sequencing decision:** finish Track A (the cycle) next — it is what makes the system *revolutionary*
and it only needs what already exists. Track B (LLM) is the biggest external-value jump but is gated on a
design decision, so it waits for an explicit go. Tracks C/D are opportunistic.

---

## Next increment (recommended, not yet started)

**The command center has voice, a synced face, live state, tuning, a reasoning panel, a capability
catalog, edges (internet/research/compare/tool/notes/mail/calendar/tasks/speech), files/documents as a
first-class surface, and a real LLM path (Increments 89–142); cognition thresholds are live-tunable (141),
documents are folder-aware (142), the per-belief weighting policy is root-injectable (144), deep
multi-turn reasoning rides a session span (145), hypotheses narrate their own temporal stability
(146), beliefs and hypothesis sets share one `CognitiveEpisode` shape (147), documents carry
recorded ownership (148) and documents are editable via the chat itself (149).** The audit-gate reset (135), the reasoner-consuming-
ConversationContext work (138), live knobs (141), the deterministic event guard (143), the
weighting-policy seam (144), the reasoning span (145), the hypothesis-stability narration (146), the
episode-shape unification (147), document provenance (148) and chat-based document editing (149) have
all landed. The mechanical debt is gone; the
remaining choices are capability. Natural next moves — pick one:
- **A remaining honest gap:** the real database behind the repository contracts (D10), the live STT
  backer behind the speech seam, or more §15 energy modelling (charge deliberations).
- Discipline unchanged: new command = pure `handle` branch + socket-free test; new tunable = injectable via
  constructor/config, never a module constant; asset tripwire guards new UI wiring; no network in the suite;
  §38 boundary intact (the LLM extracts candidate evidence, it never decides).

---

## After that — remaining directions

Track A (the reflective cycle) is complete and persistent; **Track B is live** (Increments 86–98); **Track
C (§15 energy) has both its seams done** (cost visible + a fatigue budget, Increments 84–85, + decay
weighting, Increment 113). The remaining directions:

- **Capability depth beyond the seams:** the calendar/tasks/notes/mail/speech/agent edges exist as seams +
  adapters; each can be deepened (CalDAV sync, scheduling execution, STT integration, richer delegation
  scopes). Each must stay behind its domain Protocol (D39), earned (D37), and offline-testable (D8).
- **Conversation context for reasoning (landed, Increment 138);** the deep multi-turn edge is now landed
  too: the session `ReasoningSpan` (Increment 145) carries the discussion across turns. The span is
  conversation-scoped; extending it into the *episode* path or a live voice session stays open.
- **Track C/D leftovers (opportunistic).** More §15 energy modelling (charge deliberations; energy recovery
  over time); count/recency weighting in `TemporalStability`
  beyond the opt-in decay policy; injectable
  weighting policy at the `Jarvis(...)` level (done — decay at Increment 113, per-belief root default at
  144); pin ruff/pyright in a lockfile; consider a real DB behind the repository
  contracts (D10).

*Recommendation: the mechanical gates debt is gone (Increment 135), the reasoner reads recent turns
(Increment 138), cognition thresholds are live-tunable (Increment 141), documents are folder-aware
(Increment 142), the per-belief weighting policy is root-injectable (144), deep multi-turn reasoning
rides a session span (145), hypotheses narrate their temporal stability (146), beliefs and hypothesis
sets share one `CognitiveEpisode` shape (147), documents carry recorded ownership (148) and documents
are editable via the chat itself (149). Document depth is complete; the biggest-value remaining goal is
a real database (D10) behind the
repository contracts.*

*(Deferred, natural follow-ups: excessive-complexity self-observation tendency; semantic trigger↔trait
matching now that embeddings exist; recurring-goals/working-patterns facets; live STT wiring for the speech
seam.)*

---

## Known limitations / not built yet  (refreshed 2026-09-07, Increment 149)

**Landed since the last refresh (do not re-plan):**
- The reflective cycle is **complete end to end** (Increments 74–82) and its `reflect_cycle()` runs all
  seven stages including Connect and Act (P0 fix, Increment 111); the Reflect stage is a genuine review
  with an `EpisodeReflected` note (P1, Increment 112); refutations and the **episode trace persist** (JSONL,
  Increments 83 + 112).
- **Real perception is wired end-to-end** (Increments 86–93): `LlmPerception` behind the `PerceptionSource`
  seam, an open provider registry, env-config, a UI switcher, `.env` creds, streaming replies (101),
  per-provider keys/models (102/103). The keyword rule stays the offline default.
- **Memory recall + reasoning + learning loop** (Increments 104–110): lexical and semantic (embedding)
  recall, identity-aware answers, provisional inference answers that mature on confirmation, self-diagnosing
  provider errors, and decay weighting (113).
- **Capabilities at the edge** (Increments 115–134): web (Agent-Reach), deep research, blind model
  comparison, tool registry, notes, mail (real IMAP/SMTP), calendar (local + Google), task scheduler,
  speech-perception seam, agent delegation.
- **Audit gates at HEAD:** ruff clean and pyright **strict 0 errors** across `src` and `tests`
  (Increment 135).
- **Capabilities/needs persist** and live-backed ones provision at boot (Increment 136).
- **Files/documents as a surface** (Increments 137–140): `DocumentStore` seam over bytes + local adapter,
  list/read/write/remove, `JARVIS_PROJECT_ROOTS` for the `FileSystemTool`, a Documentos panel, lexical
  documents search, documents riding memory recall (MemoryKind.DOCUMENT), and document chips in `say`
  replies — all behind offline, io-injectable adapters.
- **Reasoner consumes the short-term `ConversationContext`** in both the conversational and episode paths
  (Increment 138).
- **Cognition thresholds are live-tunable** (Increments 141): one validated `CognitiveKnobs` VO replaces the
  module constants and domain mirrors; injectable at `Jarvis(...)`, runtime-swappable, and exposed as a
  `tunables` action + sliders in the settings panel.
- **A deterministic event-registration guard** kills a collection-order flake and keeps every new event type
  firmly registered (Increment 143).
- **Deep multi-turn reasoning** (Increment 145): a session `ReasoningSpan` carries the reasoning threads
  across turns so a follow-up continues the discussion instead of restarting it, with a deterministic
  thread lifecycle (open/revise, move-on, seal on confirmation, dispute on correction) and zero model
  say over thread state.
- **Temporal stability for hypotheses** (Increment 146): hypotheses derive the same span-based
  `TemporalStability` estimator as beliefs; the `Challenge` narration flags a narrow-time-window leader
  as possible overfitting (anti-overfit, Vision §11) without touching its strength, ranking or ties.
- **One `CognitiveEpisode` shape** (Increment 147): deliberations attach their `HypothesisSet` exactly
  like conclusions attach their `Belief` — one `_conclusion` slot, one lifecycle, one event boundary;
  `EpisodeKind` is derived from that conclusion, never painted by the record callers.
- **Document ownership** (Increment 148): every stored document carries recorded provenance
  (`DocumentOwner` + stored/updated timing via `DocumentMeta`), persisted out-of-band from the bytes;
  `documents info` answers "whose is this and when did I get it?" and `list` tags generated files.
- **Chat editing of documents** (Increment 149): a `DocumentEditor` seam proposes a complete rewrite
  from a free-form `documents edit` instruction; Jarvis applies it, preserves attribution, and frames
  the change from the real diff; binary files are never rewritten.
- **Per-belief weighting is root-injectable** (Increment 144): `Jarvis(default_belief_policy=...)` /
  `set_belief_policy(...)` override the source policy every fresh belief is born with — goals, actions,
  companion traits, self-observed habits — swap reaches subsequent creations only, inherited by
  `Jarvis.persistent()`.

**Still open / honest gaps:**
- A real database behind the repository contracts (D10) — persistence is per-store JSON (now crash-safe).
- `TemporalStability` is span-based for both beliefs *and* hypotheses now (Increment 146) — no
  count/recency weighting beyond the opt-in decay policy; hypotheses narrate their narrowness without
  it affecting ranking or ties.
- Belief/connection identity still keys on exact strings (D17); semantic matching exists for *recall*
  (embeddings) but not for belief/connection identity.
- The episode-shape split is *gone* (Increment 147): beliefs and hypothesis sets share one
  `CognitiveEpisode` shape and `EpisodeKind` is derived from the conclusion, never painted.
- *Deep multi-turn* reasoning: an incremental reasoning span over several turns is now built — the
  session `ReasoningSpan` (Increment 145) continues the discussion across turns with a deterministic
  thread lifecycle. The span is conversation-scoped and bounded; it is not yet carried into the
  *episode* path or connected to a live-STT voice session.
- Documents are folder-aware (Increment 142), carry recorded ownership (Increment 148) and are
  editable via the chat itself (Increment 149) — remaining gap: search ranks whole documents, not
  passages.
- Speech has a perception seam but no live STT backer; real instruction execution is unimplemented
  (instructions are acknowledged honestly, not acted on — earned agency).
- Notes/tasks/calendar local adapters are file-backed (no CalDAV/ICS sync); email has a real IMAP/SMTP
  adapter but no per-account UI management.
- NervousSystem is single-threaded synchronous drain only; ruff/pyright not pinned in a lockfile.

**Already built (do not list as missing):** goals & decomposition, curiosity (incl. give-up/ask-for-help),
episodic + belief + companion + action memory, self-model (3 tendencies), graded autonomy, attention,
persistence across restart (crash-safe), perception seam + streams + contested-belief resolution, belief
connections, the full reflective cycle, trace persistence, decay forgetting, semantic recall, provisional
reasoning + confirmation, the five edge capability seams + tool registry, and the command center
dashboard/sphere/catalog surface, the files/documents surface (accept, recall, search, chip, read, folders),
live-tunable cognition thresholds, and the root-injectable per-belief weighting policy.

---

## Open blockers

None.
