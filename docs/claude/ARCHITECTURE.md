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
                    │ Capabilities (Odysseus)      │
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

## Odysseus (capability acquisition)

Odysseus is the mechanism by which Jarvis recognises and grows new *capabilities* --
extensions of its ability to act (Vision §34). Phase 1 delivered the core model + scout
(discovery); Phase 2 grounds recognition in evidence and wires acquisition into curiosity
and the surfaces; Phase 3 put the *live* capability at the edge behind a provider registry;
Phase 4 added the self-initiated half: Jarvis noticing recurring subjects it failed to
answer, as the seed of a need.

The flow:

```text
recognise_need  (a need becomes a belief, confidence derived from evidence, §8)
        ↓
capability_scout
        ↓
Capability proposals (PROPOSED), persisted
        ↓
capability_evaluator  (derived stance: suggest / ask first / withhold, §28)
        ↓
feel_curious → pursue  (a confident unmet need raises an acquisition impulse)
        ↓
acquire or reject (deliberate; autonomy is earned, Vision §28)

(Phase 4) observe_capability_gaps → detect_capability_gaps
        ↓
unanswered_subjects  (recurring failure subjects from the episode history)
        ↓
capability notice (Command Center): recognise_need with grounded evidence from those
episodes → scout proposes how to answer better
```

Boundaries:

- The scout is an evidence *producer* only: it pairs a need with plausible candidates from
  a deterministic catalog (keyword-matched capability templates). It decides nothing
  (Vision §32).
- A ``Capability`` is bookkeeping of what Jarvis *can* do; the capability itself is always an
  injectable, provider-agnostic capability at the edge (D7). No cognition lives inside a
  capability.
- A recognised need is an ordinary *belief* (``"I need the ability to …"``) whose confidence
  is derived from evidence (Vision §8) -- never asserted. ``capability_evaluator.recommend``
  mirrors ``action_advisor`` (Vision §28): it *suggests* acquisition only when the need is
  confident and the capability is not yet held; it withholds when contracted; otherwise it
  asks first. It only recommends, it acquires nothing.
- Acquiring (`CapabilityStatus.ACQUIRED`) and rejecting (`REJECTED`) are deliberate, separate
  steps -- autonomy is earned (Vision §28).
- Curiosity closes the loop: a confidently-needed, unavailable capability raises a
  ``CuriosityImpulse`` naming it, and ``pursue`` marks it acquired (so growth is both earned
  and acted on). ``state_summary`` and the Command Center ``capability`` command expose
  capabilities and needs.
- Gap detection (Phase 4) is read-only observation: `capability_gap_observation.detect`
  clusters the episode history by shared subject words and reports each subject Jarvis
  concluded about *ungrounded* more than once (`observe_capability_gaps` /
  `unanswered_subjects`). It only *detects*: turning a gap into an evidence-grounded need
  is the surface's job — the Command Center ``capability notice`` action records it via
  ``recognise_need``, so the need's confidence is derived from the failed episodes, never
  asserted. Like the scout, this is shallow keyword matching (D11), deliberately.
- A ``Capability`` is *bookkeeping*; the *live* side is a ``CapabilityProvider`` at the edge
  (D7) -- a registry (`capability_registry.StaticCapabilityRegistry`) maps a capability name
  to the concrete adapter that serves it. `Jarvis.can_do(name)` is true only when a
  capability is *both* acquired and live-backed, so acquisition is real, not decorative: the
  Internet command (`external` read/search) now requires the matching capability to be
  earned, and the persistent edge (agent-reach) backs "search the web"/"read external
  documents" by default.

Storage: `CapabilityRepository` and the need beliefs (`BeliefRepository`) are domain Protocols
with in-memory and JSON stores, wired into `Jarvis.persistent()` as `capabilities.json` and
`needs.json` so acquisitions and recognised needs survive a restart.

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
