# ARCHITECTURE GATE — UNSETTLED-COGNITION WIRING v1

Status: **FAIL — DO NOT IMPLEMENT** (as one composite seam)

Date: 2026-09-20
HEAD checked: `331eb48` (Increment 169, "a changed mind is resolved, not stacked")
Dirty files at gate start: `docs/claude/FORENSIC_CLOSURE_EPISODE_PATH_REASONINGSPAN_V1.md` only (pre-existing, untouched).

Scope of this gate: verify the discovery claims against the repository, trace both
`EvidenceRequest` and `UnresolvedItem` completely, and decide whether the proposed
writer + conversational + resolver wiring can proceed. Nothing was modified except
this report. No commit.

---

## A. Verdict

**FAIL — DO NOT IMPLEMENT** (the composite seam as proposed).

The proposal bundles three distinct wiring decisions:

1. **Episode writer**: `completed episode + EvidenceRequest → note_open_question(...)`
2. **Conversational writer**: `_engage_reply → note_open_question(...)`
3. **Automatic resolver**: `later grounded episode → resolve_open_question → USER_STATEMENT evidence`

Half 3 is architecturally unsafe as specified (provenance corruption: a Jarvis-derived
conclusion would be stamped `EvidenceSource.USER_STATEMENT`). Half 2 is unsafe
(no predicate in the repository distinguishes the ≥5 situations `_engage_reply`
collapses, and conversational questions never produce an `EvidenceRequest` at all).
Half 1 is mechanically inert but **under-specified**: the occurrence predicate, the
question-text mapping, and the dedup decision are all absent. The repository's own
discovery report is otherwise accurate (verified below).

The smallest correct seam — if pursued — is a **writer-only** follow-up gate
restricted to the episode path with the three missing decisions made explicit.

---

## B. EvidenceRequest lifecycle

### Creation

Two creation sites, both in `src/jarvis/executive/executive_controller.py`:

* **Conclusion episodes** — `_maybe_request_evidence()` (line 1129), called once in
  `run()` at line 643, after `_decide(...)` and before `episode.complete(...)`, for
  every episode regardless of attention depth. Condition: the working belief's final
  derived confidence `< knobs.grounded_confidence` (default 0.5). This fires for both
  zero-confidence ("insufficient evidence") and tentative conclusions. A grounded
  episode gets `None`.
* **Deliberation episodes** — `deliberate()` builds an `EvidenceRequest` inline
  (line 718) **only when** `hypothesis_set.leading()` is `None` (undecided tie / no
  evidence). When a leader exists, `evidence_request=None` (line 740) — even if the
  leader's confidence is below grounded.

Fields (`src/jarvis/domain/value_objects/evidence_request.py`): `question` (the
episode trigger), `statement` (the working/concluding statement), `confidence`
(current, low), `needed` (the kind of observation that would raise it).

**Can an episode be ungrounded without an EvidenceRequest?** Yes, in two cases:
a deliberation that picks a low-confidence leader, and any episode that leaves the
lifecycle through `fail()` (which never runs `_maybe_request_evidence`).

### Lifetime

* Stored in `CognitiveEpisode._evidence_request` (`cognitive_episode.py:84`), a plain
  in-memory field.
* Survives only as long as the returned `CognitiveEpisode` / `Deliberation` Python
  object is referenced. `think()` returns the episode to the caller; once dropped the
  request is gone.
* Deliberation copies it into the `Deliberation` value object (`deliberation.py:28`),
  which is returned to the caller. It is never attached to the episode itself.
* **Not emitted as an event.** `attach_evidence_request()` records no
  `CognitiveEvent` (contrast with `observe()`, `record_reflection()`, etc.), and
  there is no `EvidenceRequested` event class. `EpisodeCompleted` does not carry it.
* **Not serialized.** `EpisodeRecord` (`value_objects/episode_record.py`) has no field
  for it; `_remember()` (`executive_controller.py:1166`) drops it. JSON/SQLite episode
  stores never see it. Grep across `src/` confirms no serialization and no other
  carrier.

### Meaning

For a conclusion episode, an `EvidenceRequest` means:

> *This episode completed, but the working belief it reasoned toward finished below
> the grounding threshold. Here is the theory (statement), the current derived
> confidence, and the kind of observation that would ground it.*

