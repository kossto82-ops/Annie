# Jarvis

A long-term **cognitive companion** — not a chatbot, not an LLM wrapper.

Jarvis is being built as a persistent cognitive system that develops, maintains, revises
and uses an evolving model of the world, its companion, and itself. Its unit of thought is
a **cognitive episode**, not a prompt→response. Its knowledge is grounded in **evidence**,
and its core epistemic rule is absolute:

> A belief must never be stronger than the evidence supporting it.

Beliefs are provisional, confidence is *derived* from evidence (never asserted), contradictions
are first-class facts, and understanding accumulates across episodes. The full intent lives in
[`JARVIS_VISION.md`](JARVIS_VISION.md); the current build state and decision log live in
[`STATUS.md`](STATUS.md).

## What works today

```python
from jarvis import Jarvis
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.enums.evidence_source import EvidenceSource

j = Jarvis()
q = "Does my companion prefer simplicity?"

# No evidence -> an honest non-conclusion, not a fabricated answer:
j.think(q).result
#   "Insufficient evidence to conclude about: ... (confidence 0.00)."

# Evidence accumulates across episodes; confidence rises with experience:
j.think(q, evidence=[Evidence(content="chose the simpler design",
                              source=EvidenceSource.USER_STATEMENT,
                              weight=Confidence(0.9))])
ep = j.think(q, evidence=[Evidence(content="said: I do not want another assistant",
                                   source=EvidenceSource.USER_STATEMENT,
                                   weight=Confidence(0.8))])
ep.result                       # "Concluded ... grounded in N piece(s) of evidence."
ep.working_belief.explain()     # provenance: *why* it concluded
```

The decision genuinely depends on the epistemology — the same question yields *insufficient*,
*tentative*, or *grounded* conclusions purely as a function of evidence. No LLM is involved.

## Architecture (current)

```
trigger (+ evidence)
  -> CognitiveEpisode        # the unit of cognition; owns a working Belief
  -> ExecutiveController     # thin orchestrator, not a God Object
  -> NervousSystem           # decoupled event signalling (subscribe/publish/dispatch)
  -> Belief                  # confidence DERIVED from Evidence, never assigned
  -> BeliefRepository        # beliefs persist and evolve across episodes (continuity)
```

- **Value objects:** `Confidence` (validated [0,1]), `Evidence` (weighted, supports/contradicts).
- **Entities:** `Belief`, `Hypothesis` (evidence-derived confidence).
- **Aggregates:** `CognitiveEpisode`, `HypothesisSet` (competing explanations, no premature collapse).
- **Events:** immutable cognitive events (`EpisodeStarted`, `EvidenceAdded`, `BeliefStrengthened/Weakened`,
  `ContradictionDetected`, `HypothesisCreated`, ...).
- **Infrastructure:** `InMemoryBeliefStore`.

## Vocabulary

Everything Jarvis can do, by cognitive role. All in-memory by default; wire durable JSON stores per
store, or use `Jarvis.persistent(directory)` for full cross-restart continuity.

**Construct**
- `Jarvis()` — ephemeral (in-memory).
- `Jarvis.persistent(directory)` — all memory (beliefs, episodes, companion, actions, reversibility, goals) on disk under one dir.

**Perceive**
- `perceive(observation, trigger=None, goal=None)` — turn a raw observation into evidence (via the injected `PerceptionSource`) and reason over it; unknown input yields honest silence.
- `perceive_all(observations, trigger=None, goal=None)` — perceive a whole stream at once; a multi-line exchange grounds one belief from all of it.
- `perceive_about_companion(trait, observation)` / `perceive_all_about_companion(trait, observations)` — perceive utterance(s) about the companion and fold them into the lasting companion model.
- `ask_about(topic)` / `resolve(topic, guidance, supports=True)` — voice a contested belief ("I've heard both X and not-X — which is it?") and fold the companion's answer back in as evidence.
- `Jarvis(perception=…)` — inject any `PerceptionSource` (a dumb keyword rule by default; an LLM-backed perceiver is a drop-in behind the same Protocol).

**Reason**
- `think(trigger, evidence=(), goal=None)` — run a cognitive episode toward one grounded conclusion, optionally *toward* a `Goal`; returns the episode.
- `consider(observation, options)` — weigh competing explanations (`{statement: [evidence, ...]}`); returns a `Deliberation`.

