# Jarvis — Claude Code instructions

## Mission

Jarvis is a long-term cognitive companion, not a chatbot, LLM wrapper, RAG app, agent framework, or prompt-orchestration layer.

The core goal is to build a persistent cognitive system that develops, maintains, revises, and uses evolving models of the world, its companion, and itself.

The fundamental epistemic invariant is:

> A belief must never be stronger than the evidence supporting it.

Cognition is centred on **Cognitive Episodes**, not prompt/response pairs.

## Source of truth

Read these files only when relevant:

1. `docs/claude/AI_CONTEXT.md` — compact orientation; start here when the task needs project context.
2. `docs/claude/ARCHITECTURE.md` — current architecture and boundaries.
3. `docs/claude/DECISIONS.md` — architectural decisions that must not be casually reversed.
4. `docs/claude/DEVELOPMENT.md` — development workflow and token-efficient working rules.
5. `JARVIS_VISION.md` — foundational philosophy/specification; read only when a task touches vision, epistemology, or a major architectural decision.
6. `STATUS.md` — historical/project log. **Do not read by default.** Read only when the exact history of an increment, decision, or prior implementation matters.

`README.md` is for public/project orientation, not default implementation context.

## Token discipline

- Do NOT read the whole repository to understand a small task.
- Do NOT read `STATUS.md` unless historical context is explicitly needed.
- Do NOT read all tests before changing one module. Read the target module and its closest tests first.
- Prefer targeted search (`rg`) over opening large files.
- Before editing, identify the smallest set of files that can answer the question.
- After editing, run the narrowest relevant tests first, then the full suite only when appropriate.
- Do not reproduce large files or large code blocks in your response.
- Do not create duplicate documentation when an existing document already covers the subject.
- If a task requires broad architectural context, read `AI_CONTEXT.md` and `ARCHITECTURE.md` before expanding further.

## Architectural boundaries

- Domain cognition must remain independent of provider SDKs and network access.
- An LLM may extract candidate evidence through `PerceptionSource`; it must not become the decision-maker.
- Confidence is derived from evidence. Never add an imperative confidence setter.
- Contradictions are first-class information.
- Uncertainty must remain representable; do not collapse competing hypotheses prematurely.
- The command center is a UI/window onto the core, not a second brain.
- Keep infrastructure and external providers at the edges.
- Prefer dependency injection and protocols over hard-coded providers.
- Preserve offline, deterministic tests.

## Current priority

The architectural audit is complete (Phases 0-5, 2026-09-11). All 5 phases implemented:
- Phase 0: God Object Split (jarvis.py → 7 modules)
- Phase 1: Semantic Memory
- Phase 2: Temporal Reasoning
- Phase 3: Knowledge Graph
- Phase 4: Persistent Conversation
- Phase 5: Second-Order Reflection (Meta-Knowledge)

The refactor and maintenance pass is complete (2026-09-12):
- Phase 0: CI, MIT license, pinned deps, portable tests
- Phase 1: command_center.py split (3628→205 lines, 10 domain modules)
- Phase 2: jarvis.py split (2688→2098 lines, 4 sub-facades)
- Phase 3: Narrowed 3 except Exception patterns
- Phase 4: Python ≥3.11, ruff lint clean

1647 tests passing, ruff clean.

