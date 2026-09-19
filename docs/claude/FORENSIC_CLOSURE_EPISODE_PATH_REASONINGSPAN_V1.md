# Forensic Closure — Episode-Path ReasoningSpan v1

**Date:** 2026-09-19
**Scope:** Verification of the *Episode-Path ReasoningSpan v1* seam (`b6a2159`, Increment 166) before
freeze: explicit span propagation down `Jarvis.think`, completion-only recording, failure safety,
instance isolation, and the audit gates.
**Method:** committed-diff inspection, code trace of the full propagation chain, focused and full
regression suites, lint, strict types.
**Verdict:** **FAIL — DO NOT FREEZE** (the E1–E9 functional contract is verified; the audit **type gate
is broken** — pyright strict reports 5 errors at HEAD, all in the new test code — and one of the 7 new
tests is vacuous in every reachable configuration. See Findings 1–3.)

> Hard-stop discipline honored: this audit changed **no code and no tests**. The only file created is
> this closure record. Nothing is committed.

---

## 1. Verified propagation chain (E1–E9)

| Condition | Status | Evidence |
|---|---|---|
| **E1** Explicit propagation `Jarvis.think → cognitive.think → run_episode → executive.run → _reason_into → reasoner.infer(..., span=...)` | **PASS** | `jarvis.py:2068-2072` (snapshot + forward); `cognitive.py:139-163` (`think`/`run_episode` keyword-only `span`); `executive_controller.py:558,610,890-911` (`run`→`_reason_into`→`infer(episode.trigger, recalled, conversation, span)`); `reasoner.py:34-44` protocol carries `span` |
| **E2** Active snapshot in `think(span=None)`; explicit `span=()` stays empty | **PASS** | `jarvis.py:2068` uses `span is not None` (not truthiness); test `test_explicit_empty_span_does_not_substitute_live_span` asserts no `<reasoning_span>` in the prompt for `span=()` |
| **E3** Completion-only mutation | **PASS** | `jarvis.py:2070-2072`: `record` runs only when `episode.inference is not None`. `_reason_into` returns without `episode.infer` when the provider yields nothing (`executive_controller.py:912-914`). Only three `_reasoning_span.record` call sites exist in `src` (`jarvis.py:695,732,2072`), each gated on a completed answer |
| **E4** Recorded content = `trigger + inference.answer`, never span contents | **PASS** | `jarvis.py:2072`; thread rendering (`llm_reasoner.py:_render_span`) reads span only for the prompt; recording is independent of span contents |
| **E5** Provider failure does not mutate the span | **PASS** | `LlmReasoner.infer` catches and returns `None` (`llm_reasoner.py:62-63`) → no `episode.infer` → no record; test `test_failure_does_not_advance_the_span` |
| **E6** Instance isolation | **PASS** | `_reasoning_span` constructed per instance (`jarvis.py:618`); test `test_instance_isolation` |
| **E7** Context-only boundary (≠evidence/belief/semantic-memory/confidence/persistence) | **PASS in code / test ineffective** | Span never written to beliefs (`_reason_into` observes a fresh `Evidence` from `inference.answer`, independent of span), never to semantic memory (`_remember`/`consolidate_semantic_memories` take no span input), never persisted (no serializer references `ReasoningSpan`; snapshot exposure in `interface/_state.py:118,526` is read-only). **However** its dedicated test is vacuous — see Finding 2 |
| **E8** Conversational `reason()` / `reason_stream()` semantics intact | **PASS** | `reason`/`reason_stream` (`jarvis.py:673-732`) are byte-identical to the parent commit `13231a8`; the truthy-fallback `span if span else …` and completion-gated recording predate this change |
| **E9** Frozen seams untouched | **PASS** | The commit touches exactly 4 files; production diffs are additive keyword-only parameters with defaults. Topic Identity v3, Topic-Anchored Addressing v1, Polarity, Evidence, Confidence, Semantic Memory, Persistence, Session and Reflection architectures are not semantically altered (verified by diff, Section 2) |

