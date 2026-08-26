# Jarvis — Architecture

## Layering

```text
                    ┌─────────────────────────────┐
                    │ Interface / Command Center  │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │ Public API / Jarvis         │
                    │ ExecutiveController         │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │ Domain / Cognition          │
                    │ Episodes                    │
                    │ Beliefs / Hypotheses        │
                    │ Reflection / Curiosity      │
                    │ Goals / Actions              │
                    │ Domain Events                │
                    └──────────────┬──────────────┘
                                   │ protocols
                                   ▼
                    ┌─────────────────────────────┐
                    │ Infrastructure              │
                    │ JSON / memory stores        │
                    │ Perception                  │
                    │ Language models             │
                    │ Provider registry           │
                    └─────────────────────────────┘
```

## Repository map

```text
src/jarvis/
├── jarvis.py
├── domain/
│   ├── aggregates/
│   ├── entities/
│   ├── enums/
│   ├── events/
│   ├── perception/
│   ├── repositories/
│   ├── services/
│   └── value_objects/
├── executive/
├── infrastructure/
├── interface/
├── nervous_system/
└── observability/
```

## Responsibility rules

### Domain

Owns meaning, invariants, cognitive state, evidence, beliefs, hypotheses, and domain events.

The domain must not import provider SDKs, HTTP clients, browser code, or environment-specific infrastructure.

### Executive

Coordinates domain collaborators for a cognitive episode. It should not become a second domain model or a generic workflow engine.

### Infrastructure

Implements repository/perception/model protocols and handles persistence, environment settings, network/provider details.

### Interface

Translates user/UI input into calls to the public API and renders returned state. It must not invent cognition.

### Observability

Makes cognitive activity inspectable without changing the cognitive decision itself.

## Cognitive flow

A normal reasoning episode is conceptually:

```text
trigger + evidence
       ↓
CognitiveEpisode
       ↓
retrieve/adopt existing belief if present
       ↓
observe evidence
       ↓
derive confidence/stability
       ↓
ExecutiveController chooses lifecycle decision
       ↓
persist updated belief + episode
       ↓
publish domain events
```

The reflective flow is:

```text
Remember
   ↓
Connect
   ↓
Reflect
   ↓
Hypothesise
   ↓
Challenge
   ↓
Learn
   ↓
Act / recommend verification
```

## LLM boundary

```text
raw observation
      ↓
PerceptionSource
      ↓
LanguageModel (optional)
      ↓
candidate Evidence
      ↓
Domain cognition
      ↓
Belief / hypothesis / decision
```

The model must not directly set belief confidence or make the core decision.

## Persistence boundary

Repositories belong to the domain as protocols. JSON/in-memory stores belong to infrastructure.

A future database should implement the same repository contracts rather than moving database concepts into the domain.

## UI boundary

The Command Center is a window onto Jarvis. If a UI feature requires new cognitive behaviour, implement that behaviour in the core first; do not hide cognition in JavaScript or HTTP handlers.
