# Jarvis — Audit Remediation Report (Stage 2)

Date: 2026-09-14. Plan: `docs/claude/REMEDIATION_PLAN.md` (committed before any
production change, Stage 1). Implementation: 11 remediation commits on top of
the plan (Stage 2). Every finding below was re-verified against the repository
before planning, and every fix is proven by runtime behaviour, not by the
existence of classes.

## 1. Executive verdict

The gaps between architecture, claimed capabilities and observable behaviour
are closed for all P0 and P1 items. Jarvis now demonstrably: rejects replayed
evidence without losing independent confirmation; keeps a single authoritative
tuning state; persists justified learning across restarts and behaves
differently because of it; hydrates conversation, abstractions, graph
traversals, decisions, history and open questions across restarts and uses
them in later cognition; gates reflection; and refuses prompt/tool/memory
attacks at the domain boundary. The full suite (1767 tests) is offline,
deterministic and terminating; pyright strict reports 0 errors; ruff is
clean. Two P2 items are explicitly deferred with reasons (no silent drops).

## 2. Original audit findings vs verified current reality

| # | Finding (as received) | Verified reality | Verdict |
|---|---|---|---|
| P0-A | ~461 Pyright errors despite "clean" claims | 461 errors reproduced exactly (374 src + 87 tests). Root cause: post-split modules reaching into each other's privates (275 `reportPrivateUsage` in src alone), plus real defects (bad import, `Confidence\|float` ordering, untyped stream probe, 25 operator issues in tests, dead helpers) | CONFIRMED → FIXED |
| P0-B | Tests hang on real Google Calendar I/O | Reproduced precisely: `TestGoogleCalendarCommand` hung >5 min. Path: `handle()` → `snapshot()` → `_upcoming_events()` → live `list_events()` on a wired Google store. All transports have timeouts, so this was a bounded-stall-by-design in a path that must never read network, not an infinite hang | CONFIRMED (refined) → FIXED |
| P0-C | Split-brain CognitiveKnobs (adapt vs `knobs()`) | Reproduced exactly: executive adapted to 0.9 while `Jarvis.knobs()` stayed 0.5 | CONFIRMED → FIXED |
| P0-epi | 50× identical evidence → ~0.968 | Reproduced: 50× → 0.9259 (w=0.5; ≈0.98 at w=1.0). Default `_dedup_policy=None` appended unconditionally | CONFIRMED → FIXED |
| P0-learn | Adaptation evaporates on restart | Confirmed: no knobs/meta persistence in either factory | CONFIRMED → FIXED |
| P1-conv | Persistence without hydration | Confirmed: dual-write existed, deque never reloaded, `persistent()` volatile | PARTIALLY CONFIRMED → FIXED |
| P1-sem | SemanticMemory without producer/recall | Confirmed: zero callers of `abstract_patterns`, no factory wiring | CONFIRMED → FIXED |
| P1-graph | Graph writes, no reads | Confirmed: zero readers of `neighbors`/`path_between`; executive never received the store | CONFIRMED → decision below |
| P1-dec | Decisions written, not retrieved | Partially: fields persisted (SQLite) but JSON twin dropped them; no "why" query path | PARTIALLY CONFIRMED → FIXED |
| P1-temp | Timestamps without reconstruction | Not reproduced as a gap: replay-from-provenance existed but was coarse and unexposed | NOT REPRODUCED (as gap) → hardened + exposed |
| P1-unres | No first-class unresolved state | Confirmed: fragments only | CONFIRMED → FIXED |
| P1-gate | Cycle runs all stages unconditionally | Partially: episode gate existed, `reflect_cycle` ran everything | PARTIALLY CONFIRMED → FIXED |
| P2-pro | Proactive cognition | Exists as selection (curiosity cascade) without a wake loop | DEFERRED (reason §13) |
| P2-strat | Strategy learning | Statistics recorded; think-vs-consider suggestion unconsumed | PARTIALLY CONFIRMED → DEFERRED (reason §13) |

## 3. Remediation plan executed

