# Forensic Closure — Topic-Anchored Belief Addressing v1 (Model B)

**Date:** 2026-09-18
**Scope:** Verification of the *Topic-Anchored Belief Addressing* seam (Model B) before freeze.
**Method:** code trace, empirical repro, focused + full regression suites.
**Verdict:** **FAIL — DO NOT FREEZE** (one confirmed integrity defect; see Finding 1).

> Hard-stop discipline honored: this audit changed **no code, no topic identity, no tests**.
> The `is_neutral` persistence defect is **reported, not fixed** (hard-stop rule: *neutral evidence
> changing belief polarity* → stop and report).

---

## 1. Model B definition and frozen decision record (read-only)

Frozen decision record (read, not re-litigated):
- **Topic Identity v3** (`src/jarvis/domain/services/topic_resolution.py`): a trigger's identity is its
  canonical concept signature; topics unify only when `|S n T| >= 2 AND (S <= T OR T <= S)`. A single
  shared concept must never unite different matters.
- **Addressing seam** (`src/jarvis/domain/repositories/belief_repository.py`): `resolve_belief_for`
  (topic-first), `belief_registry` (one shared reconciliation over stored beliefs), `reconcile_topic`
  (dedup + retain-first + weighted merge, topic leader becomes representative), `belief_topic_id`,
  `working_statement`. Model B docstring explicitly promises: no evidence loss, proof-preserving
  contradiction accumulation, **neutral evidence preserved and neutral**, deterministic order,
  no read-time mutation, no cache/memo, statement-addressed kinds and the legacy net untouched.
- **Store wiring invariant:** identity lookups route through `repository.get_by_topic` only;
  statement-addressed kinds (companion, goals, subgoals, actions, reversibility, needs) keep
  statement identity by design.

## 2. Runtime addressing path (verified end-to-end)

`trigger -> working_statement(trigger) -> belief_topic_id (topic_resolution.topic_id_of) ->
repository.get_by_topic (belief_registry.reconcile_topic) -> fallback get_by_statement -> new Belief`.

Every live working-belief caller routes through `resolve_belief_for`:

| Caller | Location | Path |
|---|---|---|
| `ExecutiveController` (main) | `executive/executive_controller.py:748` | OK |
| `cognitive.act_on_insight` | `cognitive.py:302` | OK |
| `curiosity.ask_about` | `curiosity.py:269` | OK |
| `Jarvis.confirm` | `jarvis.py:2471` | OK |
| `Jarvis.why_decision` | `jarvis.py:2614` | OK |
| `interface._cognition._explain` | `interface/_cognition.py:41` | OK |

No live working-belief path bypasses the seam (see section 10).

## 3. Reconciliation geometry and invariant verification (B1-B12)

Empirical and code-traced results:

| Invariant | Status |
|---|---|
| B1 identity: same topic merges | PASS |
| B2 representative/leader stable | PASS |
| B3 evidence preserved, incl. **neutral** | PASS in-session / **FAIL after JSON/SQLite persistence** |
| B4 evidence order deterministic | PASS |
| B5 reconciliation idempotent | PASS |
| B6 same semantic belief survives round-trip | PASS non-neutral / **FAIL neutral evidence degrades** |
| B7 no-topic fallback (raw-trigger topics stay distinct) | PASS |
| B8 different topics never merge | PASS |
| B9 contradiction accumulation = direct-statement confidence, both orders | PASS in-session / **FAIL after persistence reload** |
| B10 neutral does not raise support | PASS in-session / **FAIL after persistence reload** |
| B11 replay after concurrency safe, dedup keeps first | PASS |
| B12 semantic boundary (canonical subsets never fuse) | PASS |

**Defect:** B3/B6/B9/B10 fail across persistence. Root cause and proof in Finding 1.

## 4. Five-trigger corpus (classified SUPERSEDED, not a defect)

Verified trigger signatures:

| Trigger | Signature | Topic |
|---|---|---|
| "supplier failed to deliver" | `{DELIVER}` | `DELIVER` |
| "supplier succeeded in delivering" | `{DELIVER}` | `DELIVER` |
| "delivery from the supplier failed" | `{DELIVER}` | `DELIVER` |
| "the supplier did not deliver" | `{DELIVER}` | `DELIVER` |
| "supplier keeps promising delivery dates that fail" | `{PROMISE, DELIVER, TIME}` | `DELIVER > PROMISE > TIME` |

The old "all five are the same belief" criterion is **incompatible with the frozen v3 geometry**
(`{DELIVER}` vs `{PROMISE, DELIVER, TIME}` share only `DELIVER`; `|S n T| = 1 < 2`). This is the
historically-frozen reason the fifth trigger is intentionally separate. **Classified SUPERSEDED, not
a defect.** Old acceptance test left untouched (audit must not re-define the frozen decision).

## 5. Actor blindness

Documented as intentional (role nouns -> `ROLE`, contributing nothing to a signature:
`abstraction.py`; `SEMANTIC_COGNITION_IMPLEMENTATION.md` section 2). Empirically verified:
`supplier` / `vendor` / `contractor` + "failed to deliver" -> all `DELIVER`, one belief. Not an
accidental regression.

## 6. Legacy reconciliation (congruence with 2026-09-11 decision)

Read-time reconciliation verified: evidence fully preserved (incl. neutral, parts, provenance),
no evidence loss, no duplication, idempotent repeated reads, save/reload stable, statement
fragments remain readable for historical narration via `get_by_statement`. No schema change.
Same behavior in `JsonBeliefStore` and `SqliteBeliefStore` for non-neutral evidence.

## 7. Determinism

Replays across all three stores are structurally deterministic: identical unified structure, leader,
evidence order (stable chronological by `observed_at`; ties in stored order), and in-session
confidence. Residual, intentional equivalence only — the actor-blindness abstraction.

