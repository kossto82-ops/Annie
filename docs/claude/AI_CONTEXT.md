# Jarvis — AI Context

## What Jarvis is

Jarvis is a long-term cognitive companion. It is a persistent cognitive system whose primary unit is a **Cognitive Episode** rather than a chat turn.

The intended loop is:

`Experience → Perception → Interpretation → Attention → Memory → Reasoning → Reflection → Decision → Action → Outcome → Learning → Updated state`

The response is only one possible output of cognition.

## Non-negotiable principles

- Beliefs are provisional.
- Evidence is first-class and carries provenance/source/weight.
- Confidence is **derived**, never manually assigned to a belief.
- Contradictions are explicit.
- Competing hypotheses can coexist.
- Uncertainty must not be hidden by premature conclusions.
- Memory preserves evidence and state; memory is not truth.
- The LLM, when present, extracts candidate evidence; the core remains the judge.
- Providers must be swappable.
- Core tests must remain deterministic/offline.
- The system should grow through evidence and experience, not through increasingly large prompts.

## Current system

### Domain

- `CognitiveEpisode` — aggregate root and unit of cognition.
- `Belief` — evidence-grounded entity.
- `Hypothesis` / `HypothesisSet` — competing explanations.
- `CompanionModel` — model of the companion.
- Value objects cover evidence, confidence, temporal stability, goals, actions, deliberation, reflection, energy, connections, state summaries, etc.
- Domain events represent episode, evidence, belief, contradiction, and hypothesis changes.

### Cognitive services

Important services include:

- evidence weighting
- reflection
- connection/association
- curiosity
- hypothesis generation
- action recommendation
- goal reflection
- self-observation

### Executive/core

`ExecutiveController` orchestrates the lifecycle of an episode. It should remain thin.

`Jarvis` is the public composition/API surface.

`NervousSystem` provides synchronous event signalling.

### Memory

Repositories are defined in the domain and implemented by infrastructure.

Both in-memory and JSON-backed stores exist. `Jarvis.persistent(directory)` wires durable JSON persistence.

There is no real database yet.

### Perception / LLM

`PerceptionSource` is the abstraction from observation to evidence.

Current implementations include a deterministic keyword perceiver and an LLM-backed seam.

`LanguageModel` is provider-agnostic. `LlmPerception` uses it to extract candidate evidence, not to decide beliefs.

`OpenAiCompatibleModel` and the provider registry support multiple remote and local endpoints, including Ollama/LM Studio style endpoints.

A live API call must remain opt-in. Secrets belong in environment/configuration, never source control.

### Command Center

The command center is a local browser UI served by the stdlib HTTP server.

The browser handles voice input/output and the visual face. Python remains the cognitive core.

`handle`, `route`, and `snapshot` are intended to be pure/socket-free and tested independently from the server.

## Reflective cycle

The implemented autonomous reflective cycle is:

`Remember → Connect → Reflect → Hypothesise → Challenge → Learn → Act`

The cycle is evidence-grounded, revisable, auditable, and implemented inside the core rather than as an external agent wrapper.

Curiosity can trigger the cycle.

## Current state snapshot

- Reflective cycle: implemented.
- Curiosity/self-triggering: implemented.
- Episodic, belief, companion, action and goal memory: implemented.
- Persistence: implemented through JSON stores.
- Cognitive energy/fatigue budget: implemented at the current basic level.
- LLM abstraction/registry: implemented.
- Live provider integration: still opt-in / not the default.
- Command Center: implemented.
- Speech mouth synchronisation: implemented.
- Reasoning/provenance visualisation: a strong next refinement, not a permanent requirement.

## Known technical debt / future directions

- Persisting event traces.
- Possible real DB behind repository interfaces.
- Semantic matching instead of exact-string identity.
- More sophisticated temporal weighting.
- Injectable weighting policy at the Jarvis level.
- Further cognitive-energy modelling.
- Unification/documentation of conclusion vs deliberation episode shapes.
- More configurable runtime parameters.

Do not turn every future direction into immediate work. Follow the current user request.
