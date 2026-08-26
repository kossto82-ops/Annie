# Jarvis — Context Policy

This document explains what Claude should load, and when.

## Context tiers

### Tier 0 — always loaded

`CLAUDE.md`

Keep this file small. It contains rules, boundaries, and pointers, not the full project documentation.

### Tier 1 — normal project work

`docs/claude/AI_CONTEXT.md`

Use for orientation when the task is not obviously local.

### Tier 2 — architectural work

`docs/claude/ARCHITECTURE.md`
`docs/claude/DECISIONS.md`

Use when changing boundaries, persistence, cognition, providers, or major abstractions.

### Tier 3 — foundational/historical context

`JARVIS_VISION.md`
`STATUS.md`

Load only when the task genuinely depends on the original specification or historical reasoning.

## File selection rule

For a local code task, target this minimum set:

```text
CLAUDE.md
→ target source file
→ direct dependency if needed
→ closest test(s)
```

For an architectural task:

```text
CLAUDE.md
→ AI_CONTEXT.md
→ ARCHITECTURE.md
→ DECISIONS.md
→ only the relevant implementation files
```

For historical investigation:

```text
CLAUDE.md
→ relevant STATUS.md section
→ relevant commit/code
```

Never use the historical log as a substitute for current code.

## Large-file rule

`STATUS.md` is a historical append-only log and can become very large. Do not load it wholesale. Search for a specific increment/decision/topic first.

If a document becomes large enough to be routinely expensive, split stable knowledge from history rather than making Claude read it every time.

## Conversation rule

Do not repeatedly restate the same architecture in chat. Once the relevant document has been read, refer to it and work from it.

When summarising progress, record only durable decisions or current state; do not create a second copy of the whole implementation history.