## 2. Actual diff verification (Section 3 of the report contract)

`b6a2159` — one commit, working tree clean at HEAD (`git status: nothing to commit`).

| File | Change |
|---|---|
| `src/jarvis/cognitive.py` | `think`/`run_episode` gain keyword-only `span` and forward it |
| `src/jarvis/executive/executive_controller.py` | `run` gains `span`; `_reason_into` gains `span` and passes it to `reasoner.infer` |
| `src/jarvis/jarvis.py` | `think` snapshots `self._reasoning_span.threads()` when `span is None`, forwards, and records `(trigger, inference.answer)` on completed inference only |
| `tests/test_reasoning_span.py` | `TestEpisodePathReasoningSpan` + 7 tests; trailing-newline fix |

- Exact test changes: 7 new tests — `test_two_episode_continuity`, `test_failure_does_not_advance_the_span`,
  `test_span_content_is_not_evidence`, `test_no_semantic_memory_leakage`, `test_instance_isolation`,
  `test_same_trigger_revisit_preserves_existing_thread`,
  `test_explicit_empty_span_does_not_substitute_live_span`.
- Unexpected modified files: none. Unrelated cleanup: none (production diffs are purely additive plumbing).
- Frozen-seam files touched: none.
- **Report inaccuracies found:** (a) the report states "No commit was made" — the work **is** committed
  as `b6a2159`; (b) the report states "Pyright strict: 0 errors" — **false**, 5 errors at HEAD (Finding 1).
  The full-suite claim (2176 passed, 3 skipped) is accurate and reproduced.

## 3. Findings

### Finding 1 — CONFIRMED: pyright strict gate is broken at HEAD (5 errors, all in new test code)

`python -m pyright` (strict, `include = ["src", "tests"]`, pyright 1.1.414):

```
tests/test_reasoning_span.py:25:7   reportRedeclaration   "_RecordingModel" obscured (declared twice)
tests/test_reasoning_span.py:258:47 reportOptionalMemberAccess  "evidence" not known on None
tests/test_reasoning_span.py:266:47 reportOptionalMemberAccess  "evidence" not known on None
tests/test_reasoning_span.py:281:52 reportUnknownMemberType      Type of "content" is unknown
tests/test_reasoning_span.py:281:56 reportAttributeAccessIssue   no attribute "content" on SemanticMemory
5 errors, 0 warnings, 0 informations
```

The parent commit `13231a8` run in an isolated worktree with the **same** pyright build reports **0
errors**. The 5 errors are therefore introduced by `b6a2159`. Every previous closure/forensic record in
this repo treats "pyright strict 0 (tests included)" as a freeze gate; the report's own claim of 0
errors is disproved by the repository itself.

### Finding 2 — CONFIRMED: `test_no_semantic_memory_leakage` is vacuous in every reachable configuration

The E7 leakage test (`tests/test_reasoning_span.py:272-281`) can assert nothing:

1. Default `Jarvis` constructor wires no semantic store → `jarvis.semantic_memories is None`
   (`jarvis.py:2217-2219`; verified empirically) → the guard `if store is not None:` skips the whole
   body.
2. With a store wired manually, a single `think()` leaves the store empty
   (`consolidate_semantic_memories` needs cross-episode abstraction; verified empirically: `[]`), so
   the loop never executes.
3. If the loop body **ever** executed, it would raise `AttributeError`: `SemanticMemory` has
   `pattern`, not `content` (`domain/entities/semantic_memory.py:70-71`).

The E7 *property* holds in code (nothing writes span threads into any memory surface); the property is
simply not what this test establishes.

### Finding 3 — minor: duplicate helper declaration

`_RecordingModel` is declared twice in the module (line 25 pre-existing, line 220 re-declared by this
commit); pyright's `reportRedeclaration` is a direct consequence, and it silently re-binds the
existing `_recording_reasoner` helper to the second class.