It is a **post-hoc epistemic-gap label on an episode's conclusion**. It is **not**
"an open question worth pursuing":

* No question is required to produce one: statements stored with thin evidence,
  BRIEF/cheap probes, and self-triggered curiosity pursuits all attach requests when
  ungrounded.
* It carries no signal about whether anyone (the companion, the reasoner) expressed
  interest in resolving it.
* Therefore the equivalence "Jarvis does not know X" ⇔ "X is an open question worth
  pursuing" is **not established anywhere in the codebase**. Adopting it — even for
  the writer half — is a **new semantic decision**, not a reading of existing code.

The deliberation variant is closer to "worth pursuing" (it names what would break a
tie), but it is only produced for undecided ties, not for every unsettled weighing.

### Trigger provenance

The `EvidenceRequest` retains: the trigger (`question`), the working `statement`,
current `confidence`, and `needed`. It does **not** retain:

* originating episode ID (on the episode, not the request);
* topic identity (`target_topic_id` is on the episode; only topic-aware callers set it);
* evidence already considered (the belief's evidence list is on the episode's working
  belief, not referenced by the request);
* source/origin (`TriggerOrigin` is on the episode);
* **any timestamp** (no field at all).

Provenance is therefore partial. If the writer hooks the *completed episode* at the
moment `_maybe_request_evidence` fires, episode-level provenance (id, origin,
attention, goal, topic) is available in memory. The value object alone cannot provide
it, and nothing persists it.

---

## C. UnresolvedItem lifecycle

* **Creation** — `Jarvis.note_open_question(question)` (`jarvis.py:2323`). Always
  constructs a fresh `UnresolvedItem` (new uuid4 id, `opened_at=now(UTC)`,
  `status=OPEN`). Empty/whitespace questions raise.
* **Persistence** — `JsonUnresolvedStore` (`unresolved.json`, atomic whole-file
  writes) or `SqliteUnresolvedStore` (`unresolved_items(id, payload)` in `jarvis.db`,
  commit-per-save), or an in-memory dict when no store is wired
  (`jarvis.py:588`, session-only). Both persistent factories wire a store
  (`persistence.py:86`, `:146`; `server.py:219`), so production is durable.
* **Retrieval** — `open_questions()` returns OPEN items oldest-first;
  `unresolved_history()` returns all items oldest-first.
* **Attention** — `feel_curious()` reads `open_questions()` as the **last fallback**
  in a static cascade (`curiosity.py:217-229`); see section H.
* **Investigation** — `pursue(impulse)`/`jarvis.pursue` turns the fallback impulse into
  a full `CURIOSITY`-origin episode (see section H).
* **Resolution** — `resolve_open_question(question, resolution)`
  (`jarvis.py:2354`): exact-string match against OPEN items (raises `KeyError` if
  none), marks a copy resolved, saves, then runs
  `think(question, evidence=[Evidence(resolution, USER_STATEMENT, 1.0, supports=True)])`.
* **Restart** — verified by `tests/test_unresolved_continuity.py` on both backends:
  open items recover, resolved history persists, and the resolution lives on as belief
  evidence.
* **Production callers** — `note_open_question` and `resolve_open_question` have **no
  production callers** (only tests). The only production consumer of the store is the
  `feel_curious` fallback read. The discovery claim "production writers are currently
  absent" is confirmed.

### What `UnresolvedItem.question` semantically means

Per the value object's docstring, it is an open question not yet settled — an
epistemic uncertainty / investigation target in the caller's own words. The model does
**not** distinguish a user question from an epistemic uncertainty from a missing
observation from a task from an investigation target. There is no kind field, no
belief/topic link, and no evidence link. Identity is defined only by **exact string
equality** (that is what `resolve_open_question` matches on). These are not
interchangeable categories, and the current model neither forces one nor records which
it is.

---

## D. Proposed writer seam

`EvidenceRequest → UnresolvedItem`

**Mechanically safe, but not sufficiently specified.**

* Invariant U1 (no false knowledge): holds — writing a question string does not
  create or strengthen a belief.
* Invariant U2 (request stays epistemic): holds — an `UnresolvedItem` is a question
  string, not a conclusion; nothing in the writer converts it into one.