`REMEDIATION_PLAN.md` phases 1–11 executed in dependency order (types →
offline guard → knobs → dedup → learning persistence → conversation →
semantic → graph decision → why/temporal → unresolved → gating), then the
adversarial pass, TEST J, docs and this report. No phase was declared
complete without its behavioural acceptance test; no capability was
duplicated (consolidations: introspection helpers, NEED_PREFIX ×3, goal
triple-layer delegation, serialiser sharing).

## 4. Changes by phase

- **P0-A** (`93b267a`): facades use public seams (new read-only
  repo/executive/ledger properties, `beliefs`-precedent); `EnergyLedger`
  unifies energy state; interface handlers compose per-module `COMMANDS`
  tables into a public router table; shared helpers renamed/moved;
  `introspection.py` deduplicated onto `actions`/`goals`/`capabilities`;
  dead forwarders/wrappers deleted; real defects fixed (HypothesisSet
  import, `Confidence|float`, stream probe matching the reasoner pattern,
  `RetrievedDocument.snippet`, store annotations); tests narrow at use.
- **P0-B** (`93b267a` + guard file): snapshot skips remote (Google) stores
  (D16, mail-block precedent); on-demand `calendar list` unchanged;
  `tests/test_offline_snapshot_guard.py` (hostile transport proves no read).
- **P0-C** (`93b267a`): executive owns live knobs; `Jarvis.knobs()`
  read-through; `set_knobs` forwards only.
- **P0-epistemic** (`d480721`): `same_observation()` default-ON across
  Belief/Hypothesis (+new seam)/SemanticMemory (D15); run/episode/gap/
  abstraction provenance for distinct world-events; 47 tests encoding
  inflation updated to independent observations (intents preserved).
- **P0-learning** (`61fe4e5`): `LearnedState` + repository contract, JSON +
  SQLite backends, both factories; executive notifies from adaptation paths
  only; explicit-wins precedence; corrupt recovery; `reset_learned_state`;
  sibling-knob reset bug fixed in the meta path.
- **P1-conversation** (`dc93d1a`): ring hydration at construction (bounded);
  new `JsonConversationStore`; `persistent()` durable.
- **P1-semantic** (`d192b0b`): `reflect_cycle` consolidates (idempotent);
  `JsonSemanticMemoryStore` (shared serialisers); SQLite wired; factories
  enable lexical recall; `semantic_memories` seam; server composition fixed.
- **P1-graph** (`fdc3ca6`): traversal read in `_recall_into` (depth-2,
  decaying relevance, new `GRAPH_NODE` kind); `knowledge_graph_store`
  plumbed through Jarvis/executive/factories/server; `JsonKnowledgeGraphStore`.
- **P1-history** (`e34402d`): `belief_timeline`/`what_changed`/
  `belief_snapshot_at`/`why_decision` (+`DecisionAccount`) on Jarvis; fixed
  JSON episode round-trip dropping `reflection_note`/`evidence_snapshot`.
- **P1-unresolved** (`2322399`): `UnresolvedItem` + repository, JSON +
  SQLite, note/recover/curiosity-impulse/investigate/resolve/history;
  resolutions ground as episode evidence.
- **P1-gating** (`025a610`): conditional hypothesise/challenge/learn chain;
  cycle reports its execution `path`.
- **Security** (`6411c36`): 11 adversarial tests (injection, tool gates,
  output-as-data, stored hostility, forged authority, prior-bound certainty).
- **TEST J** (`57a2a80`): full mistake lifecycle in one test.

## 5. Behavioural evidence

