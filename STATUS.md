# Jarvis — Implementation Status

Living document. Updated at the end of every increment. Single source of truth for
"where are we / what's next". No other progress docs — extend this one.

**North star:** `JARVIS_VISION.md` (repo root) is the objective every increment must move
toward. STATUS.md tracks *where we are*; JARVIS_VISION.md defines *where we are going*.
Every implementation decision must preserve the possibility of reaching that architecture
(Vision §41). Current code has no contradictions with the vision (verified 2026-08-21).

Last updated: 2026-08-24 (Increment 51)

---

## Git / commits

- Remote is the source of truth: `github.com/kossto82-ops/Annie` (branch `main`). Every increment
  ends with a commit **pushed** to that remote (local-only commits are not "done").
- Identity for this repo (local config only): `ksst <kossto82@gmail.com>`.
- Convention: **one commit per increment**, message in English, ending with the
  `Co-Authored-By: Claude Opus 4.8` trailer. The foundation (increments 1–5) is a single commit
  (`484fd49`); increments 6+ are one commit each.

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
  jarvis.py                              Jarvis.think() entry point
  nervous_system/nervous_system.py       subscribe / publish / dispatch (sync)
  observability/episode_trace.py          EpisodeTrace — cognitive events grouped by episode (Vision §26)
  executive/executive_controller.py      orchestrates one episode's lifecycle
  infrastructure/in_memory_belief_store.py    InMemoryBeliefStore (BeliefRepository impl)
  infrastructure/in_memory_episode_store.py   InMemoryEpisodeStore (EpisodeRepository impl)
  infrastructure/json_belief_store.py         JsonBeliefStore (file-backed, survives restart)
  infrastructure/json_episode_store.py        JsonEpisodeStore (file-backed, survives restart)
  domain/
    repositories/belief_repository.py    BeliefRepository (Protocol) — get/save/all_beliefs
    repositories/episode_repository.py   EpisodeRepository (Protocol) — record/history of episodes
    services/evidence_weighting.py       EvidenceWeightingPolicy + SourceWeightingPolicy (Vision §11)
    services/self_observation.py         observe_evidence_habit / overconfidence / prediction_accuracy (§6/§31)
    services/curiosity.py                wonder — a self-belief → CuriosityImpulse (Vision §16)
    services/action_advisor.py           recommend — a learned belief → ActionRecommendation (Vision §28)
    value_objects/curiosity_impulse.py   CuriosityImpulse (a self-triggered investigation, recommended)
    aggregates/cognitive_episode.py      CognitiveEpisode (aggregate root) + InvalidStateTransition
    aggregates/hypothesis_set.py         HypothesisSet (competing hypotheses) + UnknownHypothesis
    aggregates/companion_model.py        CompanionModel — beliefs about the companion (Vision §5)
    entities/belief.py                   Belief (entity) + derive_confidence + BeliefExplanation
    entities/hypothesis.py               Hypothesis (entity, evidence-derived confidence)
    enums/episode_state.py               EpisodeState (6 of 12 conceptual states)
    enums/episode_kind.py                EpisodeKind (CONCLUSION | DELIBERATION)
    enums/evidence_source.py             EvidenceSource (Vision §8 origins)
    enums/trigger_origin.py              TriggerOrigin (COMPANION | CURIOSITY — who started the episode)
    enums/action_stance.py               ActionStance (SUGGEST | ASK_FIRST | WITHHOLD — Vision §28)
    enums/attention.py                   Attention (FULL | BRIEF — depth routing, Vision §14)
    events/domain_event.py               DomainEvent -> CognitiveEvent (immutable)
    events/episode_events.py             EpisodeStarted, EpisodeCompleted
    events/evidence_events.py            EvidenceAdded (shared by belief + hypothesis)
    events/belief_events.py              BeliefStrengthened, BeliefWeakened, ContradictionDetected
    events/hypothesis_events.py          HypothesisCreated
    value_objects/unit_interval.py       UnitInterval (shared [0,1] validation base)
    value_objects/confidence.py          Confidence (UnitInterval subtype)
    value_objects/evidence.py            Evidence (immutable, weighted, supports/contradicts)
    value_objects/temporal_stability.py  TemporalStability (UnitInterval subtype; time axis, ≠ confidence)
    value_objects/episode_record.py      EpisodeRecord (immutable memory of a completed episode)
    value_objects/evidence_request.py    EvidenceRequest (what an ungrounded episode is missing)
    value_objects/deliberation.py        Deliberation (outcome of weighing competing explanations)
    value_objects/action.py              Action (a declared intention + expected outcome, Vision §27)
    value_objects/goal.py                Goal (what an episode is toward, Vision §12/§26)
    value_objects/state_summary.py       StateSummary (compact immutable snapshot of all Jarvis holds)