## 8. Regression suite

| Gate | Command | Result |
|---|---|---|
| Focused | `pytest tests/semantic_attention/test_topic_anchored_addressing.py tests/semantic_attention/test_topic_identity_v3.py -q` | **38 passed** |
| Full | `python -m pytest -q` | **2157 passed, 3 skipped** |
| Lint | `python -m ruff check .` | **All checks passed** |
| Types | `python -m pyright` (strict via `pyproject.toml`, includes `tests`) | **0 errors, 0 warnings** |

Notes: strict is config-driven (`[tool.pyright] typeCheckingMode: strict`, `include: [src, tests]`);
`--strict` CLI is not supported by this pyright build. The suite is green, **but no round-trip test
exercises neutral evidence**, which is why Finding 1 went undetected.

## 9. Architectural leakage

- `topic_resolution` is the **single** authoritative identity source; `topic_id_of` is imported and
  used only by `belief_repository`.
- `resolve_episodes` consumed only by `attention_priority` (read-side projection).
- All three stores' `get_by_topic` delegate to the **one** shared `belief_registry`.
- No repo-specific semantic identity rules; no hidden statement caches; no memo (identity is
  recomputed on read; the only memo is `signature_of`'s bounded `lru_cache`).
- No hard-coded matter-specific addressing (`DELIVER` appears only as general vocabulary in
  `abstraction.CONCEPT_MAP`, not in addressing).
- No schema duplication: belief tables remain `(statement TEXT PRIMARY KEY, payload TEXT NOT NULL)`.

**Leakage: none found.**

## 10. Caller audit

All live working-belief resolution routes through `resolve_belief_for` (section 2). Remaining
`get_by_statement` calls are intentional:
- Statement-addressed kinds (identity is the statement): companion, goals/subgoals, actions,
  reversibility, needs (`companion_model.py:52,66`, `goals.py`, `actions.py:83,116,137,157`,
  `capabilities.py:77,204`, `introspection.py:138`).
- Inspection command `interface/_cognition.py:307` (show one stored belief).
- Compat display for the belief web / connection narration (`cognitive.py:213`).
- The seam's own statement fallback net.

None produces a correctness or integrity problem.

## 11. Finding 1 — CONFIRMED integrity defect: `is_neutral` is not persisted

**Location:** `src/jarvis/infrastructure/json_belief_store.py` — `_serialise_evidence` /
`_deserialise_evidence` (payload keys: `content, source, weight, supports, context, provenance,
observed_at, id`; no `is_neutral`); `src/jarvis/infrastructure/sqlite_belief_store.py` reuses the
same serializers; `src/jarvis/infrastructure/sqlite_semantic_memory_store.py` —
`serialise_memory` (same omission for semantic-memory evidence).

**Consequence:** `Evidence(is_neutral=True)` round-trips as `Evidence(is_neutral=False)` (a
*supporting* piece). Confidence/stability are re-derived from evidence on every load, so a stored
belief that contains neutral evidence gains artificial support after reload.

**Proof (empirical repro, both JsonBeliefStore and SqliteBeliefStore):**
- Save one neutral piece -> reload: `is_neutral` False, belief confidence `0.0 -> 0.2307` (3/13).
- A conflicting replay whose in-memory confidence was `0.25` (neutral counted) becomes `0.40` after
  JSON/SQLite reload (neutral converted to support).
- Same for `JsonSemanticMemoryStore` / `SqliteSemanticMemoryStore` (semantic-memory confidence also
  re-derived from persisted evidence).

**Violations:** B3 (neutral must remain neutral), B6 (same semantic belief survives round-trip),
B9 (persisted contradiction behavior diverges from direct statements), B10 (neutral must not add
support), and the hard-stop rule *"neutral evidence changing belief polarity"*.

**Bearing:** pre-existing, not introduced by this addressing change (`git log -S is_neutral` on both
files: zero commits — the field was never serialized). In-memory behavior is correct (object
identity preserved). The seam's promises in-session hold; the long-term persistent stores
(JSON file and SQLite, the production modes) violate them for any belief or memory containing
neutral evidence.

**Suggested fix (NOT applied — hard-stop report-only):** add `"is_neutral": evidence.is_neutral`
in `_serialise_evidence` and `is_neutral=...` in `_deserialise_evidence` (additive key, no migration),
mirror in `sqlite_semantic_memory_store.serialise_memory`, and add a persistence round-trip test
that includes a neutral piece.

## 12. Final verdict

**FAIL — DO NOT FREEZE**

The addressing logic itself (geometry, reconciliation, fallbacks, actor blindness, determinism,
caller wiring, leakage) is correct and verified. The freeze is blocked by one actual integrity
defect in the seam's persistence path: neutral evidence changes polarity across reload, corrupting
derived confidence for every stored belief/memory containing a neutral observation. This matches the
audit's hard-stop trigger exactly.

The five-trigger acceptance conflict is **not** a ground for this verdict; it is a superseded
criterion, and the frozen Topic Identity geometry is itself intact.

## 13. Closure record

- No code, topic-identity, or test changes were made during this audit.
- The seam **cannot be frozen** until the `is_neutral` persistence defect (Finding 1) is
  implemented and covered by a round-trip test that includes neutral evidence.
- On that condition, the seam is otherwise clean to freeze: 2157 pytest green, ruff clean,
  pyright strict 0 (tests included), no leakage, all live callers on the seam, legacy
  reconciliation idempotent and loss-free.
- Frozen limitations carry forward and are accepted, not defects: exact-topic addressing
  (`DELIVER > PROMISE > TIME` != `DELIVER`), actor blindness, concept-free fallback (raw-trigger
  topics stay distinct), no fuzzy matching, legacy read-time reconciliation, no schema change.