| Capability | Scenario (command/test) | Observed behaviour | Source files |
|---|---|---|---|
| Types | `pyright` | 0 errors, 0 warnings | all `src/`, `tests/` |
| Offline suite | `pytest tests` | 1764 passed, 3 skipped, ~100 s, no network | `interface/_state.py`, `test_offline_snapshot_guard.py` |
| Knobs | adapt in executive → `Jarvis.knobs()` | same object values, never stale | `jarvis.py`, `executive_controller.py` |
| Dedup | `test_evidence_identity.py` (17) | 50× replay, same-day flood, restart re-ingest: confidence frozen; independent source/day: grows | `evidence_identity.py`, entities |
| Learning | `test_learning_continuity.py` (7) | failures → 0.5→0.6+ → file → fresh boot keeps it → borderline probe now asks | `learned_state*`, executive, `jarvis.py`, `persistence.py` |
| Conversation | `test_conversation_continuity.py` (3) | Session B answers with Session A words via restored context | `conversation_context.py`, `json_conversation_store.py` |
| Semantic | `test_semantic_continuity.py` (3) | abstraction forms → restart → novel query selects SEMANTIC → answer shows it | `abstraction.py`, `cognitive.py`, retrievers |
| Graph | `test_knowledge_graph_continuity.py` (5) | 2-hop Charlie recalled; control empty; INFERENCE evidence; restart-safe | `executive_controller.py`, graph stores |
| Decision | `test_history_continuity.py` | post-restart account (decision, evidence, note); contradiction flips `same_today`, past intact | `jarvis.py`, `decision_account.py`, `json_episode_store.py` |
| Temporal | `test_history_continuity.py` | T1 answer A, now answer B, reconstructed identically after restart | `jarvis.py`, `temporal_reasoning.py` |
| Unresolved | `test_unresolved_continuity.py` (4) | Day1 open → Day2 recover + curiosity impulse → resolve → Day3 belief holds answer | `unresolved_*`, `curiosity.py`, `jarvis.py` |
| Gating | `test_reflective_cycle_gating.py` (4) | early path `(connect, reflect, act, scout)`; uncertainty extends it; evidence changes it | `cognitive.py`, `reflective_cycle.py` |
| Security | `test_adversarial_memory.py` (11) | injections ungrounded, gates refuse, output stays data, forgery bounded | boundary seams (no new code needed) |
| Full mistake | `TestFullLifeOfAMistake` | WITHHOLD persists + probe flips after restart | `test_learning_continuity.py` |

Acceptance tests A–J (§22) map 1:1 onto the files above (J in
`TestFullLifeOfAMistake`).

## 6. Persistence/restart evidence

Every continuity claim is a restart test (fresh runtime from the same
directory): learned knobs (JSON + SQLite), conversation rings (JSON +
SQLite), abstractions (JSON + SQLite), graph (JSON + SQLite), episodes +
trace (pre-existing, extended), beliefs/companions/actions (pre-existing),
unresolved items (JSON + SQLite). Corrupt-store recovery tested for learned
state; tolerant loads elsewhere preserved.

## 7. Epistemic integrity evidence

- Same object ×50: confidence bit-identical, one evidence stored.
- Fresh content-identical builds ×50 (same day): identical outcome.
- Restart re-ingest (ids/instants preserved by serialisers): identical.
- Independent source / day / provenance / near-duplicate: all grow
  confidence; cross-day replication also grows stability.
- Contradiction lowers; repeated identical contradiction does not compound.
- Production producers of distinct events carry identity (run ids, episode
  ids); manufacturing distinctness to evade the rule is forbidden (D15).

## 8. Learning continuity evidence

`test_adaptation_persists_and_changes_post_restart_behaviour`: baseline
probe grounds (0.5); 4 unfounded thinks adapt 0.5→0.6 with a recorded
reason; `learned.json` exists; fresh boot restores 0.6; the identical probe
now yields an evidence request. Database twin equivalent. Operator tuning
provably does not write learned state; explicit constructor knobs win;
reset restores defaults and survives reboot.

## 9. Dead architecture removed or integrated

Removed: ~20 dead forwarders/wrappers (Jarvis-private and GoalSurface
pass-throughs), triple-layer goal delegation, duplicated
action/goal/need helpers in `introspection.py`, 3× `_NEED_PREFIX`,
`Jarvis._run/_charge/_should_conserve`, unused test helper, uncalled
`_make_controller`. Integrated (previously dead): `abstract_patterns`,
graph `neighbors`/`path_between`, `COMMANDS` dispatch references,
`belief_timeline` family, episode `reflection_note`, `StreamEvent`
re-exports (via `__all__`). No `manager`/`engine`/`orchestrator` added (D12).

