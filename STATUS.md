# Jarvis — Implementation Status

Living document. Updated at the end of every increment. Single source of truth for
"where are we / what's next". No other progress docs — extend this one.

**North star:** `JARVIS_VISION.md` (repo root) is the objective every increment must move
toward. STATUS.md tracks *where we are*; JARVIS_VISION.md defines *where we are going*.
Every implementation decision must preserve the possibility of reaching that architecture
(Vision §41). Current code has no contradictions with the vision (verified 2026-08-21).

Last updated: 2026-08-24 (Increment 78)

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
    value_objects/goal.py                Goal (what an episode is toward + optional part_of, Vision §12/§26)
    value_objects/state_summary.py       StateSummary (compact immutable snapshot of all Jarvis holds)
    value_objects/action_recommendation.py  ActionRecommendation (a graded stance, Vision §28)
    services/goal_reflection.py          recurring_goals / reflection_effort (patterns over episodic goals)
    perception/perception_source.py      PerceptionSource (Protocol) — raw observation → Evidence (Vision §32)
  infrastructure/keyword_perception.py   KeywordPerception — dumb rule-based perceiver (NO LLM; §32/§37)
  (persistent() also wires JsonBeliefStore files: companion, actions, reversibility, goals, subgoals)
examples/                                6 runnable tours (main_loop, goal_arc, goal_parts, perceiving,
                                         conversation, resolving) — each guarded by tests/test_examples.py
tests/                                   353 tests mirroring the above (+ public-surface & example guards)
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
| Act | ✅ exists, ▶ WIRE NEXT | graded autonomy / stances — let a learned insight recommend an action |
| Run the whole cycle autonomously | ⬜ | one `reflect_cycle()` (or curiosity source) that runs Connect→…→Learn on itself |

### Track B — perception → the LLM adapter (highest external impact, separate)
- Seam done (Increments 63–68): `PerceptionSource`, streams, provenance, contested-belief resolution.
- **Open:** an LLM-backed `PerceptionSource` (§32) — the piece that lets Jarvis understand real language.
  Needs an explicit decision (which provider, where secrets live, offline/test story) before any code,
  and must keep the §38 boundary (LLM produces evidence, never decides). **Flag when we want this; design first.**

### Track C — §15 cognitive energy (self-contained, still open)
- Per-episode cost (FULL > BRIEF), accumulate + expose read-only, later a budget that makes attention
  *choose* BRIEF under load. Deepens Increment 33/34 attention. No deps. Pick up any time.

### Track D — smaller finish-offs (fold in opportunistically, not their own phase)
- Unify the two `CognitiveEpisode` shapes (conclusion vs deliberation) — or document the split as final.
- `TemporalStability` for hypotheses (currently beliefs only); count/recency weighting.
- Injectable weighting policy at `Jarvis(...)` level (currently per-belief default).
- Semantic matching for belief/connection identity (beyond exact-string D17) — naturally becomes an
  LLM/embedding job once Track B exists.
- Persist traces; consider a real DB behind the JSON stores; pin ruff/pyright in a lockfile.

**Sequencing decision:** finish Track A (the cycle) next — it is what makes the system *revolutionary*
and it only needs what already exists. Track B (LLM) is the biggest external-value jump but is gated on a
design decision, so it waits for an explicit go. Tracks C/D are opportunistic.

---

## Next increment (recommended, not yet started)

**Run the whole cycle in one call — `reflect_cycle()` (Vision §31, §19).** Every stage exists
(Connect→Reflect→Hypothesise→Challenge→Learn) but the caller must invoke them one by one. The natural
capstone is a single method that runs the cycle end-to-end and reports what it did, so Jarvis "thinking
about what it knows" is one honest action — and the seam for later triggering it autonomously. Smallest
honest step:
- `jarvis.reflect_cycle()` → a structured result: the top reflection, the hypothesis it brewed, the
  challenge it raised, and the belief it learned (or None at each stage it stopped). It calls the existing
  stage methods in order; it does not re-implement them. Returns a `ReflectiveCycle`/summary VO.
- Keep it truthful: it only *reports* what the derived stages produced; no new epistemics. If nothing is
  load-bearing, it returns an empty result honestly. This is the "one action" a future autonomous trigger
  (a curiosity source, or a scheduled self-reflection) will call — not built yet, but the method makes it
  a one-liner when we get there.
- Behaviour tests: on a belief web with a load-bearing observation, `reflect_cycle()` returns a result
  whose reflection/hypothesis/challenge/learned are all populated and consistent; on an isolated web it
  returns an empty result; after it runs, the learned belief is in the web.

*(When ready for the §32 LLM adapter, that is a separate track needing an API/secret decision — flag it
 and we design it explicitly. §15 cognitive energy also still open. Deferred, natural follow-ups:
excessive-complexity self-observation tendency; a real DB behind the JSON stores; persisting traces;
semantic trigger↔trait matching; recurring-goals/working-patterns facets; weighting-policy injection.)*

---

## Known limitations / not built yet  (refreshed 2026-08-24, Increment 74)

**Big missing capability (the ~20–30% gap):**
- **No real perception yet.** The `PerceptionSource` seam exists (Increments 63–68) but the only
  implementation is the dumb `KeywordPerception`. Jarvis cannot understand real language — an LLM adapter
  behind the same Protocol (§32) is the single highest-impact remaining piece. Separate track: needs an
  API/secret + design decision (see Roadmap).

**Reflective cycle — partially built (see Roadmap for order):**
- Connect ✅ (Increment 74). Reflect / autonomous Hypothesise / Challenge / cycle-wiring: NOT built.
- `reflection` in the executive is still a lifecycle placeholder (no genuine review of reasoning); the
  real Reflect stage is the next increment. Decision policy is still a confidence threshold (D14).

**Smaller open threads:**
- Deliberations reuse `CognitiveEpisode` as a lifecycle shell (two episode shapes gated by `EpisodeKind`
  rather than one unified belief+hypothesis model).
- `TemporalStability` is span-based (no count/recency weighting) and derived for beliefs, not hypotheses.
- Weighting policy is per-belief (default `SourceWeightingPolicy` — §11 source weighting DOES exist,
  Increment 7) but not injectable at the `Jarvis(...)` level.
- Belief/connection identity keys on exact strings (D17): trigger for beliefs, evidence *content* for
  connections. No semantic matching yet — the deliberate later, richer step.
- Persistence is per-store JSON (`Jarvis.persistent` wires all 7); no real DB; traces are not persisted.
- §15 cognitive energy/cost: not started (self-contained track, still open).
- NervousSystem is single-threaded synchronous drain only; ruff/pyright not pinned in a lockfile.

**Already built (do not list as missing):** goals & decomposition, curiosity (incl. give-up/ask-for-help),
episodic + belief + companion + action memory, self-model (3 tendencies), graded autonomy, attention,
persistence across restart, perception seam + streams + contested-belief resolution, belief connections.

---

## Open blockers

None.
