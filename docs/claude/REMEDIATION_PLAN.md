# Jarvis — Audit Remediation Plan (Stage 1)

Date: 2026-09-13. Baseline: 1704 tests collected, ruff clean, pyright **461 errors**
(374 in `src/`, 87 in `tests/`). Epistemic repro: 50x identical evidence →
confidence **0.9259** (weight 0.5; ≈0.98 at weight 1.0). Knobs split-brain repro:
`Jarvis.knobs()` stays 0.5 after `executive.set_knobs(0.9)`.

This plan was written AFTER verifying every audit finding against the repo.
Status words: CONFIRMED / PARTIALLY CONFIRMED / NOT REPRODUCED.

## A. Verified findings

### P0-A — Type checking: CONFIRMED (count exact, category different from lore)
- `pyright` (strict, `include = ["src", "tests"]`): **461 errors, 0 warnings**.
- `src/` (374): `reportPrivateUsage` 275, `reportUnusedFunction` 41,
  `reportUnknownMemberType` 14, `reportUnknownVariableType` 9,
  `reportUnusedImport` 3, misc 4. Root cause is the Phase-0 god-object split:
  facade modules (`surfaces.py` 65, `command_center.py` 33, `edges.py` 29,
  `cognitive.py` 27, `capabilities.py` 24, `goals.py` 22 …) reach into the
  Jarvis root's privates (`_task_scheduler` 20, `_capabilities` 17,
  `_documents_store` 16, `_notes_store`/`_calendar_store` 12, `_knobs` 9,
  `_fresh_belief` 8, …). Real encapsulation debt, not config fiction.
- `tests/` (87): `reportOperatorIssue` 25 in `test_command_center.py` (real
  type defects) + `reportPrivateUsage` in white-box tests (`_executive`,
  `_episodes`, `_should_reflect`).
- No scope-hiding in config (`pyproject.toml` includes all of src+tests,
  strict). Fix must be code, not config.

### P0-B — Test suite hangs on real network I/O: PARTIALLY CONFIRMED
- Every network edge has an injectable transport + bounded timeout
  (`google_calendar.py:48-50,79`, `agent_reach_source.py:57-59,87`,
  `mail_source.py:46-69,97`, `openai_compatible_model.py:39-54`,
  `odysseus_search_source.py:50-52`, `whisper_transcriber.py:32-37`).
  No unbounded hang exists; worst case is a bounded 15–120 s stall.
- Residual risk is real: `build_google_calendar_store()` /
  `build_*_store()` return live adapters whenever env creds are present, and
  nothing stops a test (or a dev's env leak) from constructing one without the
  fake transport. `GoogleCalendarStore` tests themselves use a fake
  (`tests/test_google_calendar.py:50`). So: "hangs indefinitely" NOT
  REPRODUCED; "tests can touch real network when env is configured"
  CONFIRMED as a latent risk. Remediation: regression guard, not a rewrite.

### P0-C — Split-brain CognitiveKnobs: CONFIRMED
- `Jarvis._knobs` (`jarvis.py:626`) and `ExecutiveController._knobs`
  (`executive_controller.py:186`) are two independent copies.
- `Jarvis.set_knobs` forwards to the executive (`jarvis.py:2004-2005`), but
  the executive's own adaptation (`executive_controller.py:415-423`
  `adapt_knobs_from_self_observation` → `self.set_knobs`, plus
  `adapt_from_meta_observation:270-278` mutating `self._knobs`) never writes
  back. Repro script: after `executive.set_knobs(0.9)`, `jarvis.knobs()`
  still returns 0.5. The command-center sliders (`_cognition.py`) and
  `Jarvis.knobs()` therefore show stale values after learning.
- Ownership decision: the **executive owns the live knobs** (it gates
  cognition); `Jarvis.knobs()` becomes a read-through delegate, and every
  mutation path funnels through one setter that syncs both (or a single
  shared reference). No duplicate objects.

### P0-epistemic — Duplicate evidence inflates confidence: CONFIRMED
- `Belief.add_evidence` (`belief.py:239-253`): `_dedup_policy` defaults to
  `None` → "historical default: append unconditionally". Derive is pure
  mass-counting (`supporting / (supporting + contradicting + 1)`).
- Measured: 1x evidence (w=0.5) → 0.2857; 50x identical → **0.9259**.
  Invariant violated: strength grew from repetition, not information.
- Identity design (reuse domain model, no parallel system): `Evidence` already
  carries `id`, `content`, `source`, `weight`, `supports`, `context`,
  `observed_at`. Policy: **same observation re-injected (same `id`) is always
  a no-op; same claim re-observed gets diminishing weight only when it is
  genuinely independent** (different `id` + different `observed_at` event or
  different `source`/provenance). Default must be ON for beliefs created on
  the episode path; exact fingerprint documented in `belief.py` + DECISIONS.

