# ARCHITECTURE GATE — EPISODE EVIDENCE-REQUEST WRITER v1

Verdict: **PASS WITH FINDINGS — READY FOR IMPLEMENTATION**

Date: 2026-09-20
HEAD: `331eb48` (Increment 169). Dirty/untracked at start: the pre-existing
`FORENSIC_CLOSURE_EPISODE_PATH_REASONINGSPAN_V1.md` plus the previous rejected gate's
report (untracked). Nothing else; nothing modified by this gate except this report. No commit.

Frozen context honored: Topic Identity v3, Topic-Anchored Belief Addressing v1, Polarity
Semantics v1, Episode-Path ReasoningSpan v1, knowledge-graph context-only invariant,
the existing UnresolvedItem persistence model, and the existing
`resolve_open_question()` provenance semantics are untouched. The composite proposal
(`UNSETTLED-COGNITION WIRING v1`) is not reopened.

---

## A. Verdict

**PASS WITH FINDINGS — READY FOR IMPLEMENTATION**

The existing `EvidenceRequest` produced by a qualifying conclusion episode can be
safely connected to the existing `UnresolvedItem` lifecycle — provided the occurrence
predicate in section C is applied and the exact-string write guard is used. No schema,
no model change, no store change, no event type, no `resolve_open_question` change, no
`_engage_reply` change, no curiosity/wake/ReasoningSpan change. All inferred from the
repository itself; full evidence below.

---

## B. EvidenceRequest inventory

Construction sites (all of them; `src/` grep): `ExecutiveController._maybe_request_evidence`
(`executive_controller.py:1129`, conclusion path) and the inline construction in
`ExecutiveController.deliberate` (`executive_controller.py:718`, undecided deliberation).
No other production site creates an `EvidenceRequest`.

| EvidenceRequest origin | Example trigger | Current purpose | Should persist? | Why |
|---|---|---|---|---|
| Ungrounded conclusion (COMPANION, FULL) | `"does my companion prefer simplicity?"` (no evidence) | Names the evidence a companion-initiated full episode could not ground | YES | Question-shaped, externally asked, genuinely open; the intended semantics |
| Tentative conclusion (COMPANION, FULL) | same trigger, weak support | Same, with 0 < confidence < grounded | YES | Same class at lower confidence; still ungrounded at completion |
| BRIEF/CHEAP/conserve episode left ungrounded | stored thin belief + no evidence, answered briefly | Request attached because the stored belief is below threshold | NO | Deliberate shallow routing, not an investigation target |
| Statement/remember stored under a raised threshold | taught memory that no longer reaches threshold | Statement taught to Jarvis | NO (excluded by question-shape) | A declaration, not a question worth pursuing |
| confirm/resolve episodes that fail to ground (only under a learned raised threshold) | the companion's earlier question, re-confirmed | Companion feedback | YES | The companion genuinely asked; still ungrounded under the strict standard |
| Undecided deliberation (no leader) | `"my companion went quiet mid-project"` | Request on the `Deliberation` value, never attached to the episode | NO (out of v1 scope) | Different semantics (hypothesis competition); not reachable at the conclusion boundary |
| Deliberation with a low-confidence leader | same observation, weak leader | No request at all | — | Not an EvidenceRequest source |
| Investigation echo (CURIOSITY) | `"Investigate the open question: X"` | Self-initiated pursuit episode | NO | Self-generated; excluded by origin |
| `learn_from_external` subject lacking question-shape | `"supplier X financials"` | External ingest that fails to ground | NO (v1 false negative, accepted) | Not phrased as a question by the companion |
| Grounded conclusions | any | No request produced | — | `evidence_request is None` |

Not all EvidenceRequests are equivalent: only the COMPANION-origin, FULL-attention,
question-shaped, ungrounded conclusion class carries the "open question worth
persisting" meaning.

---

## C. Occurrence predicate

The predicate is expressible entirely with state that exists today.

