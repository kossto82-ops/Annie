# Jarvis — Implementation Status

Living document. Updated at the end of every increment. Single source of truth for
"where are we / what's next". No other progress docs — extend this one.

**North star:** `JARVIS_VISION.md` (repo root) is the objective every increment must move
toward. STATUS.md tracks *where we are*; JARVIS_VISION.md defines *where we are going*.
Every implementation decision must preserve the possibility of reaching that architecture
(Vision §41). Current code has no contradictions with the vision (verified 2026-08-21).

Last updated: 2026-08-21 (Increment 17)

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

j = Jarvis()

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
    services/self_observation.py         observe_evidence_habit — a belief about Jarvis (Vision §6/§31)
    services/curiosity.py                wonder — a self-belief → CuriosityImpulse (Vision §16)
    value_objects/curiosity_impulse.py   CuriosityImpulse (a self-triggered investigation, recommended)
    aggregates/cognitive_episode.py      CognitiveEpisode (aggregate root) + InvalidStateTransition
    aggregates/hypothesis_set.py         HypothesisSet (competing hypotheses) + UnknownHypothesis
    aggregates/companion_model.py        CompanionModel — beliefs about the companion (Vision §5)
    entities/belief.py                   Belief (entity) + derive_confidence + BeliefExplanation
    entities/hypothesis.py               Hypothesis (entity, evidence-derived confidence)
    enums/episode_state.py               EpisodeState (6 of 12 conceptual states)
    enums/evidence_source.py             EvidenceSource (Vision §8 origins)
    enums/trigger_origin.py              TriggerOrigin (COMPANION | CURIOSITY — who started the episode)
    events/domain_event.py               DomainEvent -> CognitiveEvent (immutable)
    events/episode_events.py             EpisodeStarted, EpisodeCompleted
    events/evidence_events.py            EvidenceAdded (shared by belief + hypothesis)
    events/belief_events.py              BeliefStrengthened, BeliefWeakened, ContradictionDetected
    events/hypothesis_events.py          HypothesisCreated
    value_objects/confidence.py          Confidence (immutable, validated [0,1])
    value_objects/evidence.py            Evidence (immutable, weighted, supports/contradicts)
    value_objects/temporal_stability.py  TemporalStability (immutable [0,1]; time axis, ≠ confidence)
    value_objects/episode_record.py      EpisodeRecord (immutable memory of a completed episode)
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
- **D19** Source→weight factors live in one policy (`SourceWeightingPolicy`), not scattered constants,
  and the policy is injectable (`EvidenceWeightingPolicy`). Effective weight = raw × source factor;
  the raw weight/source are never mutated (provenance preserved). `USER_STATEMENT` factor is 1.0 so
  prior USER_STATEMENT-based tests/behaviour are unchanged; other sources scale down.

---

## Next increment (recommended, not yet started)

**Ask, don't guess: an ungrounded episode requests the evidence it needs (Vision §16, §37).** Jarvis
already says "insufficient evidence" and, once it has learned the habit, "I am asking for evidence" —
but it never says *what* evidence would resolve the question. Vision §16 frames curiosity as naming a
valuable unknown; §37 wants uncertainty made explicit and actionable. The smallest honest step:
- When `think()` reaches an ungrounded or tentative conclusion, produce a structured
  `EvidenceRequest` (the working statement + what kind of observation would raise confidence), exposed
  on the episode (e.g. `episode.evidence_request`), not just embedded in the decision string.
- Keep it honest: the request is derived from the actual gap (no/low evidence), and disappears once
  the belief is grounded.
- Behaviour tests: an ungrounded `think()` yields an `EvidenceRequest` naming the statement; a
  grounded one yields none; the request references the question being asked.

*(Deferred, natural follow-ups: a real DB behind the JSON stores; persisting traces; semantic
trigger↔trait matching; recurring-goals/working-patterns facets; wiring `HypothesisSet` into episodes;
system-level weighting-policy injection + persistence; a `UnitInterval` base.)*

---

## Known limitations / not built yet

- `reflection` in the executive is still a placeholder (no genuine review of reasoning); the
  decision policy is a simple confidence threshold (D14).
- `HypothesisSet` exists but is **not yet wired into episodes** (episodes use a single belief).
- Stability is span-based only (no count/recency weighting yet); `TemporalStability` is derived for
  beliefs but not yet for hypotheses.
- Weighting policy is applied per-belief (default) but not yet injectable at the `Jarvis(...)` level.
- Persistence is process-lifetime only (`InMemoryBeliefStore`); no durable/DB store yet.
- Belief retrieval keys on the exact trigger string (D17), not semantic meaning of statements.
- Source-based weighting policy (Vision §11: explicit confirmation weighs more) not implemented —
  the caller assigns weight; `EvidenceSource` is recorded for when policy arrives.
- No goals, curiosity, memory, self-modeling. No persistence. No LLM.
- NervousSystem single-threaded synchronous drain only.
- ruff/pyright installed into the interpreter, not pinned in a lockfile.

---

## Open blockers

None.