### P0-learning — Adaptation does not survive restart: CONFIRMED
- Adaptation is in-memory only (`jarvis.py:626`,
  `executive_controller.py:186,415-423`). `persistence.py:86-136` and
  `infrastructure/sqlite_database.py:24-78` persist beliefs/episodes/trace/
  capabilities/refutations — **no knobs table, no meta-knowledge store
  wiring**. Restart resets thresholds and learned meta-knowledge.
- Smallest architecture-consistent model: persist a `learned_knobs` record +
  durable `MetaKnowledge` entries behind existing repository contracts
  (new narrow `LearnedStateRepository` protocol only if no existing contract
  fits; prefer extending the capability/need JSON+SQLite pattern, D10).
  Bounded, inspectable, evidence-backed, reversible, small-sample resistant.

### P1-conversation: PARTIALLY CONFIRMED
- Writes exist (SQLite conversation store, dual-write in
  `conversation_context.py:47-63`). Short-term `ConversationContext` never
  preloads on restart (`__init__:39-45`); `persistent()` uses in-memory store
  (`persistence.py:82`). Old turns reach cognition only via lexical/semantic
  recall (`memory_candidates.py:127-136`), not as conversational context.
- Fix: hydrate recent turns into `ConversationContext` on boot (bounded N)
  for `database()`/`persistent()`; keep prompt injection bounded (recent +
  retrieved, never whole history).

### P1-semantic: PARTIALLY CONFIRMED
- Entity/service/stores/retrievers exist; **zero production callers of
  `abstract_patterns()`**; `persistent()/database()` never wire a semantic
  store (`jarvis.py:388,588` default `None`); embedding recall opt-in only.
- Fix: wire store in both factories, call abstraction at a bounded point
  (episode close / reflect), prove recall→reasoning influence.

### P1-graph: CONFIRMED (write-only)
- Write path (`executive_controller.py:849-857`); zero readers of
  `neighbors()/path_between()` in `src/`; `jarvis.py:627-637` never passes
  `knowledge_graph` into the executive. Decision gate required:
  KEEP AND WIRE (one traversal-matters scenario) / KEEP BUT DEFER (named
  blocker) / RETIRE. Lean: wire one443f concrete traversal (multi-hop
  recall: A→B→C where isolated retrieval misses C) or retire honestly.

### P1-decision-history: CONFIRMED as stored+queryable, PARTIAL as usable
- `EpisodeRecord.reflection_note/evidence_snapshot` populated
  (`executive_controller.py:823-846`), durable in SQLite+JSON, `history*`
  queries exist. Only substring `trigger` search — no "why did we decide"
  answer path. Fix: one grounded `why_decision()` query (recorded vs
  reconstructed vs current interpretation, never fabricated).

### P1-temporal: NOT REPRODUCED as gap (replay exists, coarse)
- `belief_timeline/what_changed/belief_snapshot_at`
  (`temporal_reasoning.py:76-185`) rebuild snapshots from episode history,
  not current state. Gap is resolution (substring match, last-before-time, no
  diff). Keep: smallest API to answer T1/T-now + what changed; no new system.

### P1-unresolved: CONFIRMED missing
- Only fragments (`EvidenceRequest`, `Challenge`, `ContradictionDetected`,
  undecided branch). No `UnresolvedItem` lifecycle. Reuse goal/episode
  infrastructure; do not build a duplicate task manager.

### P1-reflection-gating: PARTIALLY CONFIRMED
- `_should_reflect` (`executive_controller.py:700-720`) gates only the
  episode-path reflect (`:394`); `reflect_cycle()` (`cognitive.py:275-296`)
  runs all stages unconditionally. Fix: route the cycle through the same
  gate (early stop / continue / record-unresolved), prove 4 behaviours.

### P2-proactive / P2-strategy-learning: DEFERRED by dependency order (§D)
- Proactive exists as curiosity cascade + `detect_pattern` wiring (Phases
  8/10) but without stable continuity foundations it must stay bounded and
  read-only-ish. Strategy statistics without consumption are theatre; wire
  consumption or defer.

### Security/poisoning: standing requirement
- Preserved boundary `LLM proposes → domain evaluates → domain persists →
  domain authorizes` (§37/guardrail/registry gates). Every phase adds an
  adversarial test (injection, poisoned memory/evidence, provenance
  manipulation, fake approval, duplicate-abuse).

