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

## D11 — Exact matching is currently deliberate

Belief/connection identity currently relies on exact strings in places. Semantic matching is a future enhancement, not something to sneak into a small feature.

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