```
P(episode) persists an unresolved item ⟺
  1. episode.evidence_request is not None          # ungrounded conclusion (executive_controller.py:1129)
  2. episode.origin is TriggerOrigin.COMPANION       # external, not self-generated (enums/trigger_origin.py)
  3. episode.attention is Attention.FULL             # actually reasoned (enums/attention.py)
  4. trigger is question-shaped                      # "?"-suffixed or interrogative cue — the exact
                                                     # is-question line already used by
                                                     # _looks_like_self_question (executive_controller.py:170)
  5. no OPEN item has item.question == request.question   # exact-string guard over existing open_questions()
```

If all five hold → `note_open_question(episode.evidence_request.question)`.

Findings on the dimensions:

* **Origin (2)** is the structural recursion guard (section D). `TriggerOrigin` has
  exactly two values (`COMPANION`, `CURIOSITY`); the investigation echo is built with
  `origin=CURIOSITY` (`curiosity.py:315`), the same origin-based discrimination the
  rest of the codebase already uses for attention/abstraction inputs.
* **Attention (3)** is a real routing signal: BRIEF means "answered from existing
  understanding, not fresh grounding" (Vision §14). The request is still attached in a
  CHEAP/conserve-unforced-BRIEF ungrounded completion; FULL excludes those.
* **Question-shape (4)** reuses the existing vocabulary (`?` suffix or the executive's
  `_QUESTION_CUES` set), i.e. the `is_question` line of `_looks_like_self_question`.
  It is the dimension that removes the statement/declaration class (the strongest
  residual false-positive source under a learned raised threshold). If private-name
  import from `executive_controller` is undesired, expose the existing check via a
  public alias; it is reuse, not a new classification framework.
* **Dedup (5)** uses the unresolved model's own identity (exact string equality, the
  same comparison `resolve_open_question` uses) via existing `open_questions()`.
  Section E shows this guard is **required**, not optional: without it the existing
  `test_unresolved_continuity.py::test_full_lifecycle_across_restarts` would break.
* No embeddings, no fuzzy matching, no new value object, no schema are needed. The
  predicate does not use anything that does not exist in the codebase.

---

## D. Self-recursion analysis

Trace (from code):

```
UnresolvedItem "X"
  → feel_curious fallback: impulse.trigger = "Investigate the open question: X"   (curiosity.py:224)
  → pursue(): CognitiveEpisode(trigger="Investigate the open question: X",
                               origin=TriggerOrigin.CURIOSITY)                     (curiosity.py:313-318)
  → executive.run(): ungrounded → attaches its own transient EvidenceRequest       (executive_controller.py:643)
```

That episode **can** produce another `EvidenceRequest` (it is ungrounded), but under
predicate clause 2 it **cannot** create another item: its `origin` is `CURIOSITY`, and
`TriggerOrigin.CURIOSITY` is definitionally "Jarvis initiated it to reduce its own
uncertainty" (`trigger_origin.py:17`). No string normalization is used; the origin guard
is structural and matches how `abstraction.py` (`COMPANION`-only) and
`attention_priority.py` (`COMPANION`-only) already fence self-generated cognition.

Therefore `X → Investigate X → Investigate Investigate X → …` **cannot start**. Extra
defense: the pursuit path calls `run_episode` directly (not the `Jarvis.think` facade),
so the writer's hook point is not even reached by echoes. In the companion-literal case
("investigate the open question: X" spoken by the human) the episode is genuinely
COMPANION-origin and a *distinct* item is correct, not a self-amplification, and the
exact-string guard still bounds duplicates of it.

---

## E. Deduplication

Current semantics (verified):

* `note_open_question` always builds a fresh `UnresolvedItem` — new `uuid4` id, new
  `opened_at` — and `save()` upserts **by id** (`json_unresolved_store.py:56`,
  `sqlite_unresolved_store.py:31`). There is no UNIQUE constraint on `question`, and
  the stores never examine it for equality.
* Identity across the model is defined only by **exact string equality**: that is what
  `resolve_open_question` matches on (`jarvis.py:2363`) and only the first match is
  resolved.
* `open_questions()` returns OPEN items oldest-first; history keeps resolved items.

