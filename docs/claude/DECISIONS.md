# Jarvis — Architectural Decisions

This file is intentionally short. It contains decisions Claude should treat as constraints unless the user explicitly asks to revisit them.

## D1 — Jarvis is not an agent wrapper

Do not introduce an outer autonomous-agent framework that calls Jarvis methods to simulate cognition. The reflective cycle belongs inside Jarvis's core.

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