## B. Priority
- **P0**: A (pyright), B (offline suite), C (knobs), epistemic dedup,
  learning persistence.
- **P1**: conversation hydration, semantic wiring, graph decision,
  decision-why, temporal resolution, unresolved lifecycle, reflection gating.
- **P2**: proactive bounded wake (only if P0+P1 stable), strategy learning
  (only if it consumes stats).
- **P3**: cleanup of dead helpers found by `reportUnusedFunction`.

## C. Implementation phases
1. **P0-A types**: expose narrow public seams on `Jarvis` for what its own
   facades need (`executive`, stores, `_fresh_belief`→`fresh_belief`-or-equivalent,
   energy/goal internals); rewrite facade call sites `_jarvis._x`→`_jarvis.x`;
   public `should_reflect` alias consumed by tests + `reflect_cycle`; delete
   or justify every `reportUnusedFunction`; annotate unknown-member/variable
   sites; fix 25 `test_command_center` operator issues. Invariant: no
   `reportPrivateUsage` suppression, no scope exclusion, strict stays.
   Tests: `pyright` 0 errors + full suite green. Acceptance: `pyright` prints
   `0 errors`. Rollback: pure renames/additive properties; revert per file.
2. **P0-B offline suite**: regression test: builders return `None` without
   env; socket-guard test (no `urlopen`/IMAP/SMTP construction in default
   suite without fake transport — via monkeypatched transport asserting
   unused); document bounded-timeout table. Acceptance: suite passes with
   hostile env vars set (except explicit opt-in smoke test).
3. **P0-C knobs**: single ownership (executive authoritative; `Jarvis.knobs()`
   delegates; one syncing setter; adaptation writes through it). Tests:
   adapt-then-read consistency both directions. Acceptance: repro script
   shows agreement.
4. **P0-dedup**: default-ON identity policy in `Belief` (+ `Hypothesis`
   parity): same `id` → skip; same
   `(content, source, supports, context)` with same `observed_at` instant →
   skip; independent (`source` differs, or `observed_at` differs with
   distinct `id`/provenance) → counted, with sublinear credit so N repeats
   cannot asymptote to 1 (cap repeated-identical mass). 8 behavioural tests
   (§3.1–3.8). Restart test: re-ingest after rehydration still dedups.
   Invariant: D3 (no confidence setter), auditability (skips recorded as
   events, not silent drops… or explicit skip-count; decide in code).
5. **P0-learning persist**: `LearnedState` (knobs + meta-knowledge refs +
   evidence links + bounds) behind repository contracts, JSON + SQLite,
   wired in `persistent()`/`database()`; restore on boot; adaptation writes
   through; bounds/rollback (`reset_learned_state`). End-to-end §4
   experiment as a test (baseline → failure → adapt → persist → fresh
   `Jarvis` from same dir → adapted behaviour on same problem class).
6. **P1-conversation**: bounded hydration (last N turns) into
   `ConversationContext` on boot for both factories; test Session A →
   restart → Session B influence; cap prompt contribution.
7. **P1-semantic**: wire store in factories; bounded abstraction call;
   9-step experiment test (experiences → abstraction → persist → restart →
   related novel query → candidate → selected → reasoning → influence).
8. **P1-graph decision**: implement traversal-recall scenario; KEEP AND WIRE
   iff it beats isolated retrieval, else DEFER (named blocker) or RETIRE
   (delete wiring, keep entity? no — remove or integrate, §19).
9. **P1-why/temporal/unresolved/gating**: `why_decision()` grounded answer;
   T1/T-now/what-changed test; `UnresolvedItem` lifecycle on goal/episode
   infra; `reflect_cycle` through `should_reflect` with 4 gating tests.
10. **P2 (gated)**: bounded proactive wake + strategy-consumption, only if
    P0+P1 green; else explicitly deferred in report.
11. **Adversarial pass + docs + report**: per-phase adversarial tests;
    update ARCHITECTURE/AI_CONTEXT/STATUS minimally; write
    `REMEDIATION_REPORT.md` with four-dimension scorecard.

## D. Dependency order
Types first (otherwise later edits rot the baseline) → offline guard (so all
later behavioural tests are trustworthy) → knobs single-source (dedup and
learning both mutate/read thresholds; must agree first) → dedup (learning
must not learn from inflated confidence) → learning persistence (needs
stable knobs+dedup semantics) → conversation/semantic (continuity consumers
of the now-stable core) → graph decision (needs recall consumers to compare
against) → why/temporal/unresolved/gating (need history that P0/P1 produce)
→ P2 last (needs everything). No proactivity before continuity; no strategy
learning before persistent adaptation works.