**Act & learn**
- `act(description, expected, *, confidence=None, reversible=True)` — declare an intention (no side effect).
- `record_outcome(action, actual, met_expectation)` — learn from expected-vs-actual; returns the action-outcome belief.
- `belief_about_action(description)` — what Jarvis has learned about that kind of action.
- `recommend_action(action)` — a graded stance (SUGGEST / ASK_FIRST / WITHHOLD); recommends, never acts.

**Model of itself**
- `observe_self()`, `observe_overconfidence()`, `observe_prediction_accuracy()` — one self-tendency each, or None.
- `self_beliefs()` — every self-tendency it has enough history to judge.
- `feel_curious()` — an impulse to reduce the most confident weakness, or None.
- `pursue(impulse)` — run the self-triggered corrective episode.
- `introspect()` — a plain-language account of who it is, from real state.
- `state_summary()` — a compact, immutable snapshot of everything it currently holds.

**Model of its companion**
- `observe_companion(trait, evidence)` — evolve a belief about the companion.
- `explain_companion(trait)` — why it believes that (evidence, confidence, "I may be wrong"), or "no view yet".
- `companion.belief_about(trait)` / `companion.beliefs()` / `companion.summarise()`.

**Goals & relationship**
- `recurring_goals()` — the goals it keeps returning to, as `(goal, count)` (most-returned-to first).
- `mark_goal_reached(goal, reached=True)` — learn whether a goal of this kind is reachable; `belief_about_goal(goal)` reads it back. A `Goal` may name a larger goal it is `part_of`.
- `sub_goals(parent)` / `goal_progress(parent)` — a decomposed goal's recorded parts and `(parts reached, parts known)`.
- `reflection_effort(goal_statement)` — how many times it has wondered about a goal on its own initiative.
- `stuck_goals()` — goals it has given up wondering about alone (learned unreachable *and* reflected on to exhaustion).
- `ask_for_help()` — a spoken request for help with the most stuck goal, naming the blocking part (warmer once the companion has proven helpful), or None.
- `receive_help(goal, helpful=True)` — take the companion's guidance in as evidence; it can lift a stuck goal, advance its blocking part, and teaches that the companion is helpful.

**Reflect (the cognitive cycle)** — Remember → Connect → Reflect → Hypothesise → Challenge → Learn, self-triggered by curiosity.
- `connections()` / `related_beliefs(trigger)` — beliefs linked by the evidence they share.
- `reflect()` — load-bearing observations several beliefs rest on.
- `hypothesise()` — a common-cause `HypothesisSet` brewed from the top reflection.
- `challenge()` — the concrete falsifier of the leading hypothesis; `refute(observation, belief)` dethrones it.
- `learn_from_reflection()` — adopt a surviving insight as a belief (the loop closes).
- `reflect_cycle()` — run the whole cycle once; `feel_curious()` raises a reflect impulse on an un-mined pattern.

**Memory & provenance**
- `episodes.history()` — past episodes (conclusions and deliberations).
- `trace_of(episode)` / `trace(correlation_id)` — the ordered event trace of one act of cognition.

Runnable end-to-end tours live in [`examples/main_loop.py`](examples/main_loop.py) (the core loop),
[`examples/goal_arc.py`](examples/goal_arc.py) (the goal → stuck → ask-for-help → help-received arc),
[`examples/goal_parts.py`](examples/goal_parts.py) (a goal made of parts, worked one blocker at a time),
[`examples/perceiving.py`](examples/perceiving.py) (language in, evidence-grounded cognition out),
[`examples/conversation.py`](examples/conversation.py) (a multi-line exchange grounds a belief that strengthens across a restart),
[`examples/resolving.py`](examples/resolving.py) (hear a contradiction → get curious → ask → resolve),
and [`examples/reflecting.py`](examples/reflecting.py) (Jarvis notices a pattern in its own beliefs, reflects, hypothesises, challenges, and learns — unprompted).

## Development

Requires Python 3.13+.

```bash
python -m pytest -q        # tests
python -m ruff check .     # lint
python -m pyright          # type check (strict)
```

Built incrementally: the smallest correct system first, then evolved — every step preserving the
path to the vision. See [`STATUS.md`](STATUS.md) for the increment log and settled decisions.