So exact-string deduplication is **not** part of the model, and this gate does **not**
add it to the model (no constraint, no schema, no fuzzy/semantic matching). Instead the
**writer** performs the guard in clause 5 — checking the existing `open_questions()`
enumeration — which is expressible with current state and changes nothing.

Why the guard is required for correctness, demonstrated by the existing suite:
`test_full_lifecycle_across_restarts` notes `"why do the swallows return?"`, later calls
`day_two.think("why do the swallows return?")` (question-shaped, COMPANION, FULL,
ungrounded → would write a duplicate), then `resolve_open_question(...)`, and finally
asserts `open_questions() == ()` on Day 3. `resolve_open_question` resolves only
`matches[0]`; a writer that just appends would leave the think-created duplicate OPEN
forever and break that assertion. With the guard, the noted item is seen as already
open and the writer skips. Guard on **OPEN** items only: a resolved-then-re-asked
question correctly re-opens.

---

## F. Question representation

`UnresolvedItem.question` := `episode.evidence_request.question`, verbatim.

Verified valid: `EvidenceRequest.question` is the episode trigger
(`executive_controller.py:1135: question=episode.trigger`), and a `CognitiveEpisode`
requires a non-empty trigger (`cognitive_episode.py:93-96`), and `UnresolvedItem`
requires a non-empty question (`unresolved_item.py:49-51`). No transformation of the
request text is performed; `needed` ("observations bearing on whether: X") is **not**
re-prefixed or rewritten. The persisted value is the originating trigger, which is the
UnresolvedItem model's existing semantics: a freeform question string in the
companion's own words that curiosity may later investigate verbatim
(`curiosity.py:224`) and `resolve_open_question` matches on. The two models have
compatible meanings; nothing was invented.

---

## G. Provenance analysis

The write loses episode id, origin, evidence context, confidence, and source. This is
**acceptable**:

* The only consumers of `UnresolvedItem` are `curiosity.feel_curious` (reads
  `question` + `opened_at` to build an impulse trigger and rationale), the
  `resolve_open_question` path (matches `question`), and history listing. None needs
  the dropped fields.
* `opened_at` already acts as the item's own timestamp; the trigger text is the link
  back to the topic by the same identity the model uses everywhere.
* This is not a justification to add a schema. If a future feature (e.g. automatic
  attribution on resolution, which is **out of scope** and frozen) needs episode
  provenance, that will be a separate, blocker-proven schema change. It is not needed
  for writer v1's correctness, because nothing downstream requires the dropped fields
  to interpret the item safely.

---

## H. Epistemic isolation

Verified against ownership boundaries. `note_open_question` / store `.save()` construct
an `UnresolvedItem` and persist it; they touch nothing else (`jarvis.py:2323-2334`,
`json_unresolved_store.py:56`, `sqlite_unresolved_store.py:31`).

* **U1 — no belief mutation**: the writer never opens/executes an episode and never
  calls `think`; no `Belief` object is read or written.
* **U2 — no evidence mutation**: the `EvidenceRequest` is read only; nothing converts
  it into `Evidence`.
* **U3 — no confidence mutation**: confidence is derived solely from belief evidence
  (`Belief`), which the write does not touch; the store does not persist confidence for
  unresolved items.
* **U4 — no semantic-memory mutation**: semantic consolidation runs only from
  `EpisodeRecord` history at episode completion (`executive_controller.py:1210`,
  `abstraction.py:535` COMPANION-only); the unresolved write is not an episode and
  cannot feed it.
* **U5 — no Topic Identity mutation**: topic identity is derived from `EpisodeRecord`
  history (`attention_priority.py`/`topic_resolution`); an `UnresolvedItem` is not part
  of episode history and never reaches it.
* **U6 — no ReasoningSpan mutation**: the write happens wholly outside
  `_reasoning_span`; no span read/write occurs.

---

## I. Persistence

