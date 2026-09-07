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

The current project is around Increment 145 (see `STATUS.md`). The reflective cognitive cycle is
complete; recall (lexical + semantic), provisional reasoning with a learning loop (the reasoner now
consumes the short-term `ConversationContext` **and** carries a session `ReasoningSpan` across turns for
deep multi-turn reasoning), memory decay, and the capability edges
(web/research/compare/tools/notes/mail/calendar/tasks/agent/speech seam) are implemented. Files/documents
are a first-class surface (accept, recall, search, chip in chat, read, folder-aware nesting). The command
center exists with voice, a sphere/face, streaming, a reasoning panel, live-tunable cognition thresholds,
a root-injectable per-belief weighting policy, and a capability/tool surface; a live LLM provider is
opt-in and must remain provider-swappable and offline-testable. Audit gates are clean at HEAD
(ruff · pyright strict 0 errors).

The most useful next increments currently identified are `TemporalStability` for hypotheses (beliefs-only
today), unifying the two `CognitiveEpisode` shapes, or document depth (ownership, per-file ranking,
editing via chat). However, **do not assume this is mandatory**: follow the user's current task.

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
