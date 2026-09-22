# Jarvis — Architectural Decisions

This file is intentionally short. It contains decisions Claude should treat as constraints unless the user explicitly asks to revisit them.

## D1 — Jarvis is not an agent wrapper; the core owns cognition

Do not introduce an outer autonomous-agent framework that calls Jarvis methods to
*simulate cognition*. The reflective cycle and all reasoning/deciding stay inside
Jarvis's core (Delegating any of *that* is forbidden).

Jarvis MAY delegate **material actions** to an edge agent (e.g. Odysseus agent mode)
behind a domain seam (D7): the agent executes concrete tasks with its own tool
catalog (email, notes, calendar, shell, web, …) and returns *outcomes with
provenance*. It never substitutes for Jarvis's judgement (D6) and never writes to
Jarvis's beliefs/memory directly. Delegation is governed by the existing
controlled-autonomy policy (risk + permission + confidence + reversibility →
EXECUTE / ASK / REFUSE) and by the Tool Registry's permission levels (destructive /
external demand approval). The boundaries are earned, observable, reversible, bounded.

## D2 — Cognitive Episode is the unit of cognition

A prompt/response is not the fundamental unit. New cognitive functionality should attach to the episode/state model where appropriate.

## D3 — Evidence precedes belief strength

Belief confidence is derived from evidence. Do not add setters or shortcuts that allow arbitrary confidence assignment.

## D4 — Contradictions are first-class

Contradicting evidence must remain visible and auditable. Do not silently overwrite or discard it.

## D5 — Competing hypotheses remain possible

Do not force one explanation when evidence does not justify choosing it.

## D6 — LLMs are perception components, not judges

An LLM may extract candidate evidence from language. The domain derives confidence and makes decisions.

## D7 — Provider agnostic

No provider SDK should leak into the domain. Provider selection belongs at composition/configuration boundaries.

## D8 — Offline deterministic core

The default test suite must not require network access or API keys. Live integrations are opt-in.

## D9 — UI is not cognition

The Command Center renders and routes state. It must not become a second brain.

## D10 — Repository abstraction before database choice

The domain defines repository contracts. Persistence technology can change behind them. Do not introduce PostgreSQL/SQLite/graph DB merely because a feature sounds like memory.

## D11 — Shallow matching is deliberate outside identity

Belief identity is **canonical-topic-anchored** since Increment 163 (episodes group by concept
signature, never by raw trigger) and recall reaches the same memory by meaning since Increment 168
(`relatedness = max(surface_overlap, concept_relevance)` over a bilingual concept map). Deliberately
*shallow* keyword matching may still be used in surfaces that only *propose* options (capability scout,
gap detection) — never to decide identity, evidence, or confidence. Embeddings are an opt-in recall
channel, not an identity mechanism.

## D12 — Prefer domain concepts over generic abstractions

Avoid generic `Manager`, `Engine`, `AIService`, `Orchestrator`, or wrapper abstractions unless they represent a real responsibility that cannot live in an existing domain/infrastructure component.

## D13 — Configuration over hard-coded providers/tunables

When adding provider selection or runtime tuning, prefer injected/configured values over module-level constants.

## D14 — Graphify is a dev-time tool, not Jarvis memory

Graphify indexes source code into a local code graph for Claude Code navigation
(`.mcp.json`, `docs/graphify.md`). It is not imported by Jarvis, not in
`pyproject.toml`, and not a substitute for episodic/semantic/belief memory. Only
the deterministic `graphify update` (AST, no LLM) path is used — consistent with
D8. If Jarvis ever needs graph *retrieval* inside cognition, it goes behind a
domain-owned `GraphRetriever` Protocol with Graphify as one swappable adapter
(cf. D7/D10/D12) — never a direct dependency. Do not wire that interface into
`src/` until a real consumer exists.

## D15 — Evidence identity is default-ON deduplication

The same observation re-injected (same evidence id, or the same claim
fingerprint on the same UTC day) is skipped by Beliefs, Hypotheses and
SemanticMemories through one shared `same_observation` policy. Independent
confirmations (different source, provenance, or day) still count. Production
code that models distinct world-events must carry distinguishing provenance
(action run ids, episode ids); manufacturing distinctness to evade the
policy is forbidden. See `domain/services/evidence_identity.py`.

## D16 — Snapshots never perform live network reads

The command-center snapshot reports what is wired (source/connected), never
fetches through a remote store. On-demand commands (`calendar list`, …) do
the reading. A test that wires a remote store must never stall the suite.

## D17 — One authoritative copy of runtime-tunable state

CognitiveKnobs live in the executive; the composition root reads through and
never keeps a second copy. Learned adaptations persist as LearnedState
(knobs + reason + timestamp) behind repository contracts; operator tuning
never writes there. Meta-knowledge stays derived from persisted history.

## D18 — Semantic abstraction is deterministic and offline

Semantic generalization (paraphrase/analogy/cross-domain ties and ES↔EN) is implemented as an explicit,
testable domain service over a hand-maintained bilingual concept vocabulary (stemmed + lemmatised
tokens, `CONCEPT_MAP` ES↔EN) — not an LLM call and not embeddings (D6, D8). LLMs remain perception
providers that may extract evidence behind the provider seams; they must never be smuggled into the
abstraction layer as a shortcut. The vocabulary is extended in `domain/services/abstraction.py` with
tests, never rewritten per-use. The retriever ranks every durable candidate with the one
`relatedness` scorer (D8); `SEMANTIC` is a tie-break only, never a separate scoring path (Increment 168).

## D19 — Attention priorities are derived, never stored