Compatible without modification. The writer's item is an ordinary
`UnresolvedItem(question=...)` produced through `note_open_question`, i.e. exactly the
shape already serialized by `serialise_item` (id, question, opened_at, status,
resolution, resolved_at — `json_unresolved_store.py:18`) and persisted by the JSON
store (`unresolved.json`, atomic flush) and the SQLite store (`unresolved_items`
table, commit-per-save). Both are wired in every persistent factory
(`persistence.py:86,146`). `test_unresolved_continuity.py` already proves restart
recovery for this exact shape on both backends. Required contract:
`episode → unresolved write → save → restart → open item still exists`. No schema
migration; none is needed (no provenance fields were added, section G).

---

## J. Downstream interaction

After a write: `open_questions()` → `feel_curious` fallback → impulse
`"Investigate the open question: X"` → `pursue` (CURIOSITY-origin episode). Verified
the existing consumers can receive the new item safely:

* **No new immediate loop**: the pursued episode is CURIOSITY-origin and is therefore
  excluded by clause 2; and `pursue` does not flow through `Jarvis.think`, so the
  writer's hook is never reached by the investigation it spawns.
* **No unsafe reinterpretation**: the item only becomes a curiosity *candidate*
  (last in the cascade, unchanged), the impulse is a recommendation, and the only
  closing path is the existing, user-supplied `resolve_open_question` (frozen
  semantics) — the item cannot auto-resolve itself.
* **Wake/attention unchanged**: `derive_attention_priorities` never reads the
  unresolved store (its "unresolved" signal comes from episode conclusions), so the
  writer does not move saliency.
* **Boundedness**: dedup (clause 5) + a fixed predicate keep the store linear in
  distinct qualifying questions; no scheduler was introduced; pursuit remains cold;
  ReasoningSpan untouched.

Finding: the writer covers the `Jarvis.think` completion boundary. `pursue` (echoes)
and `perceive`/`perceive_all` (no production callers today) bypass that facade; echoes
are excluded by origin regardless, and perceive flows are documented as not covered in
v1.

---

## K. Deterministic implementation tests

Minimum set, all offline/deterministic (JSON + SQLite where persistence is asserted):

* **Test A — valid occurrence**: `jarvis = Jarvis.persistent(tmp)`; `jarvis.think("does
  my companion prefer simplicity?")` (no evidence) → exactly one item,
  `question == "does my companion prefer simplicity?"`; repeat the same `think` → still
  exactly one (guard).
* **Test B — non-qualifying request**: (1) `consider` of an undecided tie produces an
  `EvidenceRequest` on the `Deliberation` but **no** item; (2) a CURIOSITY-origin
  pursuit (`pursue(feel_curious())`) after `note_open_question` produces **no** new
  item; (3) a statement/remember with grounding evidence produces **no** item; (4) an
  ungrounded statement-shaped COMPANION FULL episode (no `?`, no interrogative cue)
  produces **no** item; (5) an ungrounded BRIEF completion (CHEAP/conserve path)
  produces **no** item.
* **Test C — investigation echo**: `note_open_question("X")` →
  `pursue(feel_curious())` → `open_questions()` is unchanged (no "Investigate…" item
  ever appears; no recursion).
* **Test D — persistence**: writer item survives restart on JSON and SQLite backends.
* **Test E — epistemic isolation**: snapshot beliefs / their evidence / confidence /
  semantic memories / topic identities / reasoning span before the write and assert
  unchanged after (maps to U1–U6).
* **Test F — existing behavior**: the full `test_unresolved_continuity.py` suite and
  the unresolved-lifecycle assertions pass byte-for-byte with the writer installed
  (the exact-string guard is what keeps `test_full_lifecycle_across_restarts` green).

Additionally at implementation time: re-run the attention/curiosity and conversation
suites, since tests asserting "no curiosity impulse / empty open questions" after
question-shaped ungrounded COMPANION thinks may legitimately observe new items
(section M).

---

## L. Minimal implementation boundary

Exact surface (no new manager, no new store, no new schema, no new event type):

* `src/jarvis/executive/executive_controller.py` — expose the existing question-shape
  test as a public alias (`is_question_shape` or similar) reusing `_QUESTION_CUES` and
  the `?`-suffix line already in `_looks_like_self_question`; no behavioral change.
