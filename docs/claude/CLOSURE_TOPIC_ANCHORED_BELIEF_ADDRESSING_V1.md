# Closure Record — Topic-Anchored Belief Addressing v1 (Model B)

**Date:** 2026-09-19
**Scope:** Formal closure of the *Topic-Anchored Belief Addressing* seam (Model B) after the
forensic integrity defect reported in `FORENSIC_CLOSURE_TOPIC_ADDRESSING_V1.md` was fixed and
verified.
**Method:** read-only re-verification of the addressing seam, canonical serializer fix
(`03dd42d`), focused persistence + addressing suites, full regression, lint and strict types.
**Verdict:** **PASS — FROZEN**

> Closure discipline honored: this step changed no implementation code and no tests. The only file
> created is this closure record.

---

## 1. Final verification trace (read-only, Part I)

| Condition | Status |
|---|---|
| `resolve_belief_for` is the working-belief addressing seam | PASS |
| `topic_id_of` remains the sole semantic identity source | PASS |
| `get_by_topic` implemented across the stores (in-memory, JSON, SQLite) | PASS |
| Legacy statement-keyed fragments reconcile deterministically (`reconcile_topic`) | PASS |
| Evidence (direction, neutrality, provenance, timestamps) preserved across reconciliation | PASS |
| Neutral evidence remains neutral across persistence (JSON + SQLite + semantic memory) | PASS |
| Contradictory evidence across paraphrases accumulates in one topic-anchored belief | PASS |
| Concept-free fallback remains statement/raw-trigger based | PASS |
| Different topics remain distinct (single-concept isolation intact) | PASS |
| Topic Identity v3 geometry not weakened | PASS |
| Actor blindness unchanged | PASS |
| Semantic-memory behavior unchanged except the serialization integrity fix | PASS |
| No live working-belief caller bypasses the addressing seam | PASS |

**The persistence defect is closed.** `Evidence.is_neutral` is now serialized and deserialized in the
canonical serializers (`json_belief_store._serialise_evidence` / `_deserialise_evidence`), inherited
by `SqliteBeliefStore` and `JsonSemanticMemoryStore`, and mirrored in
`sqlite_semantic_memory_store.serialise_memory`. Missing `is_neutral` defaults to `False` (legacy
payloads stay ordinary; no schema migration). No confidence, valence, negation, Evidence, Topic
Identity, or belief-addressing semantics changed.

**Gates at HEAD:**

| Gate | Command | Result |
|---|---|---|
| Focused persistence | `pytest tests/infrastructure/test_json_stores.py tests/infrastructure/test_sqlite_stores.py tests/infrastructure/test_semantic_memory_stores.py -q` | **38 passed** |
| Addressing/persistence regression | `pytest tests/semantic_attention/test_topic_anchored_addressing.py tests/semantic_attention/test_topic_identity_v3.py -q` | **38 passed** |
| Full | `python -m pytest -q` | **2169 passed, 3 skipped** |
| Lint | `python -m ruff check .` | **All checks passed** |
| Types | `python -m pyright` (strict, src + tests) | **0 errors, 0 warnings** |

## 2. Closed seam

`Topic-Anchored Belief Addressing v1 (Model B)`

## Frozen identity rule

For concept-bearing working beliefs:

> belief identity = canonical Topic Identity

Statement remains representative/display metadata.

## Frozen persistence rule

Evidence, including `is_neutral`, must survive persistence without semantic degradation.

## Frozen Topic Identity dependency

Belief addressing consumes Topic Identity.

It does not redefine or tune Topic Identity.

## 3. Accepted limitations (frozen, not defects)

- exact-topic addressing (`DELIVER > PROMISE > TIME` != `DELIVER`)
- no fuzzy/embedding belief matching
- concept-free raw-trigger fallback
- actor/entity blindness
- legacy read-time reconciliation
- no persistence schema change
- `{DELIVER}` remains distinct from `{PROMISE, DELIVER, TIME}`

## 4. Superseded criterion

> The original requirement that all five delivery-related triggers converge into one belief is
> superseded by the frozen Topic Identity v3 geometry. The fifth trigger contains
> `{PROMISE, DELIVER, TIME}` and must remain distinct from `{DELIVER}` because a single shared
> concept cannot unite different matters.

The Topic Identity tests are untouched; the superseded criterion did not re-define them.

## 5. History

- `c686fff` — Polarity Semantics Correction v1 (frozen)
- `8d4c1d1` — Aboutness-Only Topic Identity v1 (frozen)
- `46866af` — Topic-Anchored Belief Addressing v1 gate (Model B)
- `b978e4f` — Forensic Closure: **FAIL — DO NOT FREEZE** (`is_neutral` not persisted)
- `03dd42d` — Closure fix: neutral-evidence persistence (additive `is_neutral` key, default `False`)
- This record — **PASS — FROZEN**