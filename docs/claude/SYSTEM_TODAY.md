# How Jarvis Works Today

**Source of truth for the running system** (currently Increment 180 — roadmap F6 shipped). Read this before
touching memory/cognition/recall code; read `ARCHITECTURE.md` for the detailed layer map and
`STATUS.md` only for history. Marked `[EXPERIMENTAL]` are implemented, tested, but not the
runtime default.

## The one-turn flow

```text
USER INPUT
   │
   ▼
CONVERSATION (interface/_conversation.py, _say → _say_core)
   │  IntentClassifier (domain/conversation/intent.py, bilingual, deterministic):
   │  GREETING | SMALLTALK | FEEDBACK | INSTRUCTION | REMEMBER | STATEMENT | ACT
   │
   ├─ question ────────────────────────────────────────────────┐
   │   _is_question = ends in "?" or a _QUESTION_CUES opener    │
   │   ("when"/"cuando" deliberately NOT question cues)         │
   ├─ statement → _remember_statement: ≥3-word non-question     │
   │   → USER_STATEMENT evidence (weight 1.0) → jarvis.think    │  ← statements are MEMORY (Inc 167)
   ├─ revision cue → companion.revise_companion / Belief.revise │  ← a changed mind is first-class (Inc 169)
   └─ directive  → ConversationIntent.ACT → charitable compiler │  ← earned agency, sandboxed, approved=False (Inc 160);
       │            → Jarvis.execute: decided-script when        │    a charitable envelope compiles first (Inc 179)
       │              compilable, else the offline agent          │
                                                               ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ EXECUTIVE (ExecutiveController.run)  — the thin decider                   │
   │   recall   MemoryRetriever: relatedness = max(surface_overlap, concept_relevance)
   │            (bilingual CONCEPT_MAP; SEMANTIC is a tie-break; turns surface-only)
   │   consult  KnowledgeSource: one deliberate edge visit (research/web/graph)
   │   reason   ReasoningSpan across turns (Inc 145); Reasoner proposes, never decides
   │            a live spoken turn rides the same span (Inc 180)
   │            strategy selected per query from live, revisable strategy_stats (Inc 166)
   │   graph    relation-aware traversal when a stored relation cue matches (Inc 166)
   │   topic    canonical identity: episodes group by concept signature, never raw trigger (Inc 163)
   └──────────────────────────────────────────────────────────────────────────┘
   │
   ▼
 MEMORY / COGNITION
   CognitiveEpisode → derive confidence (evidence, NEVER assigned) → Belief/HypothesisSet
   consolidation/abstraction: COMPANION-only episodes + neutral evidence (Inc 164)
   change of mind → precedents archive; superseded never recalled (Inc 169)
   transient EvidenceRequest when a FULL-attention question arrives evidence-less (Inc 170)
   │
   ▼
 CONTEXT → LLM (optional)
   LanguageModel seam: OpenAiCompatible + pydantic-ai + fallback (JARVIS_LLM_BACKUP_*)
   guardrail: a decline (EN/ES content filter) is honest silence  (Inc 157)
   provider_stats: bookkeeping only, never influences a decision (Inc 156)
   │
   ▼
 RESPONSE (rendered from real state, never invented)
   stance, documents chips, honest "insufficient evidence", or an honest decline
```

## Facts that hold at HEAD

- **Conversation is context, never memory** (Inc 167): `MemoryKind.CONVERSATION` is surface-only,
  matched lexically, never recited as an answer. The ring is bounded (`ConversationContext`
  `capacity=12`), rehydrated from persistence at construction.
- **Statements are real memory** (Inc 167): an everyday ≥3-word non-question sentence is stored as
  `USER_STATEMENT` evidence through `_remember_statement` (companion channel when first-person) and
  *persists* — a follow-up question after a restart answers from memory (proven in
  `tests/test_end_to_end_memory.py`).
- **Recall by meaning with no embeddings**: the offline lexical retriever ranks every durable candidate
  with `relatedness` (paraphrase + ES↔EN). Embedding recall is opt-in
  (`Jarvis.enable_embedding_recall`) `[EXPERIMENTAL]`.
- **Document search is passage-level** (Inc 175, roadmap F4): `search_passages` on the `DocumentStore`
  seam ranks deterministic word-window chunks (32 words, 8 overlap, byte offsets, no embeddings) with the
  same `relatedness` scorer; recall provenance is `document: <name>@<start>-<end>`, chat chips cite the
  passage + offsets, `documents search` returns the offending sentence + offsets, and binaries are never
  chunked (findable by name only).