* Invariant U3 (no automatic confidence mutation): holds at the writer. (Caveat: the
  **resolver** half does mutate — see section F — and repeated ungrounded episodes
  already feed knobs adaptation / meta-observation through episode history, but that is
  independent of the writer.)
* Invariant U4 (provenance): the unresolved model has **no field** for originating
  episode, topic, or evidence. Provenance is only needed for the resolver; for the
  writer + current `feel_curious` consumer it is not required (the impulse only needs
  the question text). If provenance later becomes a requirement it is a **schema
  blocker** under this gate's own rules.
* Invariant U5 (deduplication): the discovery assumes "exact-question deduplication";
  the existing store **does not deduplicate**. Every `note_open_question` call creates
  a new item with a new id, and neither store has a UNIQUE constraint on `question`.
  Exact-equality identity is what `resolve` uses, but uniqueness is not enforced at
  write time. Whether the writer dedupes by exact string (matching the resolver's
  identity) or not (matching current `note` behavior) is an **open design decision**,
  not something the repository already defines. The three example phrasings
  ("Is supplier X failing?" / "Whether supplier X is failing" / "Need evidence about
  supplier X failure") are three distinct items under current identity semantics.

**The missing decision that blocks the writer**: a predicate establishing *when* an
episode needs to become an open question. An `EvidenceRequest` is a low-confidence
label on any conclusion; not all such conclusions are worth pursuing. The proposal
must decide, explicitly:
(a) only questin-shaped triggers (e.g. ends in `?` or opens with an interrogative)
    or any ungrounded conclusion;
(b) policy for `CURIOSITY`-origin "Investigate the open question: X" echoes
    (these land ungrounded and would re-enter the store);
(c) the exact-string dedup decision.
None of these exists today; the gate cannot invent them.

---

## E. Conversational writer

`_engage_reply → UnresolvedItem` — **NOT SAFE, missing predicate.**

`_engage_reply` (`interface/_conversation.py:593-605`) is reached from
`_knowledge_reply` (lines 539, 543) exactly when `jarvis.reason(...)` returned nothing
AND (for questions) no long-term memory answer and no document surfaced, or (for
non-questions) no document surfaced. It is a **pure conversational fallback**; the
function does not even receive `jarvis`. It collapses at least these situations:

1. genuine epistemic uncertainty;
2. insufficient user context ("give me a bit more context");
3. unsupported request;
4. inability to retrieve information;
5. conversational acknowledgment after a real statement **was already stored**
   (statements ≥3 words were persisted by `_remember_statement` before
   `_knowledge_reply` runs — the engage reply is social, not epistemic);
6. a genuinely open unresolved question.

The only discrimination in the function is punctuation (line 595). The repository
provides **no predicate** to tell these apart at that call site.

Critical additional fact: **conversational questions never produce an
`EvidenceRequest`.** The conversational surface calls `think()` only on the statement /
explicit-remember paths (which carry weight-1.0 `USER_STATEMENT` evidence and ground),
and `_knowledge_reply` itself uses only `recall()` + `reason()`.
`_engage_reply` therefore has **no epistemic artifact behind it** — writing every
fallback turn into persistent unresolved state would fabricate open questions from
phrasing failures and small talk. The discovery's observation ("unanswered
conversational questions can also disappear through `_engage_reply`") is factually
correct, but the writer half over-reaches: the real gap is that this path never reaches
any epistemic state at all, and closing it requires a distinguishing predicate the
repository does not have.

---

## F. Resolver seam

Automatic resolution (grounded episode/result → `resolve_open_question` →
`USER_STATEMENT` evidence → grounded belief) — **NOT SAFE as specified.**

* **What makes a valid resolution today**: the caller supplies a free-text `resolution`
  string and it must exactly match an OPEN item's question. There is no topic match,
  no statement match, no provenance check. The method is "the companion handed me the
  answer"; it has no other validity rule.
* **Why `USER_STATEMENT` is problematic**: every call stamps the resolution as
  `EvidenceSource.USER_STATEMENT`, weight 1.0, supports=True, context="answer to an
  open question". In the codebase, `USER_STATEMENT` provenance is used **exclusively
  for the companion speaking** (statement storage, confirmation, remember intent,
  `curiosity.resolve`, `Jarvis.resolve`). A Jarvis-derived conclusion (whose real
  provenance would be `INFERENCE` or `SYSTEM_OBSERVATION`) fed through this method
  would be recorded, weighed, recalled, and consolidated **as if the companion said
  it**. That is provenance corruption, and the method has no way to express the true
  source. The discovery's "a Jarvis-generated inference should not silently become a
  user statement" concern is therefore confirmed as a hard blocker, not a nuance.
* **Can a grounded inference resolve an item?** Only if the architecture explicitly
  supports that semantics. It does not. This would be a new semantic decision; the
  method is human-answer-in, and producing its first automatic production caller is a
  design change, not a wiring fix.
* **Can the same episode create and resolve?** The writer fires on ungrounded endings
  (`confidence < grounded`); the resolver produces a weight-1.0 grounded belief. Within
  one episode the natural order is writer-before-resolver (the request is attached at
  line 643, before `complete`/`_remember`). There is no loop today because neither
  wire exists; the composite seam would need to define the ordering explicitly.
* **Self-investigation recursion (E)**: pursuing the fallback impulse runs
  `CognitiveEpisode(trigger="Investigate the open question: X", origin=CURIOSITY)`.
  That episode is ungrounded and carries its own transient `EvidenceRequest`. Under a
  **naive writer this creates a new unresolved item whose text is an escalation of the
  question** ("Investigate the open question: X"). Today nothing creates it, so
  "Investigate Investigate X" does not arise; with the naive writer it emerges as a
  deferred duplicate (the fallback picks the *oldest* open item, so the original X is
  re-proposed until resolved; the escaped items accumulate in the store meanwhile).
  `feel_curious` fallback ordering does not by itself contain the accumulation; only the
  presence/absence of the writer does.

---

## G. Persistence and restart

Confirmed for the unresolved side, from code and `tests/test_unresolved_continuity.py`:

* serialization: JSON payload (id, question, opened_at ISO, status, resolution,
  resolved_at) in `unresolved.json` or `unresolved_items(id, payload)` in `jarvis.db`;
  malformed entries are skipped on load (recovery);
* IDs: uuid4, store-keyed; `save()` is an upsert by id;
* timestamps: `opened_at` at note time, `resolved_at` at resolution; ordering oldest-
  first by `opened_at`;
* duplicates: **not** prevented (no uniqueness on question);
* resolved state: preserved as history via `all_items()`;
* transaction ordering: JSON = atomic whole-file flush per save; SQLite = commit per
  save; in `resolve_open_question` the save precedes the grounding `think()`;
* restart: open questions survive, resolved history survives, resolutions re-ground as
  belief evidence.

No schema change is needed for the note writer itself (a question string fits).
**If** the item must later retain the originating episode/topic/evidence, the current
model cannot express it — that would be a blocker-proven schema change, not a wiring.

---

## H. Attention / curiosity interaction

Actual downstream path, verified:

```
note_open_question("X")
  → store (unresolved.json | unresolved_items)        [durable, oldest-first]
  → feel_curious(): LAST fallback of the cascade        [curiosity.py:217]
      impulse.trigger = "Investigate the open question: X"
      (no target_topic_id, no representative_trigger, no goal, no reflect_on)
  → jarvis.pursue(impulse) (only user-driven via the "wonder" command today;
      there is NO proactive scheduler in production — reflect_cycle does not pursue)
  → CognitiveEpisode(trigger="Investigate the open question: X", origin=CURIOSITY)
  → executive.run(): full lifecycle, ungrounded, with its own transient EvidenceRequest
  → EpisodeRecord + belief WORKING:"Investigate the open question: X"
  → resolve_open_question("X", answer) → USER_STATEMENT evidence → grounded belief
```

Findings:

* Unresolved items **do not influence the ranked attention surface**. `wake()` /
  `derive_attention_priorities()` (`domain/services/attention_priority.py`) computes
  its "unresolved" term from episode conclusions below 0.5 **within the window**
  (lines 118-120); it never reads the unresolved store. The "unresolved" signal in the
  two systems is entirely separate.
* They appear only as **fallback candidates** in `feel_curious`, after every
  evidence-derived stage wins first.
* They **can trigger pursuit**, but pursuit is only reachable through the command-center
  "wonder" command (`interface/_cognition.py:_wonder`), i.e. explicitly or by an
  operator; nothing drives it automatically (a proactive scheduler is frozen-out).
* Pursuit **does generate a full episode** (origin CURIOSITY), recorded and traded
  through recall.
* **ReasoningSpan**: pursued episodes receive **no span threads**. `curiosity.pursue`
  → `run_episode(jarvis, episode)` passes no `span` (default `()`), and the pursue path
  does not go through `jarvis.think`, so neither `_reasoning_span.threads()` nor
  `_reasoning_span.record()` is touched. This is the known "cold pursue" limitation and
  it matters for the quality of reasoner continuations during investigation; the seam
  must not and does not change it.
* The resulting investigated episode, if ungrounded, would feed a naive writer's own
  store (see section F-E) — the single most concrete way the composite self-amplifies.

---

## I. Semantic boundaries

Current state confirms the desired separation:

* `UnresolvedItem` never becomes a belief, evidence, semantic memory, or confidence
  update. Semantic consolidation consumes **COMPANION-origin episodes only**
  (`abstraction.py:535`), and valence-less `CURIOSITY` episodes contribute neutral
  evidence skipped for confidence/stability. A curiosity pursuit cannot manufacture a
  pattern.
* The **only** cross-layer path is the resolver: `resolve_open_question(...)` grounds a
  `COMPANION`-origin episode with weight-1.0 evidence, which then flows into knowledge-
  graph extraction, semantic consolidation, knobs adaptation, and meta-observation.
  That is legitimate when the answer is genuinely the companion's; it becomes a leak
  the moment the answer is Jarvis's own (section F).
* ReasoningSpan is never written by the unresolved machinery.

---

## J. Deterministic validation contract

Current tests pinning today's behavior (they would become the regression net):

* `tests/test_jarvis.py::TestEvidenceRequest` — request present on ungrounded /
  tentative episodes, absent when grounded (in-memory, per episode).
* `tests/test_learning_continuity.py` — `baseline.evidence_request is None` /
  `repeated.evidence_request is not None` across a restart; note this asserts a
  **re-derived** request from a fresh `think()`, proving the request is not itself
  persisted.
* `tests/test_deliberation.py::TestConsider` — tie/no-evidence deliberations carry a
  request; a leading explanation carries none.
* `tests/test_unresolved_continuity.py` — unresolved lifecycle, restart recovery, exact
  user-supplied resolution, history preservation on both backends; also pins that
  `resolve_open_question` on an unknown question raises `KeyError`.

If a writer-only seam ever proceeds, required probes (all offline/deterministic):

* **Probe 1 (ungrounded episode)**: `jarvis.think("does my companion prefer
  simplicity?")` → episode `evidence_request` set; `open_questions()` unchanged today.
  Post-writer: exactly one item, and a re-run of the same condition leaves exactly one
  (dedup decision) — both halves of this assertion must be written explicitly.
* **Probe 2 (persistence)**: `note_open_question` → restart → `open_questions()`
  returns it; empty store → empty store on restart. (Exists; extend to the writer.)
* **Probe 3 (dedup)**: repeat the same ungrounded condition N times; assert the
  store's item count (must pick the dedup decision first — current model yields N).
* **Probe 4 (conversation)**: a chat question with no recall/reason/document answer →
  `_engage_reply`; assert the store is **unchanged** (the conversational writer is out
  of scope until a distinguishing predicate exists).
* **Probe 5 (resolution)**: only a direct, companion-provided `resolution` matches
  today; assert (a) a Jarvis-derived `INFERENCE`/`SYSTEM_OBSERVATION` result arriving
  via `resolve_open_question` is **not** possible without stamping `USER_STATEMENT` —
  i.e. the blocker is observable; (b) no naive auto-resolver wiring exists.
* **Probe 6 (self-recursion)**: `note_open_question("X")` → `pursue(feel_curious())`
  → assert no item whose question starts with "Investigate the open question" is EVER
  created (guards the recursion/accumulation risk even without a writer).

---

## K. Minimal implementation boundary (if the writer half proceeds)

Do **not** create an "UnresolvedManager" or equivalent abstraction. Ownership:

* The **executive already owns the EvidenceRequest transition** (`executive_controller.py`)
  — `_maybe_request_evidence` / `deliberate` are where a writer would fire.
* The **`Jarvis` facade owns the unresolved store** (`jarvis.py` `note_open_question`/
  `open_questions`/`resolve_open_question`), and `executive_controller` does not
  currently hold it — wiring would have to inject the `UnresolvedRepository` into the
  executive the same way `SemanticMemoryRepository`/`KnowledgeGraphRepository` already
  are (constructor + no-op when absent), or perform the write at `Jarvis.think` level
  after receiving the completed episode.

Concrete files that would change (no code in this gate): `executive_controller.py`
(or `jarvis.py` facade — owner is whoever holds the store), the black-box contract
tests, and wiring in `persistence.py`/`server.py` only if the store is injected
through the composition root. `domain/value_objects/*` and the schemas stay untouched
unless the provenance decision forces one (then it is a blocker, per §8).

---

## L. Risks

* **False unresolved items** — every ungrounded conclusion, curiosity echo, cheap/BRIEF
  probe, and short conversational fallback becomes a durable open question. Highest
  concrete case: `think("a novel question")`-style probes and every
  "Investigate the open question: X" pursuit echo.
* **False resolution** — low-confidence leaders and partial answers auto-closed as
  "the answer"; resident in the `resolve_open_question` design if any automatic caller
  appears.
* **Provenance corruption** — Jarvis's own conclusions recorded as
  `USER_STATEMENT`, then weighed, recalled, consolidated, and taught as companion
  speech. This is the single most damaging failure mode and it is structural in the
  resolver's API.
* **Recursive investigation** — naive writer turns each pursuit echo into a new item
  ("Investigate the open question: …"), deferring but not preventing
  "Investigate Investigate X"; ordering defers, does not bound.
* **Accumulation** — no retention bound on `unresolved_items`; nothing expires
  unresolved items, so a working Jarvis with the writer grows the store forever
  (compounding by design with the oldest-first fallback re-proposing the same item).
* **Cross-session contamination** — durable items persist across restarts by design;
  a writer that is too generous writes noisy open questions that shadow real ones when
  the fallback selects the oldest.

---

## M. Frozen invariants

Untouched by any follow-up: Topic Identity v3; Topic-Anchored Belief Addressing v1;
Polarity Semantics v1; Episode-Path ReasoningSpan v1 (no change to ReasoningSpan or its
cold-pursue behavior); no semantic embeddings; no fuzzy unresolved matching; no new
database; no new schema unless proven necessary (currently only provenance would force
one → blocker); belief confidence stays derived (no imperative confidence setter);
EvidenceRequest never becomes evidence; unresolved state never becomes belief; LLM
output never authoritative (never auto-stamped USER_STATEMENT); no proactive scheduler;
curiosity and attention algorithms not redesigned.

---

## N. Final recommendation

**FAIL — DO NOT IMPLEMENT** the composite seam as proposed.

Exact blockers:

1. The **resolver half is architecturally unsafe**: `resolve_open_question` stamps
   `USER_STATEMENT` on whatever string it is given; there is no mechanism to carry the
   true provenance of a Jarvis-derived answer, so automatic resolution corrupts
   provenance by construction.
2. The **conversational writer has no predicate**: `_engage_reply` conflates ≥5
   distinct situations and is reached with no epistemic artifact at all (conversational
   questions never produce an `EvidenceRequest`).
3. The **episode writer lacks a semantic decision**: nothing in the repository
   establishes that an `EvidenceRequest` is an open question *worth pursuing*, the
   trigger→question mapping is undefined for statement-shaped triggers, and exact-
   question deduplication does not exist in the current model.

Smallest follow-up gate required:

> **ARCHITECTURE GATE — UNSETTLED-COGNITION WRITER v2** — episode-path only. Must
> resolve, before implementation: (a) the occurrence predicate (which ungrounded
> conclusions are open questions, including whether to require question-shaped
> triggers and how to treat CURIOSITY-origin "Investigate…" echoes); (b) the exact-
> string dedup decision; (c) explicit exclusion of the `_engage_reply` writer and any
> automatic resolver until each has its own predicate; and (d) confirmation that no
> schema change is implied. The resolver's USER_STATEMENT provenance problem must be
> addressed in a separate gate of its own; it must not ride along silently.