## 4. Closure verdict

**EPISODE-PATH REASONINGSPAN v1 — FAIL — DO NOT FREEZE, report-only.**

Every functional condition E1–E9 passes in the production code, and the production code is pyright-clean.
The freeze is blocked by the test-hygiene findings above: the repo's own audit gate (pyright strict,
tests included) fails at HEAD, and the dedicated E7 test is vacuous. This mirrors exactly the shape of
the previous forensic closure (`b978e4f`): logic verified; freeze blocked on a verifiable defect.

**Remediation (NOT applied under hard-stop rules, since this task forbids code/test changes):**

1. Delete the duplicated `_RecordingModel` (reuse the module-level helper).
2. Type the `episode.working_belief` accesses as `Belief` with a guard (or assert in test, as the rest
   of the suite does).
3. Replace the vacuous E7 test with one that wires a real semantic store built from ≥ the required
   episode sources, then asserts span statements never appear in `memory.pattern` (the correct field).
4. Re-run `pyright` to 0, `ruff check` clean, full suite, then re-freeze.

On that condition, the seam is otherwise clean to freeze: E1–E9 production-verified, 2176 passed /
3 skipped, ruff clean, no leakage, no frozen seam touched.

## 5. Accepted limitations (frozen, not defects)

- `curiosity.pursue` remains conversation-free / cold path: `run_episode` defaults `span=()` and the
  direct caller (`curiosity.py:319`) reasons without the session threads and records nothing. This is a
  declared property, not a contradiction (the reasoning machinery in `_reason_into` is identical; only
  the span supply differs).
- ReasoningSpan remains per-`Jarvis`-instance (ephemeral, built per instance, `jarvis.py:618`).
- `reset_reasoning()` remains the explicit reset seam (`jarvis.py:742-744`).
- No persistent reasoning span — `ReasoningSpan` has no serializer; no store references it.
- No new session object — the span reuses the pre-existing `ConversationContext`/`ReasoningSpan` shape.
- No streaming episode-path semantics — the episode path reasons via blocking `infer`
  (`executive_controller.py:911`); `infer_stream` remains the conversational `reason_stream` surface.

## 6. Current architecture map (updated pipeline trace)

`Experience → Perception → Interpretation → Attention → Memory → Reasoning → Reflection → Decision → Action → Outcome → Learning → Updated state`

| Stage | Implementation | Callers | Entering/leaving | Persisted / ephemeral |
|---|---|---|---|---|
| Experience | companion turn (episode origin COMPANION default, `cognitive_episode.py:79`) | `say`/fact routes, curiosity (CURIOSITY origin) | raw trigger + optional evidence | trigger persisted in EpisodeRecord |
| Perception | `PerceptionSource`/LLM extraction (candidate evidence only) | statement/fact ingestion | claims → `Evidence` | evidence persisted in belief |
| Interpretation | deterministic intent (`domain/conversation/intent.py`) | `_say` routing | intent classes | ephemeral |
| Attention | `_assess_attention` (`executive_controller.py:199-210`); saliency `derive_attention_priorities` (`attention_priority.py`) | `run`; `wake` (unwired, see matrix) / `feel_curious` (`wonder`) | belief confidence + new-evidence presence → BRIEF/FULL; topic saliency | attention persisted on episode |
| Memory | recall seam (lexical/semantic/documents), stores | `run` → `_recall_into` | RecalledMemory | recalled set on episode (not evidence) |
| Reasoning | `Reasoner` seam (`_reason_into`) — now span-continuous in the episode path | `run` (think path); `pursue` cold | inference → weak INFERENCE evidence + span thread | thread ephemeral; evidence persisted |
| Reflection | `_reflect` genuinely notices; meta-observation + knobs adaptation + `adapt_from_meta_observation` | `run` (gated by `_should_reflect`); reflective cycle | note; knobs deltas | note persisted on episode; learned state persisted |
| Decision | `_decide` (`executive_controller.py:1030`), grounded in derived confidence | `run` | decision string + evidence request | EpisodeRecord.decision |
| Action | reflective-cycle recommendations (`act_on_insight`); manual `act`/`record_outcome` (Va `actions.py`) | `reflect_cycle`, `Jarvis.record_outcome` | recommendation stance; outcome evidence → action-belief only | actions store |
| Outcome | `record_outcome` writes to action-prediction belief | manual / model-compare `_record_outcome` | outcome text | persisted |
| Learning | evidence-derived confidence, dedup (`same_observation`), decay (opt-in), consolidation (COMPANION-only, neutral-skipped), adapt knobs | `run` end; `consolidate_semantic_memories` | abstractions, adapted knobs | semantic memories, learned state |
| Updated state | beliefs, episodes, semantic memories, knowledge graph | — | — | — |