## 10. Knowledge Graph decision

**KEPT AND WIRED**, with evidence: relationship traversal demonstrably
retrieves what isolated retrieval cannot (2-hop entity sharing no tokens
with the query; graphless control empty; INFERENCE evidence; restart-safe
on both backends). Cost: one read method + one enum kind + two durable
stores reusing existing patterns. Not theatre: five behavioural tests,
production path (`think` → recall → reason).

## 11. Final technical baseline

- Tests: **1767 collected — 1764 passed, 3 skipped, 0 failed** (~100 s).
  Skips are pre-existing opt-ins (live LLM, socket smoke), unchanged.
- Pyright (strict, `include = ["src", "tests"]`): **0 errors, 0 warnings**.
- Ruff (E, F, I, UP, B, SIM): **clean**.
- Commits: plan (1) + 11 remediation commits, each with green gates.

## 12. Remaining limitations

- Same-day identical assertions collapse even when a human repeated
  deliberately (nagging does not convince; documented in the policy).
- Sub-day independence must be expressed via source/provenance (context).
- `same_today` compares support levels, not verdict text (bar moves don't
  confuse it, verdict flips at equal support are read as "same").
- Goal reaches need mixed channels or separate days to accumulate.
- Abstraction clustering is exact word-set matching (D11); recall is lexical
  unless an embedder is configured.
- Snapshot timelines skip remote stores by design (on-demand commands cover).

## 13. Deferred work

- **P2 proactive wake loop**: selection half exists (`feel_curious`,
  open-question impulses, pattern detection); the wake half needs
  shutdown-safe scheduling with rate limits/cancellation/observability.
  Deferred: no scheduler exists, and inventing one here would be a new
  framework (D12), not a seam.
- **P2 strategy-selection consumption**: threshold adaptation is consumed;
  the think-vs-consider suggestion has no automatic router to consume it.
  Deferred: adding a router to justify a metric would be theatre (§19).
- **Graph relation-aware recall**: traversal ignores relation types today
  (`neighbors` accepts the filter; the read path does not pass one).

## 14. Final four-dimension scorecard

Scale per item: PROVEN (behaviour demonstrated) / PARTIAL / UNPROVEN.

- **Architectural implementation** (the code exists and is coherent):
  types PROVEN, offline-suite PROVEN, knobs PROVEN, dedup PROVEN, learning
  PROVEN, conversation PROVEN, semantic PROVEN, graph PROVEN, decision
  PROVEN, temporal PROVEN, unresolved PROVEN, gating PROVEN, security
  PROVEN. Proactive PARTIAL (selection without wake). Strategy PARTIAL
  (threshold consumption without entry-point routing).
- **Production integration** (wired into live paths, not test-only):
  all of the above PROVEN (factories + server composition roots wire the
  new stores; recall/reason/snapshot/curiosity consume them). No test-only
  capabilities remain.
- **Behavioural proof** (runtime behaviour changed observably):
  PROVEN for every P0/P1 item (§5 table; acceptance A–J green). No phase
  rests on "a class exists".
- **Continuity** (state survives restart and matters afterwards):
  PROVEN for knobs, conversation, abstractions, graph, episodes, beliefs,
  decisions, history, unresolved items (restart tests on both backends).
  Meta-knowledge correctly derived rather than stored (documented).

## 15. Next three highest-value tasks

1. **Bounded proactive wake** (unblocks P2): a scheduler-owned `wake()`
   (one attention pass → at most one impulse pursued → state update) with
   persisted last-wake, rate limits and shutdown safety; the selection half
   is already proven, so this is now a small, safe build.
2. **Relation-aware graph recall**: pass relation filters from trigger cues
   (`works_on`, `knows`) into traversal; extends the proven read path.
3. **Retrieval-quality consumption**: close the remaining strategy loop by
   routing a real automatic choice (e.g., lexical-vs-embedding recall
   selection) off retrieval meta-observations, mirroring how attention
   already consumes its own.