- **Voice input is live, streaming, or VAD-segmented** (Inc 176, roadmap F5): the ear seam adds an
  optional streaming contract — `can_stream_partials` feature-detect + `stream_transcribe(chunks)`
  yielding each new growing partial once (Whisper backers `True`, echo ear `False`). The `speech`
  snapshot block reports `streaming` honestly; a streaming ear gets a live preview
  (`POST /api/speech/stream?final=0`, closed with `final=1`), a non-streaming ear is auto-segmented
  in-browser (AnalyserNode silence ≥ `VAD_SILENCE_HOLD_MS` closes a segment and reopens) — long speech
  needs no press-hold-release. Web Speech stays the offline default. A live ear's final transcript
   is also a **server-side spoken turn** (`POST /api/speech/turn`, Inc 180): the CLI posts the
   transcript once and it runs the same `say` pipeline, so the voice session rides the session
   `ReasoningSpan` exactly like typing. The snapshot advertises `turn_endpoint` and the console uses it.
- **Edge depth behind every seam** (roadmap F6, Inc 177-179): calendar draws a remote CalDAV/ICS feed
  one-way into SQLite behind `CalendarStore` (`calendar sync`, honest "no calendar sync" state when
  unwired); mail lists per-account folders and `unread:` messages (`mail folders` / `mail list unread`);
  and a material ACT envelope compiles to a named **decided-script** (`tool key="value"` grammar) via
  `compile_charitable_instruction` — write/read/echo envelopes run deterministically through the
  `approved=False` instruction agent with zero LLM, while destructive/external steps still refuse at the
  gate.
- **Belief identity is canonical-topic-anchored** (Inc 163): `topic_resolution.py`, empty signatures
  never fuse, representative is display-only.
- **Consolidation is COMPANION-only and neutral-evidence-only** (Inc 164): valence never invented.
- **Change of mind resolves** (Inc 169): `Belief.revise()` / `Jarvis.revise_companion()` archive the
  superseded stance; resolution survives restarts on in-memory, JSON, and SQLite.
- **Confidence is derived, never assigned** (D3); **LLMs are perception components, not judges** (D6);
  **offline deterministic core** (D8).
- **Persistence**: `Jarvis()` in-memory · `Jarvis.persistent(dir)` JSON · `Jarvis.database(dir)` SQLite
  `jarvis.db` (D10/Inc 150-152); command center uses SQLite when a home is set
  (`JARVIS_HOME=./.jarvis` by default; empty `JARVIS_HOME` = in-memory).
- **Forgetting is scheduled and honest** (Inc 173): `ForgettingCandidates` (domain service) runs
  `identify_forgetting_candidates` + the decay policy on the rest cadence (`rest()` → read-only
  `refresh_forgetting`) and behind the `forgetting` command (`health` / `dry-run` / `apply`); the UI
  shows memory health and **never deletes without an explicit apply**. Gates: never a grounded
  ≥threshold companion trait, never a belief reaffirmed in the last 30 days (anti-nagging).
- **Decay weighting is wired** (Inc 173): the server root instantiates `DecayingWeightingPolicy`, so
  recall ranks old, rarely-touched topics lower (`relatedness * recency(t)`).
- **Open-question loop completion** (Inc 174, roadmap F3): an open question is an *attention* candidate,
  never a standing item on a shelf. When a conversational turn *re-triggers* an open question (same
  honest relevance floor the writer uses, `relatedness >= 0.2`) **and** Jarvis grounds it
  (confidence ≥ `grounded_confidence`, the answer belief bears at the firmer `relatedness >= 0.3`),
  the turn's own wording retires the question (newest companion-language USER_STATEMENT, else the
  belief's subject) via `resolve_open_question`. A companion confirmation also grounds+retires;
  an ungrounded re-ask ("I still wonder …") **never** retires (grace). `open-questions` /
  `settle-question` surfaces + `memory.open_questions` in the snapshot; the loop closes in the
  conversation flow (`_retire_answered_questions` in the `say` handler).
- **Temporal reasoning is read-only applicability**, not prediction: `belief_timeline` /
  `what_changed` / `belief_snapshot_at` / `detect_pattern` reconstruct history. Stored belief confidence
  is never silently decayed — only an explicit `apply` forgets (storage stays honest).

## Status legend

| Status | Meaning |
|---|---|
| implemented | in the runtime default, tested at HEAD |
| `[EXPERIMENTAL]` | implemented + tested, opt-in only (live providers, embeddings, fallback, MCP) |
| partial | seam exists; some surfaces unused at runtime |
| planned | vision only; do not document as working |

## How to keep this document true

After any change that touches the flow above, update this file in the same commit. It is the shortest
truthful arc from a user turn to a reply.