* `src/jarvis/jarvis.py` — in `Jarvis.think`, after `_think_fn` returns (the existing
  episode-completion boundary, next to the reasoning-span recording at lines 2071-2076),
  apply predicate P (C) and call the existing `self.note_open_question(...)` when it
  holds. This is the owner: the facade already owns the unresolved store and
  post-processes every completed think episode.

Untouched: `resolve_open_question`, `note_open_question`'s model/behavior,
`_engage_reply`, `curiosity.py`, `attention_priority.py`, `reasoning_span.py`, all
stores, all value objects, all schemas. The writer is additive and inert when any
clause fails.

---

## M. Risks

* **False positives** — question-shaped COMPANION FULL episodes that are rhetorical or
  transient would persist one resolvable item each. Mitigated by FULL + question-shape
  + dedup; residual cases (e.g. rhetorical questions) are bounded and closable.
* **False negatives** — deliberately accepted: research subjects without question-shape
  (`learn_from_external`, "investigate ingest"), BRIEF completions, deliberation ties,
  and `perceive` flows (no production callers). Revisitable only in a later gate; not
  a v1 defect.
* **Duplicate accumulation** — fully guarded by clause 5 (exact-string over OPEN
  items); resolved-then-re-asked correctly re-opens. Without the guard, the existing
  lifecycle test breaks (section E) — the guard is a correctness requirement, not a
  preference.
* **Recursive self-generation** — structurally impossible: the investigation echo is
  CURIOSITY-origin and not CLAUSE 2-eligible, and pursuit bypasses the facade hook.
* **Provenance loss** — acceptable under current consumers (G); becomes a blocker only
  for out-of-scope features that must attribute counts/episodes/facts, which will
  require their own schema gate.
* **Downstream reinterpretation** — a new item becomes a curiosity *candidate* via the
  existing fallback; pursuit of it is bounded (origin-excluded), and it cannot
  auto-resolve. `feel_curious` may now sometimes return an impulse where a suite
  previously asserted None after ungrounded question-shaped COMPANION thinks; verify
  at implementation time (Test F re-run).

---

## N. Final recommendation

**ARCHITECTURE GATE — EPISODE EVIDENCE-REQUEST WRITER v1**
**READY FOR IMPLEMENTATION** (with the section C predicate and the exact-string write
guard, as bounded by sections K–L).

No blocker exists: every predicate dimension already exists in the codebase, the write
is epistemically inert (U1–U6), persistence and restart need no change, the unwritten
recursion cannot start, and duplicate accumulation is prevented by a guard the existing
lifecycle tests actually require. Resolution, conversation, attention, curiosity and
ReasoningSpan remain frozen and untouched.

---

## O. Implementation status

Implemented 2026-09-20, exactly per the section C predicate and the section K–L
boundary; nothing outside it changed.

* `src/jarvis/executive/executive_controller.py` — `is_question_shape(text)` public
  alias reusing `_QUESTION_CUES` and the `?`-suffix line from `_looks_like_self_question`;
  `_looks_like_self_question` delegates to it, behavior unchanged.
* `src/jarvis/jarvis.py` — `Jarvis.think` now calls `self._note_evidence_request(episode)`
  after the reasoning-span recording (the episode-completion boundary, lines ~2076-2111);
  the private helper applies predicate P (evidence_request non-None, COMPANION origin,
  FULL attention, `is_question_shape(request.question)`, exact-string guard over
  `open_questions()`) and then calls the existing `self.note_open_question(...)`.
* `tests/test_episode_evidence_request_writer.py` — Tests A–E (occurrence + exact one
  via dedup, exclusions {undecided deliberation, CURIOSITY echo, grounded statement,
  grounded question-shaped, CHEAP/BRIEF}, no recursion from investigating an item,
  JSON + SQLite restart persistence, epistemic isolation U1–U6).
* Verification: full suite 2213 passed / 3 skipped (zero drift in the attention,
  curiosity, conversation, deliberation and existing unresolved-lifecycle suites —
  Test F); `python -m ruff check src tests` clean; `python -m pyright` 0 errors
  (strict). No commit made.