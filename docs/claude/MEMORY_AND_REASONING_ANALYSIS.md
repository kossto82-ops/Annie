# Jarvis — Why it stalls, and the next evolution (Memory & Reasoning)

> Analysis phase only. No code was changed and nothing was installed to produce
> this. Every claim below points at real code (`file:line`). The purpose is to
> explain **why Jarvis keeps answering "I don't have enough information"** and to
> design the smallest evolution that fixes it without betraying the Vision.

---

## 1. Current real state — what Jarvis actually does

The conversational entry point is **not** `Jarvis.think`. When the user types in
the command center, the browser POSTs `say`, which runs
[`_say_core`](../../src/jarvis/interface/command_center.py) (`command_center.py:183`).
That function does exactly two things, then renders:

```
say(text)
├── jarvis.perceive(text, trigger=text)      # the "world" channel
│      └── perception.perceive(text) -> evidence
│      └── think(text, evidence) -> ExecutiveController.run -> working belief + decision
├── jarvis.note_companion(text)              # the "relational" channel
│      └── companion_perception.read_companion(text) -> traits about the user
└── render:
       if learned traits      -> "Got it — I'll remember this about you: …"
       elif belief is grounded -> narrate the belief
       else                    -> "I don't have enough to form a view on that yet…"
```

Key facts, all verified in code:

- **A user turn becomes a belief named after the literal text.**
  `working_statement(trigger)` = `"Working conclusion about: " + trigger`
  (`executive_controller.py:61`). The belief is retrieved by **exact string**:
  `beliefs.get_by_statement(statement)` (`executive_controller.py:242`).
- **Confidence is structural and starts at 0.** `derive_confidence` =
  `supporting / (supporting + contradicting + 1)`; no evidence → `0.0`
  (`belief.py:57-69`, `belief.py:16`). A belief cannot be given confidence; it is
  always recomputed from evidence.
- **The decision is chosen from that confidence** (`executive_controller.py:272-314`):
  `confidence <= 0` → `"Insufficient evidence to conclude about: <trigger>"`;
  `< 0.5` → tentative; `>= 0.5` → concluded.
- **Evidence only ever comes from two narrow places:**
  1. what the perceiver extracts **from the current input text**
     (`jarvis.perceive` → `perception.perceive`, `jarvis.py:298-310`); and
  2. a companion belief whose trait text is a **literal substring** of the trigger
     and is already ≥0.5 confident (`_seed_from_companion` → `relevant_to`,
     `executive_controller.py:248-265`, `companion_model.py:58-71`).
- **The LLM has exactly two jobs, neither of which is reasoning:**
  - *Perception* (`llm_perception.py:26-33`): "extract the factual **claims the
    text makes**". A question makes no claims → returns `[]` → no evidence.
  - *Voice* (`llm_response_renderer.py:19-24`): "Rephrase … Preserve the meaning
    EXACTLY: do not add, remove, or change any fact." It can only reword the reply
    the core already decided.
- **There is no retrieval by meaning anywhere.** Every "recall" in the codebase is
  exact-string or substring: `get_by_statement`, `relevant_to`
  (substring, `companion_model.py:64-70`), recurring-goals counting on identical
  trigger strings. Grep for `embedding|similarity|vector|semantic|retrieve`
  returns only comments saying "semantic matching is a later concern".

So the running system is: **extract assertions from the user's own sentence,
weigh them into a belief about that exact sentence, and report whether that belief
is grounded.** Plus a side channel that stores traits about the user.

---

## 2. Diagnosis — why "I don't have enough information" is the default

Trace each of the example inputs through the real `say` path:

| Input | perceive() yields | note_companion() yields | Retrieval that could answer | Result |
|---|---|---|---|---|
| `Hola` | keyword: nothing / LLM: `[]` (no claim) | nothing | — | insufficient → generic no-view |
| `¿sabes cómo me llamo?` | `[]` (a question asserts nothing) | nothing (it's a question, not self-disclosure) | none — `say` never reads the companion model to *answer* | no-view, even if the name was taught |
| `¿Qué opinas de Graphify para Jarvis?` | `[]` | nothing | none | no-view |
| `¿Qué hemos intentado con Jarvis?` | `[]` | nothing | none — `recurring_goals`/episodes not consulted by `say` | no-view |
| `¿Qué sabes sobre mi proyecto?` | `[]` | nothing | none | no-view |
| `¿Cómo creo una herramienta HTML que busca y filtra?` | `[]` | nothing | none | no-view |

The pattern is exact and mechanical:

1. **A question contains no assertions**, so the perceiver (keyword *or* LLM)
   produces **zero evidence** → the working belief has confidence `0.0`
   (`belief.py:69`).
2. `_decide` maps confidence `0.0` to
   `"Insufficient evidence to conclude about: …"` (`executive_controller.py:280-291`),
   which the surface softens to *"I don't have enough to form a view on that yet"*
   (`command_center.py:220-228`).
3. **No channel retrieves relevant memory to answer**, and **no channel reasons
   from general knowledge.** The only "memory" lookup in the path is *"have I
   concluded about this exact string before?"* — which is empty for any new
   phrasing.

Answering the specific investigation questions from the brief:

1. **Which component emits these strings?** `ExecutiveController._decide`
   (`executive_controller.py:280-291`) produces the canonical text; the
   self-referential "I tend to conclude without sufficient evidence" variant is
   the same method under a learned-habit branch (`:281-287`), fed by
   `self_observation.py:41`. The surface wrapper is `command_center.py:220-228`.
2. **Why does a question become a "working belief"?** Because every trigger is
   turned into `"Working conclusion about: <trigger>"` and an episode always
   forms/adopts that belief (`_resolve_working_belief`, `executive_controller.py:240-246`).
   The system has no concept of "this input is a *question/request*, not a claim to
   form a belief about."
3. **What happens when no prior belief exists?** A fresh belief with **no
   evidence** is formed (`episode.form_working_belief`), confidence `0.0`.
4. **What evidence is provided to the new belief?** Only what the perceiver got
   from the input text (nothing, for a question) plus a substring-matched companion
   belief (almost never fires). So: none.
5. **Why confidence 0?** Structural: `0 / (0 + 0 + 1) = 0` (`belief.py:69`).
   Correct — but it is being used as the *response selector*, not just as belief
   strength.
6. **Why can't Jarvis just reason about a new question?** Because **no code path
   exists that reasons.** The LLM is fenced to perception+voice by design
   (`llm_perception.py`, `llm_response_renderer.py`); the domain only weighs
   evidence it was handed. Nothing turns a question into an answer.
7. **Where is the problem?** Not in one class — it is a **missing cognitive path**
   spanning the entry point and the executive:
   - `command_center._say_core` has only two channels and a no-view fallback.
   - `ExecutiveController.run` has no *retrieval* step and no *inference* step;
     it can only weigh handed-in evidence.
   - The belief model, persistence, and confidence derivation are **correct** and
     are **not** the cause.

**Root cause, one sentence:** *Jarvis can only form a belief about the exact
sentence you just said from the assertions inside that sentence; it never recalls
relevant memory to answer, and never reasons from knowledge — so any question, and
any input that asserts nothing, collapses to "insufficient evidence."*

---

## 3. Is `JARVIS_VISION.md` the problem?

Mostly **no** — the philosophy is sound and worth keeping. The paralysis comes
from a few principles being implemented too literally, and from a long-term
principle being enforced as an immediate runtime rule. Classified as the brief
asks (A keep / B correct-but-mis-implemented / C ambiguous / D long-term-only):

- **§7–§9 "confidence derived from evidence; never stronger than evidence"** —
  **A. Keep.** Structural, elegant (`belief.py`). Do not touch.
- **§18 contradictions first-class / §17 competing hypotheses** — **A. Keep.**
- **§37 "I have insufficient evidence"** — **B. Correct principle,
  mis-implemented.** The principle means *don't fabricate a grounded belief*. It
  has been turned into *the universal reply for any input that yields no extractable
  assertion* — including questions and requests that never called for a belief.
  A question doesn't need a grounded belief to deserve a useful, clearly-hedged
  answer. This single overreach is most of the felt problem.
- **§38 / D6 "the LLM extracts candidate evidence; the core is the judge"** —
  **B. Correct principle, mis-implemented.** "Judge, not decider" was collapsed
  into "the LLM may only extract assertions from the input and reword the output."
  **Inference is a legitimate candidate source**: an LLM (or any reasoner) can
  *propose* a provisional answer, and the core can accept it as **low-provenance,
  clearly-labeled inference** whose confidence is still derived and still beatable
  by real evidence. That honors §38 while restoring usefulness. Today there is no
  inference channel at all.
- **§3 continuity / §5 companion model / §21 persistence** — **A. Keep**, but see
  §4: they are stored and never *retrieved to answer*.
- **"Semantic/relevance retrieval"** (D11, AI_CONTEXT "known debt") — **D → promote
  partway.** It is filed as a *future* enhancement, but its **absence is exactly
  what makes memory unusable in conversation.** The fix is not embeddings yet: a
  **deterministic lexical retriever** (offline, D8-safe) is enough to make memory
  answer questions. Promote *that* now; keep embeddings as the later step.

Nothing in the Vision says "don't answer questions" or "never reason." Those are
implementation choices that read the Vision more narrowly than it requires.

---

## 4. Architectural problems (by concern)

- **Memory retrieval — missing.** Persistence exists (JSON stores), *retrieval by
  relevance does not*. The only recall is exact-string/substring. There is no
  `recall(query) -> ranked items`. This is the #1 gap.
- **Reasoning — missing for novel input.** The executive weighs evidence it is
  given; it cannot generate a provisional answer when no belief and no evidence
  exist. No inference stance.
- **Response generation — conflated with cognition.** `_decide` emits the exact
  user-facing sentence from confidence alone (`executive_controller.py:272-314`).
  There is no separation between *what Jarvis concluded* and *how it should
  respond to this kind of input* (a question vs. a claim vs. a greeting).
- **Input has no type.** Everything is a "trigger" that becomes a "working
  conclusion about <text>". Greetings, questions, requests, and assertions are all
  forced through belief-formation.
- **Beliefs — fine.** Derivation, contradiction handling, stability, provenance,
  `explain/narrate` are correct and reusable. Do not rebuild.
- **Persistence — fine but coarse.** JSON per store, keyed by exact statement.
  Adequate for now; it is not the bottleneck. Event traces are in-memory only
  (`EpisodeTrace`), so provenance is lost across restarts (known debt).

---

## 5. What already works (do not rebuild)

- Evidence-grounded `Belief` with derived confidence + temporal stability, events,
  and `explain().narrate()` self-explanation (`belief.py`).
- Companion model as revisable beliefs with contradiction handling
  (`companion_model.py`, `jarvis._record_companion`).
- Episode lifecycle, attention/energy, deliberation over competing hypotheses,
  the full reflective cycle Connect→Reflect→Hypothesise→Challenge→Learn
  (`jarvis.py:824-845`).
- Provider-agnostic perception + voice seams and a runtime-swappable registry
  (`perceiver_factory.py`, `language_model_registry.py`) — offline by default.
- JSON persistence wired end-to-end (`Jarvis.persistent`).
- Command center as a pure, testable `handle/route/snapshot` surface.

The machine is well built. It is missing two *cognitive paths*, not better parts.

---

## 6. What is missing (especially for long-term memory)

1. **A retrieval capability**: given a query (the user's turn), return the most
   *relevant* remembered items — past episode conclusions, world beliefs, companion
   traits, recurring goals — ranked, with provenance. Today nothing does this.
2. **A way to feed retrieved memory into an episode** as standing context/evidence
   — a generalization of the existing `_seed_from_companion` (which only fires on a
   literal substring match).
3. **An inference channel**: when there is no memory and no extracted evidence, the
   ability to produce a *provisional, clearly-labeled* answer instead of a refusal.
4. **A response policy** that distinguishes Memory / Knowledge / Inference /
   Uncertainty / Ignorance and picks the honest one — separate from belief
   confidence.
5. (Later) durable event/provenance traces; (later) semantic (embedding) retrieval;
   (later) typed relational links between memories.

---

## 7. Recommended architecture

The fix stays inside the existing boundaries. Two new **domain Protocols** and one
new **executive step**; everything else is reuse. No new storage tech, no new
dependency, no violation of D6/D8/D10/D12.

```
USER TURN (say)
      │
      ▼
┌──────────────────────────────────────────────────────────────┐
│ ExecutiveController.run(episode)                               │
│                                                                │
│  1. classify input          → CLAIM | QUESTION | GREETING …    │  (pure, deterministic)
│  2. RECALL relevant memory  → MemoryRetriever.recall(query)    │  ← NEW seam (domain Protocol)
│         beliefs · episodes · companion traits · goals          │
│         ranked, each carrying provenance + weight              │
│  3. observe: handed evidence + recalled memory (as SYSTEM      │
│         evidence, like _seed_from_companion, generalized)      │
│  4. derive belief confidence (unchanged, structural)           │
│  5. if still ungrounded AND input wants an answer:             │
│         Reasoner.infer(query, recalled) → provisional answer   │  ← NEW seam (domain Protocol)
│         recorded as INFERENCE evidence: low provenance,        │
│         clearly labeled; confidence still derived              │
│  6. choose cognitive STANCE from (memory? knowledge? evidence?)│
│         Memory | Knowledge | Inference | Uncertainty | Ignorance│
└──────────────────────────────────────────────────────────────┘
      │
      ▼
RESPONSE GENERATION (surface): render the stance in the companion's language
   (voice renderer rewords; it still never invents facts)
```

Two seams, both mirroring the existing `PerceptionSource` pattern (domain
Protocol, infrastructure adapter, offline default, swappable):

```
domain/retrieval/memory_retriever.py   (Protocol)      # recall(query) -> ranked hits w/ provenance
domain/reasoning/reasoner.py           (Protocol)      # infer(query, context) -> provisional claim(s)

infrastructure/lexical_memory_retriever.py             # DEFAULT: deterministic keyword/overlap ranking, offline (D8)
infrastructure/embedding_memory_retriever.py           # LATER: semantic; opt-in, behind same Protocol
infrastructure/llm_reasoner.py                         # opt-in: LLM proposes; output is INFERENCE evidence, never a verdict
infrastructure/silent_reasoner.py                      # DEFAULT offline: no inference -> honest "I can reason once an LLM is active"
```

Why this shape:

- **Retrieval is a *capability provider*, exactly like perception.** It only
  *surfaces candidates carrying provenance*; the domain still derives confidence
  and decides (D6/§38 honored). Same design already sketched for the future
  `GraphRetriever` in `docs/graphify.md §9`.
- **Inference is candidate evidence, not a judge.** `LlmReasoner` output enters as
  `EvidenceSource.INFERENCE` (new, low policy weight in `evidence_weighting.py`),
  so a real observation always outweighs a guess, and the answer is labeled *"I
  don't recall discussing this, but reasoning from what I understand…"*.
- **Stance ≠ belief confidence.** The response layer chooses among five honest
  stances; "insufficient evidence" stops being the catch-all.

---

## 8. Storage decision — keep JSON now

**Recommendation: E (evolve the existing repositories first), stay on JSON for
this phase.** Reasons:

- The problem is **retrieval logic, not storage tech.** A lexical retriever can
  run over the existing `beliefs.all_beliefs()` / `episodes.history()` /
  `companion.beliefs()` with zero schema change.
- D10 is explicit: define the retrieval contract in the domain; swap storage
  behind it later. Introducing Postgres/SQLite *now* would be adding infrastructure
  to solve a problem that isn't infrastructural.
- **When to migrate:** move to **SQLite** (option A, local, offline, no server —
  respects D8) once (a) `all_beliefs()` scans become the measured bottleneck, or
  (b) you need durable event traces / indexed queries. SQLite is the right first DB
  because it is a file, needs no daemon, and keeps tests offline.
- **PostgreSQL / pgvector**: only if/when embeddings + concurrent access are real
  needs — behind the same repository/retriever Protocols. Not now. **Do not
  install it for this phase** (Rule 0).

---

## 9. Graph database decision — none now

**Recommendation: none (option "ninguna") for this phase.**

- **Neo4j / Postgres-graph: no.** There is no consumer that needs graph traversal
  in cognition yet; adding one would be drift (D12). Relational structure that
  Jarvis already has (`connections()` = beliefs sharing evidence, sub-goal links)
  is enough for the first evolution.
- **Graphify: stays a dev-time code-navigation tool (D14).** It indexes *source
  code*, not cognition, and must not become Jarvis memory.
- **Future:** if relating concepts across long-term memory ever needs real graph
  queries, implement the already-designed domain `GraphRetriever` Protocol
  (`docs/graphify.md §9`) with a swappable adapter — **only when a real consumer
  exists.** The `MemoryRetriever` seam in §7 is the natural place that consumer
  would later appear.

---

## 10. Memory model — entities, relations, responsibilities

Reuse the existing domain vocabulary; add retrieval, not new stores.

| Memory kind | Already exists as | Retrieved for |
|---|---|---|
| Episodic | `EpisodeRecord` history (`episodes.history()`) | "what did we do / decide / try?" |
| Semantic (world beliefs) | working-conclusion `Belief`s (`beliefs`) | "what do you think about X?" |
| Autobiographical / self | self-tendency beliefs (`self_beliefs`) | "what are you like?" |
| Relationship (companion) | `CompanionModel` beliefs | "do you know my name / my project?" |
| Goal | reachability beliefs + `recurring_goals` | "what are we trying to achieve?" |
| Decision | `EpisodeRecord.decision` + `Deliberation` | "what did we decide about Y?" |

Relations (already latent, no graph DB needed yet): shared-evidence
`Connection`s (`association.py`), sub-goal `part_of` links, and
correlation-id event traces. A typed relational layer is a *later* step, only if
retrieval quality demands it.

Responsibilities:

- **Repositories** (infra): store/fetch by id/statement — unchanged.
- **`MemoryRetriever`** (domain Protocol; infra adapter): *rank by relevance to a
  query*. This is the new responsibility, and it is the missing one.
- **Executive**: call recall, fold hits into the episode as provenance-carrying
  evidence, pick a stance. Stays thin.

---

## 11. Retrieval pipeline (selective, not exhaustive)

```
USER QUERY
   │
   ▼
classify (deterministic): CLAIM | QUESTION | GREETING | REQUEST
   │  (greetings/claims may skip recall; questions/requests run it)
   ▼
MemoryRetriever.recall(query, kinds=?, limit=K)
   ├── candidate gather: beliefs · episodes · companion · goals
   ├── score: lexical overlap now (embeddings later) + recency + confidence
   ├── threshold + top-K (K small, e.g. 5)  ← token discipline
   ▼
ranked hits (each: content, kind, provenance, weight)
   │
   ▼
fold top hits into the episode as SYSTEM/RECALL evidence
   │
   ▼
reason / derive belief / choose stance
```

Selective by design: greetings and pure self-disclosures don't run recall;
recall returns **top-K small**, not the whole store; scoring is cheap and offline.
This directly satisfies the brief's token-efficiency and performance sections
(21–22): small query → small, high-relevance context → reasoning. Never "load the
whole memory into the prompt."

---

## 12. Response generation — from memory+knowledge+reasoning to a useful reply

Separate **cognition** (what Jarvis concludes) from **response** (how it says it).
The episode produces a **stance**; the surface renders it. The five honest stances
(the brief's §4/§5) map onto real state:

| Stance | Condition (from recall + evidence) | Shape of reply |
|---|---|---|
| **Memory** | recall found strongly-relevant, confident items | "Yes — we discussed this. We decided X because…" |
| **Partial memory** | recall found related but not decisive items | "I remember X, but I don't find that we settled Y." |
| **Knowledge / Inference** | no memory, but reasoner produced a provisional answer | "I don't recall discussing this, but reasoning from what I understand… (this is inference, not a settled view)." |
| **Uncertainty** | competing hypotheses / contested belief | "I have two readings; the evidence doesn't yet decide between them." |
| **Ignorance** | nothing to recall and nothing to reason from | "I don't have enough to say — tell me more." (today's default, now the *rare* case) |

Crucial guardrails (keep the Vision intact):

- The **stance is chosen by the domain**, from recall results + derived confidence
  — **not** by the LLM. The LLM only (a) proposes inference candidates (marked,
  low weight) and (b) rewords the final reply. §38/D6 preserved.
- Inference is always **labeled and beatable**: it enters as low-provenance
  evidence; one real observation outweighs it; confidence stays derived.
- "Insufficient evidence" survives, but only as the genuine **Ignorance** case,
  not as the answer to every question.

---

## 13. Migration strategy (no destruction of the existing architecture)

1. **Add contracts, don't change cognition.** Introduce `MemoryRetriever` and
   `Reasoner` Protocols in the domain with **offline defaults** (lexical retriever;
   silent reasoner). Wire them optionally into `ExecutiveController` — when absent,
   behaviour is byte-for-byte what it is today (offline tests stay green, D8).
2. **Generalize `_seed_from_companion`** into a recall step that folds top-K hits
   as evidence. This is an extension of an existing, tested mechanism, not a rewrite.
3. **Add the stance layer** in `_decide`/response, keeping the exact current strings
   for the Ignorance branch so existing tests (`"Insufficient evidence" in result`)
   still pass; new stances are new branches.
4. **Keep storage as JSON.** Only introduce SQLite behind the repository Protocols
   when measurements demand it (§8) — a later, isolated increment.
5. Every step is independently testable and reversible; no belief/persistence
   contract changes.

---

## 14. Roadmap (small, verifiable increments)

Priority order follows the brief: long-term memory first; the rest sequenced but
not built now.

- **Inc A — Input classification.** Deterministic `classify(text)` →
  CLAIM/QUESTION/GREETING/REQUEST. Test-only; no behaviour change yet. *Verifies:*
  greetings/questions are distinguishable from claims.
- **Inc B — `MemoryRetriever` Protocol + lexical adapter (offline).** `recall(query)`
  over beliefs/episodes/companion/goals, ranked, top-K. Pure/offline. *Verifies:*
  "sabes cómo me llamo?" and "¿qué hemos intentado con Jarvis?" surface the stored
  name/goals in recall results.
- **Inc C — Fold recall into the episode + Memory/Partial-memory stances.**
  Generalize `_seed_from_companion`; add the two memory stances. *Verifies:* those
  two questions now get a remembered answer end-to-end (real-data-proven in the
  command center), while offline tests stay green.
- **Inc D — `Reasoner` Protocol + Knowledge/Inference stance.** Silent by default;
  `LlmReasoner` opt-in behind the seam; output = labeled `INFERENCE` evidence,
  low weight. *Verifies:* "¿Qué opinas de Graphify?" and the HTML how-to get a
  provisional, clearly-hedged answer when an LLM is active; still honest Ignorance
  offline.
- **Inc E — Uncertainty stance polish** over existing contested-belief / hypothesis
  machinery (already largely present via `ask_about`/`consider`).
- **Later (not now):** durable event traces; embedding retriever behind the same
  Protocol; SQLite behind repositories when measured; typed relational links;
  reflection/experience/proactive-thinking capabilities (brief §10 items 2–7).

---

## Success criterion

The target is behavioural, not architectural. After Inc C+D, the six example inputs
should produce (offline where noted):

- *remembered* → "Yes, we discussed this; we decided X because…"
- *partial* → "I remember X, but I don't find we settled Y."
- *no memory, can reason* → "I don't recall discussing this, but reasoning from
  what I understand… (inference, not a settled view)."
- *genuine uncertainty* → "I have two readings; the evidence doesn't decide yet."
- *belief change* → "I held X on A; new evidence B contradicts it, so I now lean Y."

"I don't have enough information" becomes the **rare, honest** case — not the
default. The epistemology still governs *how strongly* Jarvis asserts; it no longer
governs *whether Jarvis is allowed to think*.