tests/                                   45 behaviour tests mirroring the above
```

Conceptual flow implemented:
`trigger (+ evidence) -> CognitiveEpisode -> ExecutiveController -> forms a working Belief,
grounds it in evidence -> decision reflects the belief's derived confidence -> completion`,
with belief + episode events dispatched through the NervousSystem at each step.

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
  (3) recurring goals (a pattern in its own purposes). Later sources fire only when earlier ones are
  quiet. Rationale: a companion should first be honest about its own weaknesses before turning its
  attention outward or inward on purpose. Order is settled; new sources slot in with an explicit rank.
- **D30** Within slot (3), curiosity gives up on a stuck goal once `reflection_effort >=
  _MAX_GOAL_REFLECTIONS` (=3) while reachability is still < 0.5 — it stops re-raising a door it has
  pushed enough. This is a *selection policy*, not a belief: nothing is asserted about the goal, and it
  is reversible ("not right now"): learning the goal is reachable (or a future fresh-recurrence rule)
  lifts the suppression. Threshold lives in `jarvis.py`; chosen to match the self-observation history
  floor (3) so "enough evidence to act" is consistent across the system.

---

## Next increment (recommended, not yet started)

**Companion help on a stuck goal actually moves its reachability (Vision §18, §26, §20).** Jarvis now
asks for help on a stuck goal (Increment 51), but there is no way for the companion's answer to come
back in — the loop dangles. When the companion offers guidance, that should count as evidence that
changes what Jarvis has learned. Smallest honest step:
- Add `jarvis.receive_help(goal, helpful=True)` (or fold into `mark_goal_reached`'s sibling): the
  companion's guidance becomes `USER_STATEMENT`-sourced evidence on the goal's reachability belief —
  strong provenance (weight 1.0, source factor 1.0), so a genuinely helpful answer can lift a stuck
  goal above the threshold and clear the suppression, closing the ask→answer→learn loop.
- Keep it truthful: help is evidence, not a guarantee — an unhelpful answer (`helpful=False`) is
  recorded as contradicting, and reachability is still *derived*, never set. Distinguish the source in
  the evidence content so provenance is visible in `explain()`.
- Behaviour tests: `receive_help` on an exhausted stuck goal raises its reachability and removes it
  from `stuck_goals()`/`ask_for_help()`; `helpful=False` does not; the reachability belief's evidence
  records the companion as the source.

*(Deferred, natural follow-ups: goal decomposition/planning; cognitive-energy/cost budgeting (§15);
excessive-complexity self-observation tendency; a real DB behind the JSON stores; persisting traces;
semantic trigger↔trait matching; recurring-goals/working-patterns facets; weighting-policy injection.)*

---

## Known limitations / not built yet

- `reflection` in the executive is still a placeholder (no genuine review of reasoning); the
  decision policy is a simple confidence threshold (D14).
- Deliberations reuse `CognitiveEpisode` as a lifecycle shell (no working belief) rather than a
  belief+hypothesis unified aggregate — clean, but means an episode has two possible shapes gated by
  `EpisodeKind` rather than one model.
- Stability is span-based only (no count/recency weighting yet); `TemporalStability` is derived for
  beliefs but not yet for hypotheses.
- Weighting policy is applied per-belief (default) but not yet injectable at the `Jarvis(...)` level.
- Default stores are in-memory; durable JSON stores are opt-in per store (`Jarvis(beliefs=, episodes=,
  companion_store=, actions_store=)`). No real DB yet; traces are not persisted.
- Belief retrieval keys on the exact trigger string (D17), not semantic meaning of statements.
- Source-based weighting policy (Vision §11: explicit confirmation weighs more) not implemented —
  the caller assigns weight; `EvidenceSource` is recorded for when policy arrives.
- No goals, curiosity, memory, self-modeling. No persistence. No LLM.
- NervousSystem single-threaded synchronous drain only.
- ruff/pyright installed into the interpreter, not pinned in a lockfile.

---

## Open blockers

None.