Attention development is a *read-side ranking*: recurrence/unresolved/revision/recency
signals are re-derived from the bounded recent episode history on every call
(`Jarvis.attention_priorities()`, `Jarvis.wake()`), bounded by a window and capped to
[0,1], so no second authoritative learning state and no unbounded score accumulation
exist. The `feel_curious()` cascade keeps its static class order; ranked attention is
a parallel honest surface, and nothing in it may mutate episode/belief state.

## D20 — Relations are retrieval context, never authority

A stored graph relation may route recall (relation-aware traversal) but may
never ground, raise, or transfer belief confidence. Poisoned or mistaken edges
surface as labelled context the same as any other memory.

## D21 — Strategy preferences are revisable routing evidence

Retrieval-strategy statistics decide which retriever surfaces candidates, not
what Jarvis concludes. A preference forms only on well-sampled, meaningful
gaps, defaults to lexical otherwise, and must always be reversible by later
counter-evidence. Flooding the record is bounded by the cap and undone by
honest use.

## D22 — Belief identity is canonical-topic-anchored

Episodes group by canonical concept signature, never by raw trigger; empty
signatures never fuse (`∅==∅` is a merge bug) and single-concept topics never
absorb. The most recent trigger survives as display-only `representative`; the
`topic_id = " > ".join(sorted(signature))` is the identity (Increment 163, refined
by topic identity v3).

## D23 — Consolidation is COMPANION-only and valence-neutral

Semantic abstraction/consolidation feeds on `COMPANION`-origin episodes only, and
valence-less episodes contribute *neutral* evidence (`Evidence.is_neutral`) that
`derive_confidence`/`derive_stability` skip and that emits neither
`SemanticMemoryReinforced` nor `Contested`. The semantic layer must never build
valence or contradiction out of episodes that carried none (Increment 164).

## D24 — Turns are context; statements are memory

`MemoryKind.CONVERSATION` entries stay surface-only candidates in recall — matched
lexically, never recited as answers. Long-term recall is what meaning should reach.
Statements cross into memory deliberately: an everyday ≥3-word non-question sentence
is stored as `USER_STATEMENT` evidence (weight 1.0, persisted; companion channel when
first-person) — turning conversation into memory is explicit, never ambient
(Increment 167).

## D25 — A changed mind resolves, never stacks

`Belief.revise()` supersedes the earlier stance, moves it into the belief's
`precedents` archive, and never recalls it as current. A corrected decision is a
first-class revision (a first-class timeline), not a new contradiction that must be
argued down. `revise_companion` applies the same rule to the companion model
(Increment 169).

## D26 — Evidence-request writing is epistemically inert

An evidence-request write is gated (COMPANION-origin, FULL-attention,
question-shaped, evidence-less), writes no evidence and no belief, and is a
transient trace so curiosity can return to an unanswered question. It must never
influence confidence, stability, or ranking (Increment 170).

## D27 — Recall is a candidate, never a belief

A `MemoryRetriever` supplies *recalled context* on the episode (never belief-evidence;
memory is not truth, Vision §22) and a *stance* (Memory / partial_memory) for the surface.
The seam is a domain Protocol with a deterministic lexical adapter as the offline default;
semantic/embedding retrieval swaps in behind the same Protocol. A question-shaped memory is
never recalled as knowledge. (Consolidated from the legacy STATUS log; Increment 172.)

## D28 — Reasoning is inference, not judgement

A `Reasoner` proposes a provisional answer as response context — never belief-evidence, never
confidence. Its output may be folded in as the *weakest* `EvidenceSource.INFERENCE` evidence
(weight 0.2, Increment 110) so an unconfirmed answer is held faintly and a later confirmation
matures it via `confirm()`. The executive is the decider (Vision §37, §38; D6). (Consolidated
from the legacy STATUS log.)

## D29 — Edge capabilities are earned and live-backed

`can_do(name)` is true only when a capability is *acquired* (a deliberate step, Vision §28) and
backed by a ready `CapabilityProvider`. Research/compare/reason/semantic-recall register providers
like the web seams, so one gate applies to every catalog capability — speech included (a silent
reasoner or lexical-only recall never reports `can_do`). (Consolidated from the legacy STATUS log.)

## D30 — Edge consultation is a deliberate, gated step

A `KnowledgeSource` edge (research → weaker `EXTERNAL_SOURCE`; compare → weakest `INFERENCE`) is
consulted only when the episode lacks real support and strong recall, at most once, and recorded in
the episode (`consulted`/`record_consult`). It gathers candidate evidence; empty/failed is honest
`None` (D6). Opt-in: an un-wired Jarvis never consults. (Consolidated from the legacy STATUS log.)

## D31 — Material-edge capabilities follow one seam

A domain Protocol at the edge + an infrastructure adapter (injectable io/net → offline tests,
env-gated root, `build_*() -> None` when unconfigured, D7/D8) + delegated `Jarvis` methods + a
`CapabilityProvider` in the registry. Calendar/tasks/notes/mail/speech/agent all follow it;
`can_do` reflects acquisition AND provider availability. (Consolidated from the legacy STATUS log.)

## D32 — Temporal stability is a distinct axis from confidence

`TemporalStability` never collapses into `Confidence` (Vision §10): both are [0,1] magnitudes but
different axes. Stability is span-based (`span / (span + reference)`, `STABILITY_REFERENCE = 30d`,
`LOW_STABILITY_THRESHOLD = 0.2`, tunable); count/recency weighting is deferred to the opt-in decay
policy. (Consolidated from the legacy STATUS log.)