**Where information is presently dropped / computed-but-unconsumed (read-only findings):**

- **Knowledge graph is write-only from cognition.** `_remember` extracts and persists entities/edges
  (`executive_controller.py:1140-1148`); the only graph reads are `all_nodes()` (dedup on write).
  `path_between`/neighbors exist in all three stores with **zero** cognitive consumers (grep of
  `_knowledge_graph.` shows only `all_nodes`/`save_node`/`save_edge`).
- **Saliency attention (`wake`) has no runtime caller.** `derive_attention_priorities` is fully
  implemented and tested; the top-salient topic cannot reach a decision — `.wake(` appears in no caller
  (`interface/_cognition.py:98-104` uses the fixed `feel_curious` cascade only).
- **Action outcomes never reach the originating belief/episode.** `record_outcome` targets the
  action-prediction belief only (`actions.py:82-99`); the reflective `act_on_insight` recommendation
  (`cognitive.py:303-319`) has no automatic closure; `Action` carries no origin-episode link.
- Decisions that never see an available upstream signal: none of the above blocks a current decision —
  each is a *latent* signal, not a decision made in its absence.

## 7. Candidate seam matrix (evidence-backed, unranked)

| Candidate | Current state | Missing connection | Implementable now? | Frozen-seam conflict? | Evidence |
|---|---|---|---|---|---|
| Knowledge-graph reach into cognition | Graph written per `_remember`, never read by cognition | Graph connectivity → Connections/Reflection/attention as an optional derived context signal | Yes (graph repo + traversal APIs exist; additive consumer | None | `executive_controller.py:1140-1148`; zero `path_between` consumers; `knowledge_graph_repository.py:75` |
| Action outcome → originating episode/belief | Outcomes close only the action-prediction belief | Outcome/provenance link back to the episode or belief that recommended the action; automatic outcome capture | Yes (additive `Action` provenance field + optional outcome evidence onto the verifying belief) | None (actions are statement-addressed by design; no frozen seam covers it) | `actions.py:71-111`; `cognitive.py:303-319`; `Action` VO has no origin link |
| Wake-saliency wiring | `wake()`/`derive_attention_priorities` implemented + tested, unwired | Top-saliency topic → pursuit (one-shot `wake`→`pursue`) or reflective-cycle entry | **Partially** — a one-shot wiring is implementable now; a *repeating* loop needs the deferred scheduler | None | `curiosity.py:234-262`; zero `.wake(` callers; AI_CONTEXT defers the proactive loop to "shutdown-safe scheduling" |
| Episodic continuity for curiosity (`pursue` cold span) | `pursue` reasons with `span=()` | Session span → self-initiated episode reasoning | No (declared accepted limitation, not a defect) | Would reverse the frozen accepted limitation | `curiosity.py:319`; `run_episode` default `span=()` |
| Semantic identity via embeddings (beyond exact tokens) | Belief identity = canonical topic signature; evidence dedup = `same_observation` (content-exact); embeddings exist for recall only | Any embedding-based *identity* would redefine the frozen rules | No | **Yes — blocked by frozen Topic Identity v3 + Topic-Anchored Addressing v1 (`belief identity = canonical topic`)** and D15 evidence identity | `belief_repository.py`; `evidence_identity.py` |
| Topic-index cache | `resolve_episodes` re-resolves per `derive_attention_priorities` call; only `signature_of` has a bounded lru memo | Cached group-by | No (premature at current scale; conflicts with the explicit "no read-time memo/cache" design recorded in the addressing closure §9) | Conflicts with a documented invariant | `attention_priority.py:94`; `FORENSIC_CLOSURE_TOPIC_ADDRESSING_V1.md §9` |
| STT streaming/VAD | One-blob-per-hold; Web Speech default; `WhisperTranscriber` backend | Streaming/VAD mic delivery | No relevance to the cognitive architecture (infrastructure edge) | None | `audio/speech` seam; AI_CONTEXT future directions |

Trade-offs (no superiority claim): the graph and wake candidates are *pure consumption* of already
computed information (information-drop type), smallest and most reusable; the action-outcome candidate
adds provenance but touches the actions store surface; all three are independent and additive.

## 8. Deferred-seam status

- **Semantic identity matching** — **BLOCKED**: conflates with frozen Topic Identity v3 / Topic-Anchored
  Addressing v1 (belief identity = canonical topic) and D15 evidence identity. Do not weaken.
- **Proactive wake loop** — exactly what is missing: a **scheduler + lifecycle + shutdown safety +
  ownership**. Trigger semantics (`wake`→`pursue`, real representative trigger, persisted
  `target_topic_id`), ranking, and isolation are done. Persistence is not the blocker. Not implemented.
- **Topic-index cache** — **not a real seam now**: single calling surface (`wake`, itself unwired),
  small scale, and the addressing closure explicitly records "no read-time memo/cache" as design. Do not
  optimize prematurely.
- **STT streaming/VAD** — **infrastructure edge**, not a cognitive architecture seam; nothing cognitive
  depends on it. Stays deferred.

## 9. Special question — is there a concrete gap in the newly unified episode reasoning path?

**No new internal information-flow gap requiring examination before any new subsystem.**

The unified path (`think → run → _reason_into → infer(span) → record(trigger, answer)`) is now
coherent for its `think` callers: the recorded thread is derived from the completed inference only
(E3/E4), failure leaves the span untouched (E5), instances stay isolated (E6), recording is gated on
`episode.inference() is not None` (`jarvis.py:2070-2072`), and `confirm()` still seals/disputes the
correct thread (`jarvis.py:2483`).

The two boundaries the commit deliberately leaves — (a) recording authority lives only at the `Jarvis`
facade (`jarvis.py:2070-2072`), so any episode driver bypassing `think` (b) `curiosity.pursue` →
`run_episode` default `span=()` (`curiosity.py:319`) — are precisely the accepted limitations recorded
in §5 and are not contradicted by repository evidence. No new subsystem is warranted by the episode
path itself. The real blockholders before *any* next gate are the audit-gate failures in Findings 1–3.

## 10. Candidate next gates (implementable now, after the Findings 1–3 remediation)

### Gate A — Knowledge-graph reach into cognition
- **Current behavior:** graph written on every concluded belief; never read cognitively.
- **Observed gap:** "semantic information computed but ignored" — extracted entity/relationship structure
  persists with no consumer.
- **Why real:** the traversal APIs were built and persisted (all 3 stores) yet no cognition stage reads
  them; this is an information-drop, not a new capability fantasy.
- **Existing components:** `KnowledgeGraphRepository`/`path_between`/`neighbors`; Connections/Reflection
  read shared-evidence belief links today.
- **Minimal propagation:** an *optional, derived* graph-connectivity view (e.g., shared-entity
  connections surfaced beside `connections()`, or reflection noting entities touched by multiple
  beliefs) that is read-only context, never a decision.
- **Non-goals:** no new subsystem; no belief-identity change; no graph-driven confidence; no second
  belief store.
- **Hard-stop:** any change to belief identity/evidence semantics → abort.
- **Tests:** graph-connected beliefs surface as an option; absent graph → behavior unchanged; offline
  deterministic (in-memory graph), pyright strict.

### Gate B — Action-outcome provenance to the originating episode
- **Current behavior:** reflective `act_on_insight` returns a recommendation; `record_outcome` learns
  only into the action-prediction belief; `Action` carries no origin.
- **Observed gap:** "action outcomes that fail to update the originating cognitive episode" — the belief
  a reflection act was meant to verify never hears the outcome.
- **Why real:** `record_outcome` is a public, tested seam that nothing in the default pipeline closes;
  the recommendation→outcome loop is latent platform.
- **Existing components:** `Action`/`ActionRecommendation`, `actions.record_outcome`, the actions store.
- **Minimal propagation:** additive `Action.origin_episode_id` (or origin belief id) and an optional
  outcome-evidence write toward the origin belief, gated by origin presence (None ⇒ current behavior).
- **Non-goals:** no autonomy/execution change; no action-identity change.
- **Hard-stop:** no change to stances/confidence derivation; actions stay statement-addressed.
- **Tests:** recorded outcome with origin updates the origin belief distinctly from the action belief;
  without origin, behavior identical; pyright strict.

### Gate C — Wake-saliency one-shot wiring
- **Current behavior:** saliency attention is compute-and-test-only; `wonder` uses the fixed cascade.
- **Observed gap:** "attention signals not reaching decision" — the single most salient learned topic
  cannot initiate cognition.
- **Why real:** `wake()` fully implements the re-ranking; there is simply no caller.
- **Existing components:** `wake`/`derive_attention_priorities`/`ATTEND_THRESHOLD`; `pursue` runs the real
  representative trigger with persisted `target_topic_id`.
- **Minimal propagation:** a one-shot `wake`→`pursue` entry (e.g., a `wonder` alternative), not a loop.
- **Non-goals:** no scheduler/daemon; no persistence of priorities (derived per read by design).
- **Hard-stop:** no periodic background loop without shutdown-safe lifecycle (deferred item stays
  deferred).
- **Tests:** wired entry pursues the top topic; threshold behavior unchanged; cold Jarvis wakes to
  nothing; pyright strict.

## 11. Hard stops / blockers

1. **Pyright strict gate at HEAD** — 5 errors (tests). Freeze blocked; no further gate clean until fixed.
2. No code/test changes were made by this audit; the remediation in §4 must be done by the next
   implementation step.
3. No new subsystem is warranted by this closure's findings; the reactive path is otherwise coherent.
4. Do not reopen Topic Identity v3, Topic-Anchored Addressing v1, Polarity, Evidence/Confidence,
   Semantic Memory, Persistence, or Session architecture.

## 12. Validation (commands actually run, read-only)

| Gate | Command | Result |
|---|---|---|
| Diff | `git show b6a2159` / `git diff` | 4 files; additive production plumbing + 7 tests |
| Focused | `python -m pytest tests/test_reasoning_span.py -q` | **27 passed** |
| Full | `python -m pytest -q` | **2176 passed, 3 skipped** (matches report) |
| Lint | `python -m ruff check src tests` | **All checks passed** |
| Types (HEAD) | `python -m pyright` (strict, src+tests) | **5 errors** (Finding 1) |
| Types (parent) | same pyright in `13231a8` worktree | **0 errors, 0 warnings** |
| Default store probe | `Jarvis().semantic_memories` | `None` (Finding 2, vacuous test) |
| Wired-store probe | `InMemorySemanticMemoryStore` after one `think` | `all_memories() == []` (Finding 2) |

Note: `ruff format --check` is not an enforced gate in this repo (previous closure records gate only on
`ruff check`); it reports widespread pre-existing formatting opinions across untouched files and
additionally crashes in this ruff build (internal panic on snippet rendering) — environmental, unrelated
to `b6a2159`.