The current project is around Increment 160 (see `STATUS.md`). The reflective cognitive cycle is
complete; recall (lexical + semantic), provisional reasoning with a learning loop (the reasoner now
consumes the short-term `ConversationContext` **and** carries a session `ReasoningSpan` across turns for
deep multi-turn reasoning), memory decay, hypothesis temporal-stability narration (Increment 146),
beliefs and hypothesis sets sharing one `CognitiveEpisode` shape (Increment 147), record documented
document ownership (Increment 148), chat editing of documents behind a `DocumentEditor` proposal seam
(Increment 149), a real SQLite database behind the repository contracts via `Jarvis.database()` (D10,
Increment 150) extended across the calendar/notes/tasks edge seams (Increment 151) and the
decision-provenance trace (Increment 152; `Jarvis.database()` leaves no memory surface file-backed). A
fully opt-in pydantic-ai provider landed in Increment 153 behind the `LanguageModel`, `TaskAgent` and
reasoner seams — model adapter + structured perception, a model-driven task agent that runs decided
tool loops (delegation behind the seam, cognition in the core), per-call usage accounting, a
tool-registry fallback on provider failure, and reasoner-level streaming (`Jarvis.reason_stream`
records the reasoning span only on a completed stream) — a live speech-to-text backer
landed behind the speech seam in Increment 154 (a Whisper-compatible ear chosen via `JARVIS_STT_*`,
`Jarvis.transcribe(audio)`, and `POST /api/speech/transcribe`, beside the browser Web Speech default) —
and
the capability edges (web/research/compare/tools/notes/mail/calendar/tasks/agent/speech seam) are
implemented. Files/documents
are a first-class surface (accept, recall, search, chip in chat, read, folder-aware nesting). The command
center exists with voice, a sphere/face, streaming, a reasoning panel, live-tunable cognition thresholds,
a root-injectable per-belief weighting policy, a capability/tool surface, and a deliberate attention
router (Increment 155: `DeliberationValue` routes `think`/`consider` depth by how much a problem is
worth, deliberations charge energy, and a `deliberation` command-center command sets the default
stance); live-provider instrumentation (Increment 156: `InstrumentedLanguageModel`/
`InstrumentedTaskAgent` wrappers feed a shared `InstrumentationStore`, surfaced as `Jarvis.provider_stats()`
and the command center's `provider` snapshot block — bookkeeping only); provider guardrails
(Increment 157: a refusal — `finish_reason='content_filter'` or decline text, EN/ES — becomes honest
silence `""` via `guardrail.py`, wired into both live adapters' `complete`/`stream`, §37's second
enforcement point beside the failure path); the MCP client direction
(Increment 158: a live MCP server's tools land in the same gated `ToolRegistry` as `EXTERNAL_ACTION`
`ToolSpec`s via a sync `McpTransport` seam + lazy `PydanticAiMcpToolset`, wired from `JARVIS_MCP_CONFIG`
inside `build_sandboxed_registry`); and the live STT level-2 console use
(Increment 159: the console mic uses that ear — when `JARVIS_STT_*` wires a Whisper-class backer,
push-to-talk records with `getUserMedia`/`MediaRecorder` and POSTs to `/api/speech/transcribe`, and
the ear seam self-describes via `provider`/`model`/`can_hear_audio`; the snapshot's `speech` block
tells the browser which path to take, Web Speech staying the offline default); and real instruction
execution (Increment 160: a material directive — "escribe un archivo", "run the tests" — classifies
as `ConversationIntent.ACT` and is *performed* through a new earned-agency seam,
`Jarvis.execute`/`instruction_agent`, wired by `build_instruction_agent` to the same sandboxed
`ToolRegistry` but at `approved=False` — sandbox reads/writes run, external (MCP)/destructive acts
refuse honestly at the gate, and the chat reply narrates the real outcome ("Listo — …" / "No pude
completarlo: …") or an honest decline when no executor is wired). A live LLM provider is
opt-in and must remain provider-swappable and offline-testable. Audit gates are clean at HEAD
(ruff · pyright strict 0 errors).

The pydantic-ai provider thread is complete in its shipped parts: the opt-in implementation behind the
LLM/agent/reasoner
seams shipped in Increment 153 and stays
gated — future live providers should implement the same seams, never a second bypass. The live-STT thread
is complete too (Increment 154 backend, Increment 159 console use), and earned-agency execution
(Increment 160) extends the same `TaskAgent` seam rather than adding a new abstraction —
the instruction executor is the delegated agent at `approved=False`.
Instrumentation landed as Increment 156 (pydantic-ai Phase 4, part 1);
provider guardrails as Increment 157 (Phase 4, part 2a); the MCP adapter (client direction — external
toolsets into the `ToolRegistry` as `ToolSpec`s) as Increment 158 (Phase 4, part 2b). The pydantic-ai
Phase 4 thread is therefore finished in both its shipped parts and its client direction.
However,
**do not assume any thread is mandatory**: follow the user's current
task.

## How to work

1. Inspect only the relevant files.
2. State the implementation plan briefly if the task is non-trivial.
3. Make the smallest coherent change.
4. Add/update focused tests.
5. Run focused checks.
6. Report changed files, tests run, and any uncertainty.
7. Do not make unrelated refactors.

## Safety against architectural drift

Before introducing a new abstraction, ask whether the existing domain model already provides the required concept.

Do not create a generic `manager`, `engine`, `orchestrator`, `AI layer`, or wrapper merely to make a feature easier to implement. New abstractions must have a clear domain or infrastructure responsibility.
