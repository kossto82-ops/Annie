# Jarvis — Implementation Status

Living document. Updated at the end of every increment. Single source of truth for
"where are we / what's next". No other progress docs — extend this one.

**North star:** `JARVIS_VISION.md` (repo root) is the objective every increment must move
toward. STATUS.md tracks *where we are*; JARVIS_VISION.md defines *where we are going*.
Every implementation decision must preserve the possibility of reaching that architecture
(Vision §41). Current code has no contradictions with the vision (verified 2026-08-21).

Last updated: 2026-08-21 (Increment 6)

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
  executive/executive_controller.py      orchestrates one episode's lifecycle
  infrastructure/in_memory_belief_store.py   InMemoryBeliefStore (BeliefRepository impl)
  domain/
    repositories/belief_repository.py    BeliefRepository (Protocol) — persist/retrieve beliefs
    aggregates/cognitive_episode.py      CognitiveEpisode (aggregate root) + InvalidStateTransition
    aggregates/hypothesis_set.py         HypothesisSet (competing hypotheses) + UnknownHypothesis
    entities/belief.py                   Belief (entity) + derive_confidence + BeliefExplanation
    entities/hypothesis.py               Hypothesis (entity, evidence-derived confidence)
    enums/episode_state.py               EpisodeState (6 of 12 conceptual states)
    enums/evidence_source.py             EvidenceSource (Vision §8 origins)
    events/domain_event.py               DomainEvent -> CognitiveEvent (immutable)
    events/episode_events.py             EpisodeStarted, EpisodeCompleted
    events/evidence_events.py            EvidenceAdded (shared by belief + hypothesis)
    events/belief_events.py              BeliefStrengthened, BeliefWeakened, ContradictionDetected
    events/hypothesis_events.py          HypothesisCreated
    value_objects/confidence.py          Confidence (immutable, validated [0,1])
    value_objects/evidence.py            Evidence (immutable, weighted, supports/contradicts)
    value_objects/temporal_stability.py  TemporalStability (immutable [0,1]; time axis, ≠ confidence)
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

---

## Next increment (recommended, not yet started)

**Source-based evidence weighting + explicit-confirmation strength (Vision §11).** Today the caller
assigns each `Evidence.weight` by hand and `EvidenceSource` is recorded but unused. The vision wants
the *source* to shape how much a piece of evidence counts: explicit confirmation from the companion
should weigh strongly; a single isolated observation weakly; repeated behaviour more than a one-off.
- A small domain policy mapping `EvidenceSource` (+ supports/contradicts) to an effective weight,
  applied when evidence enters a belief — without losing the raw weight (provenance stays intact).
- Enacts §11 directly: `USER_STATEMENT` (explicit confirmation) > `REPEATED_BEHAVIOR` > a lone
  `DIRECT_OBSERVATION`. Keep it a named, testable policy object, not scattered constants.
- Behaviour tests: identical raw weight but different source yields different effective contribution;
  explicit confirmation outweighs an isolated observation; the policy is injectable.

*(Deferred, natural follow-ups: episodic memory of past episodes; wiring `HypothesisSet` into
episodes; a durable (DB-backed) `BeliefRepository`; a `UnitInterval` base if a third [0,1] type appears.)*

---

## Known limitations / not built yet

- `reflection` in the executive is still a placeholder (no genuine review of reasoning); the
  decision policy is a simple confidence threshold (D14).
- `HypothesisSet` exists but is **not yet wired into episodes** (episodes use a single belief).
- Stability is span-based only (no count/recency weighting yet); `TemporalStability` is derived for
  beliefs but not yet for hypotheses.
- Source-based evidence weighting (Vision §11) not implemented — caller sets `weight`; `EvidenceSource`
  is recorded but does not yet influence contribution (next increment).
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
