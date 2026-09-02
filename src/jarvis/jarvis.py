"""The Jarvis entry point.

``Jarvis.think(trigger)`` runs a complete cognitive lifecycle over a trigger and
returns the resulting episode. The nervous system is exposed so callers can
subscribe to cognitive events *before* thinking begins.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from jarvis.domain.aggregates.cognitive_episode import CognitiveEpisode
from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.aggregates.hypothesis_set import HypothesisSet
from jarvis.domain.conversation.conversation_context import ConversationContext, Turn
from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.capability_stance import CapabilityStance
from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.events.action_events import ActionOutcomeRecorded
from jarvis.domain.events.belief_events import ContradictionDetected
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.perception.companion_perception import CompanionPerceptionSource
from jarvis.domain.perception.perception_source import PerceptionSource
from jarvis.domain.reasoning.reasoner import Reasoner
from jarvis.domain.repositories.belief_repository import BeliefRepository
from jarvis.domain.repositories.capability_repository import CapabilityRepository
from jarvis.domain.repositories.episode_repository import EpisodeRepository
from jarvis.domain.repositories.refutation_repository import RefutationRepository
from jarvis.domain.retrieval.external_source import ChannelStatus, ExternalSource
from jarvis.domain.retrieval.memory_retriever import MemoryRetriever
from jarvis.domain.services.action_advisor import recommend as recommend_stance
from jarvis.domain.services.association import find_connections
from jarvis.domain.services.capability_evaluator import recommend as recommend_capability
from jarvis.domain.services.capability_gap_observation import (
    CapabilityGap,
    detect_capability_gaps,
)
from jarvis.domain.services.capability_scout import scout
from jarvis.domain.services.curiosity import wonder
from jarvis.domain.services.evidence_weighting import EvidenceWeightingPolicy
from jarvis.domain.services.goal_reflection import recurring_goals, reflection_effort
from jarvis.domain.services.hypothesis_generation import generate_hypotheses
from jarvis.domain.services.reflection import find_reflections
from jarvis.domain.services.self_observation import (
    observe_evidence_habit,
    observe_overconfidence,
    observe_prediction_accuracy,
)
from jarvis.domain.value_objects.action import Action
from jarvis.domain.value_objects.action_recommendation import ActionRecommendation
from jarvis.domain.value_objects.capability import Capability
from jarvis.domain.value_objects.capability_need import CapabilityNeed
from jarvis.domain.value_objects.capability_recommendation import CapabilityRecommendation
from jarvis.domain.value_objects.challenge import Challenge
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.connection import Connection
from jarvis.domain.value_objects.curiosity_impulse import CuriosityImpulse
from jarvis.domain.value_objects.deliberation import Deliberation
from jarvis.domain.value_objects.energy_costs import EnergyCosts
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.goal import Goal
from jarvis.domain.value_objects.inference import Inference
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.domain.value_objects.reflection import Reflection
from jarvis.domain.value_objects.reflective_cycle import ReflectiveCycle
from jarvis.domain.value_objects.retrieved_document import RetrievedDocument
from jarvis.domain.value_objects.state_summary import LearnedAction, StateSummary
from jarvis.executive.executive_controller import (
    ExecutiveController,
    subject_of,
    working_statement,
)
from jarvis.infrastructure.agent_reach_source import build_agent_reach_source
from jarvis.infrastructure.capability_registry import (
    CapabilityRegistry,
    build_default_registry,
)
from jarvis.infrastructure.embedding_memory_retriever import EmbeddingMemoryRetriever
from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore
from jarvis.infrastructure.in_memory_capability_store import InMemoryCapabilityStore
from jarvis.infrastructure.in_memory_episode_store import InMemoryEpisodeStore
from jarvis.infrastructure.in_memory_refutation_store import InMemoryRefutationStore
from jarvis.infrastructure.json_belief_store import JsonBeliefStore
from jarvis.infrastructure.json_capability_store import JsonCapabilityStore
from jarvis.infrastructure.json_episode_store import JsonEpisodeStore
from jarvis.infrastructure.json_episode_trace import JsonEpisodeTrace
from jarvis.infrastructure.json_refutation_store import JsonRefutationStore
from jarvis.infrastructure.keyword_perception import KeywordPerception
from jarvis.infrastructure.lexical_memory_retriever import LexicalMemoryRetriever
from jarvis.infrastructure.response_renderer import IdentityRenderer, ResponseRenderer
from jarvis.infrastructure.silent_companion_perception import SilentCompanionPerception
from jarvis.infrastructure.text_embedder import TextEmbedder
from jarvis.nervous_system.nervous_system import NervousSystem
from jarvis.observability.episode_trace import EpisodeTrace, EpisodeTraceSink

# Once Jarvis has turned an unreached goal over this many times without its
# reachability improving, it stops wondering about it *for now* (Vision §16, §28):
# an honest companion knows when to stop banging on a stuck door. This is "not
# right now", not "never" -- reaching the goal or a fresh recurrence resurfaces it.
_MAX_GOAL_REFLECTIONS = 3

# The companion trait Jarvis learns about from help it received on a stuck goal.
HELPFUL_COMPANION_TRAIT = "is helpful when I am stuck"

# A reflective hypothesis is adopted as a belief only once it leads this confidently
# (mirrors the grounded threshold, D14) and has survived challenge.
_INSIGHT_CONFIDENCE = 0.5

# The internal identity prefix for a capability need belief (Odysseus). It
# distinguishes a need from other belief kinds and keeps retrieval deterministic
# (D17) -- but it is machine bookkeeping, never shown to the companion.
_NEED_PREFIX = "I need the ability to: "


class Jarvis:
    """A long-term cognitive companion (first vertical slice)."""

    def __init__(
        self,
        nervous_system: NervousSystem | None = None,
        beliefs: BeliefRepository | None = None,
        episodes: EpisodeRepository | None = None,
        companion_store: BeliefRepository | None = None,
        actions_store: BeliefRepository | None = None,
        reversibility_store: BeliefRepository | None = None,
        goals_store: BeliefRepository | None = None,
        subgoals_store: BeliefRepository | None = None,
        capabilities_store: CapabilityRepository | None = None,
        needs_store: BeliefRepository | None = None,
        perception: PerceptionSource | None = None,
        companion_perception: CompanionPerceptionSource | None = None,
        refutations_store: RefutationRepository | None = None,
        energy_costs: EnergyCosts | None = None,
        energy_budget: int | None = None,
        enable_recall: bool = False,
        reasoner: Reasoner | None = None,
        trace: EpisodeTraceSink | None = None,
        weighting_policy: EvidenceWeightingPolicy | None = None,
        external_source: ExternalSource | None = None,
        capability_providers: CapabilityRegistry | None = None,
    ) -> None:
        self.nervous_system = nervous_system or NervousSystem()
        self.beliefs: BeliefRepository = beliefs or InMemoryBeliefStore()
        self.episodes: EpisodeRepository = episodes or InMemoryEpisodeStore()
        self.companion = CompanionModel(companion_store or InMemoryBeliefStore())
        self.actions: BeliefRepository = actions_store or InMemoryBeliefStore()
        self._reversibility: BeliefRepository = (
            reversibility_store or InMemoryBeliefStore()
        )
        self._goals: BeliefRepository = goals_store or InMemoryBeliefStore()
        self._subgoals: BeliefRepository = subgoals_store or InMemoryBeliefStore()
        # Odysseus (capability acquisition): candidate and acquired capabilities.
        # In-memory by default; a durable JSON store is wired by `persistent()` so
        # proposed/acquired capabilities survive a restart.
        self._capabilities: CapabilityRepository = (
            capabilities_store or InMemoryCapabilityStore()
        )
        # The *needs* behind capability acquisition (Odysseus). A need is an ordinary
        # belief ("I need the ability to …") whose confidence is derived from evidence
        # (Vision §3, §8), so whether to acquire a capability is earned, not asserted.
        self._needs: BeliefRepository = needs_store or InMemoryBeliefStore()
        self._perception: PerceptionSource = perception or KeywordPerception()
        # The relational channel (Vision §5): reads what the companion says into
        # observations about *them*. Silent by default (needs an LLM to read free
        # utterances into traits); swappable at runtime like the world perceiver.
        self._companion_perception: CompanionPerceptionSource = (
            companion_perception or SilentCompanionPerception()
        )
        # Presentation only (Vision §40, §38): voices a decided reply in the companion's
        # language. Rides on the session object for the surface to use; the cognitive
        # core never calls it. Identity by default -> the canonical reply, unchanged.
        self._voice: ResponseRenderer = IdentityRenderer()
        # The Internet capability (Vision §38): fetches *external* information
        # (search/read) when Jarvis decides it needs updated outside knowledge. It is
        # None by default -> offline, so a bare Jarvis never reaches the network. It
        # only retrieves documents with provenance; the core still interprets and
        # reasons over them.
        self._external_source: ExternalSource | None = external_source
        # The live edge of Odysseus (D7): which acquired capability names are backed
        # by a real provider. When no registry is given, the wired ExternalSource
        # backs the web capabilities by default; None with no source -> offline.
        self._external_providers_auto = capability_providers is None
        if capability_providers is not None:
            self._capability_providers: CapabilityRegistry | None = capability_providers
        else:
            self._capability_providers = build_default_registry(external_source)
        # (observation, belief statement) pairs Challenge has refuted -- the belief
        # would hold without the observation, so it no longer rests on it (Incr 77).
        self._refutations: RefutationRepository = (
            refutations_store or InMemoryRefutationStore()
        )
        # Cognitive energy (Vision §15): each episode costs by its attention level.
        # Configurable so a later command center can tune it; only made *visible*
        # here (accumulated), not yet a budget that constrains attention.
        self._energy_costs = energy_costs or EnergyCosts()
        self._energy_spent = 0
        # An optional current-capacity budget (Vision §15): when it runs low Jarvis
        # conserves -- answering briefly rather than running the full lifecycle --
        # and recovers on `rest()`. Config-driven (Track E). None = no budget, so
        # behaviour is identical to before. Distinct from the cumulative tally above.
        self._energy_budget = energy_budget
        self._energy_available = energy_budget if energy_budget is not None else 0
        # Decision provenance (Vision §26). In-memory by default; a durable JSON-backed
        # sink is injected by `persistent()` so the trace survives a restart.
        self._trace: EpisodeTraceSink = trace or EpisodeTrace()
        self.nervous_system.subscribe(CognitiveEvent, self._trace.handle)
        # Optional long-term-memory recall (Vision §3): when enabled, a deterministic
        # lexical retriever over Jarvis's own stores lets an episode answer from what
        # it remembers instead of a blank "insufficient evidence". Off by default, so
        # the offline core is unchanged (D8); the command center turns it on. A
        # semantic retriever can replace it behind the same Protocol later (D11).
        memory_retriever: MemoryRetriever | None = (
            LexicalMemoryRetriever(
                self.beliefs, self.episodes, self.companion, self._goals
            )
            if enable_recall
            else None
        )
        # How working beliefs weigh evidence (Vision §10, §22). None -> the default
        # (no decay); a DecayingWeightingPolicy makes stale evidence fade over time.
        self._weighting_policy = weighting_policy
        # Short-term conversational context (Vision §3): the last few turns of THIS
        # conversation, kept separate from long-term memory so follow-ups and pronouns
        # resolve against what was just said, not against the belief store.
        self.conversation = ConversationContext()
        self._executive = ExecutiveController(
            self.nervous_system,
            self.beliefs,
            self.episodes,
            self.companion,
            memory_retriever,
            reasoner,
            weighting_policy,
        )

    def set_reasoner(self, reasoner: Reasoner | None) -> None:
        """Swap the reasoner at runtime (Vision §37, §38; Track B).

        Like the perceiver and voice, the reasoning capability is config: switching
        provider from the command center updates it too, so a provisional answer comes
        from the same model that perceives and voices. ``None`` disables reasoning.
        """
        self._executive.set_reasoner(reasoner)

    def reason(
        self,
        query: str,
        *,
        memory: tuple[RecalledMemory, ...] = (),
        conversation: tuple[Turn, ...] = (),
    ) -> Inference | None:
        """Ask the configured reasoner without creating an episode or belief.

        This is the conversation-first read path: recent dialogue and recalled memory
        may inform a response, but reasoning alone writes nothing to long-term memory.
        """
        return self._executive.reason(query, memory=memory, conversation=conversation)

    def recall(self, query: str) -> tuple[RecalledMemory, ...]:
        """Retrieve relevant long-term context without creating an episode or belief."""
        return self._executive.recall(query)

    def enable_embedding_recall(self, embedder: TextEmbedder) -> None:
        """Upgrade recall from surface tokens to *meaning* (Vision §3, D11).

        Installs an embedding-backed retriever over Jarvis's own stores, with a lexical
        retriever as its fallback so a local embedder outage degrades to token recall
        rather than none (Vision §37). The retriever only surfaces candidates; the
        executive still decides. Replaces whatever retriever was active.
        """
        lexical = LexicalMemoryRetriever(
            self.beliefs, self.episodes, self.companion, self._goals
        )
        self._executive.set_memory_retriever(
            EmbeddingMemoryRetriever(
                self.beliefs,
                self.episodes,
                self.companion,
                self._goals,
                embedder,
                fallback=lexical,
            )
        )

    @property
    def perception(self) -> PerceptionSource:
        """The capability provider that turns observations into evidence (Vision §32).

        Exposed read-only so a surface can *report* which perceiver is live (a dumb
        keyword rule, or a real LLM behind the same seam) without reaching into
        internals. It never decides anything (Vision §38).
        """
        return self._perception

    def set_perception(self, source: PerceptionSource) -> None:
        """Swap the perception source at runtime (Vision §32, §38; Track B).

        The choice of perceiver -- keyword rule vs a given LLM provider -- is config,
        changeable while running without rebuilding Jarvis. This only replaces the
        evidence *producer*; confidence is still derived downstream and the executive
        still reasons, so the cognitive core is untouched.
        """
        self._perception = source

    @property
    def companion_perception(self) -> CompanionPerceptionSource:
        """The relational perceiver: reads utterances into observations about the
        companion (Vision §5). Read-only so a surface can report it; it never decides.
        """
        return self._companion_perception

    def set_companion_perception(self, source: CompanionPerceptionSource) -> None:
        """Swap the companion perceiver at runtime (Vision §5, §38), like the world one."""
        self._companion_perception = source

    @property
    def voice(self) -> ResponseRenderer:
        """The presentation renderer that voices a decided reply (Vision §40).

        Edge concern, not cognition: the surface uses it to phrase Jarvis's reply in the
        companion's language. It never changes what Jarvis concluded (§38).
        """
        return self._voice

    def set_voice(self, renderer: ResponseRenderer) -> None:
        """Swap the reply renderer at runtime (matches the active provider)."""
        self._voice = renderer

    def note_companion(self, utterance: str) -> tuple[Belief, ...]:
        """Learn about the companion from what they said (Vision §5, §38).

        The relational half of a conversation turn: the utterance is read into
        observations about the companion, and each folds into the derived, revisable
        belief about that trait -- so talking to Jarvis actually builds its model of
        *you*, not only beliefs about the world. Returns the companion beliefs that were
        touched (empty when the utterance revealed nothing, §37). It only *produces*
        evidence; confidence is still derived and the belief remains contradictable.
        """
        learned: list[Belief] = []
        for observation in self._companion_perception.read_companion(utterance):
            belief, _ = self._record_companion(observation.trait, observation.evidence)
            learned.append(belief)
        return tuple(learned)

    @property
    def external_source(self) -> ExternalSource | None:
        """The Internet capability (Vision §38), or ``None`` when offline.

        Read-only so a surface can *report* whether Jarvis has an Internet source
        wired up. It is a capability provider: it retrieves external documents, never
        decides or writes to memory.
        """
        return self._external_source

    def set_external_source(self, source: ExternalSource | None) -> None:
        """Wire (or clear) the Internet capability at runtime.

        ``None`` disables it: Jarvis simply stays offline. Setting one only changes
        what Jarvis *can* fetch -- it does not change how Jarvis reasons or how often
        it chooses to look outside (that stays a deliberate, explicit decision).
        When a caller did not supply an explicit provider registry, the default
        registry (the web capabilities backed by this source) follows along.
        """
        self._external_source = source
        if self._external_providers_auto:
            self._capability_providers = build_default_registry(source)

    def read_external(self, url: str) -> RetrievedDocument:
        """Fetch one external document by ``url`` through the Internet capability.

        Raises a clear error when no Internet source is wired, or when the fetch
        fails. The returned document carries its provenance (source/url/title/
        metadata) so Jarvis can later tell it apart from internal knowledge.
        """
        if self._external_source is None:
            raise RuntimeError("no Internet capability configured; set_external_source")
        return self._external_source.read(url)

    def search_external(
        self, query: str, *, limit: int = 5
    ) -> tuple[RetrievedDocument, ...]:
        """Search the web through the Internet capability.

        Raises a clear error when no Internet source is wired or no search provider
        is configured (versus simply finding nothing). An empty result is an honest
        "nothing found".
        """
        if self._external_source is None:
            raise RuntimeError("no Internet capability configured; set_external_source")
        return self._external_source.search(query, limit=limit)

    def internet_channels(self) -> tuple[ChannelStatus, ...]:
        """Report which external channels are reachable right now (doctor).

        Returns an empty tuple when no Internet capability is wired. Report-only: it
        tells Jarvis what it *can* reach, not what to use.
        """
        if self._external_source is None:
            return ()
        return self._external_source.available_channels()

    # -- Odysseus: capability acquisition (Vision §34, §28) -------------------

    def need_capability(self, statement: str, rationale: str) -> tuple[Capability, ...]:
        """Recognise a capability gap and scout candidate ways to fill it
        (Odysseus, Vision §34).

        Given what Jarvis wants to do (``statement``) and why it matters
        (``rationale``), this proposes candidate capabilities drawn from what
        Jarvis could acquire. It only *proposes* -- none is pursued or adopted,
        and autonomy stays earned (Vision §28). A need that matches no candidate
        yields an empty tuple, an honest "no candidate yet".
        """
        need = CapabilityNeed(statement=statement, rationale=rationale)
        return scout(need)

    def recognise_need(
        self,
        statement: str,
        rationale: str,
        evidence: Iterable[Evidence] | None = None,
    ) -> tuple[Capability, ...]:
        """Record, with evidence, that Jarvis needs a capability -- the first real
        stage of acquisition (Odysseus, Vision §34, §3).

        The need becomes an ordinary *belief* (``"I need the ability to …"``) whose
        confidence is derived from the supplied evidence (Vision §8), so acquiring
        a capability is earned rather than asserted. It then scouts candidates and
        *persists* them, so a repeated need is recognised rather than re-proposed.
        Returns the candidate capabilities (possibly empty when none match). The
        need's own confidence is never set -- it is exactly as strong as its
        evidence.
        """
        need_statement = self._need_statement(statement)
        belief = self._needs.get_by_statement(need_statement) or Belief(
            statement=need_statement
        )
        for piece in evidence or ():
            belief.add_evidence(piece)
        self._needs.save(belief)
        for event in belief.pull_events():
            self.nervous_system.publish(event)
        self.nervous_system.dispatch()

        need = CapabilityNeed(statement=statement, rationale=rationale)
        candidates = scout(need)
        for capability in candidates:
            self._capabilities.save(capability)
        return candidates

    def capability_needs(self) -> tuple[tuple[str, Confidence], ...]:
        """The capability needs Jarvis has recognised, with their *derived*
        confidence, most-strongly-needed first (Odysseus, Vision §3, §8).

        Each is a need belief ("I need the ability to …") whose confidence comes
        from its evidence, not an assertion. Read-only.
        """
        needs = [
            (belief.statement, belief.confidence)
            for belief in self._needs.all_beliefs()
        ]
        needs.sort(key=lambda pair: pair[1].value, reverse=True)
        return tuple(needs)

    def recommend_capability(self, name: str) -> CapabilityRecommendation:
        """Derive a stance toward acquiring the capability named ``name``
        (Odysseus, Vision §28) -- the evaluation stage after the scout proposes.

        The stance comes from the derived confidence of the need behind it and
        whether Jarvis already has it (mirrors action learning): suggest only a
        confidently-needed, unavailable capability; ask first when uncertain or
        already available; withhold one whose need is contradicted. It only
        recommends -- it acquires nothing.
        """
        need = self._need_for_capability(name)
        capability = self._capabilities.get_by_name(name)
        return recommend_capability(need, capability)

    def _need_for_capability(self, capability_name: str) -> Belief | None:
        """The need belief bearing on a named capability, if Jarvis recorded one.

        Needs are keyed by their statement; this asks the one that most plausibly
        names the capability's work. Best effort: it looks for any recorded need
        whose plain-text subject mentions ``capability_name``, else None.
        """
        prefix = _NEED_PREFIX
        candidates = self._needs.all_beliefs()
        if not candidates:
            return None
        # The capability's own name usually appears in the need's plain subject.
        for belief in candidates:
            subject = belief.statement[len(prefix) :] if belief.statement.startswith(
                prefix
            ) else belief.statement
            if capability_name.lower() in subject.lower():
                return belief
        # Fall back to the most confident need as the best available grounds.
        return max(candidates, key=lambda b: b.confidence.value)

    def capability_stance(self, name: str) -> CapabilityStance:
        """The recommended stance toward acquiring ``name`` (Odysseus, Vision §28).

        A lightweight shorthand over :meth:`recommend_capability` for the surface.
        """
        return recommend_capability(
            self._need_for_capability(name), self._capabilities.get_by_name(name)
        ).stance

    def acquire_capability(self, name: str) -> Capability | None:
        """Mark a previously-proposed capability as acquired (Odysseus, Vision §28).

        Advertises that Jarvis now has the capability named ``name`` in its
        capability store. Returns the updated capability, or None when Jarvis has
        not proposed anything by that name. This is bookkeeping of what Jarvis
        *can* do -- it is not the capability itself, which must remain an
        injectable capability provider at the edge (D7).
        """
        current = self._capabilities.get_by_name(name)
        if current is None:
            return None
        acquired = current.mark_acquired()
        self._capabilities.save(acquired)
        return acquired

    def reject_capability(self, name: str) -> Capability | None:
        """Mark a proposed capability as rejected (Odysseus, Vision §28).

        Record that Jarvis evaluated ``name`` and declined it, so the scout will
        not keep re-proposing the same idea. Returns the updated capability, or
        None when Jarvis has not proposed anything by that name.
        """
        current = self._capabilities.get_by_name(name)
        if current is None:
            return None
        rejected = current.mark_rejected()
        self._capabilities.save(rejected)
        return rejected

    def remember_capability(self, capability: Capability) -> None:
        """Persist a proposed capability so it is not re-discovered from scratch.

        Stores ``capability`` in the capability store (used by the surface / a
        caller to record a scout result for continuity), so a repeated need is
        recognised rather than re-proposed. No acquisition happens here.
        """
        self._capabilities.save(capability)

    def capabilities(self) -> tuple[Capability, ...]:
        """Every capability Jarvis has proposed or acquired, for the surface to
        report what it can do (Vision §34). Read-only.
        """
        return self._capabilities.all_capabilities()

    def can_do(self, capability: str) -> bool:
        """Whether Jarvis can actually do ``capability`` right now (Odysseus, D7).

        ``True`` only when the capability is *acquired* (bookkeeping) *and* a
        ready edge provider backs it (the live side). A capability that is merely
        proposed, rejected, or unwired reads as not doable -- so the surfaces say
        honestly "I can't use it yet" instead of pretending.
        """
        current = self._capabilities.get_by_name(capability)
        if current is None or current.status is not CapabilityStatus.ACQUIRED:
            return False
        provider = (
            self._capability_providers.provider_for(capability)
            if self._capability_providers is not None
            else None
        )
        return provider is not None and provider.is_available()

    def usable_capabilities(self) -> tuple[str, ...]:
        """The capabilities Jarvis can actually use now, sorted by name.

        Acquired capabilities with a ready backing provider (``can_do``), for the
        surface to report what is genuinely live. Read-only.
        """
        return tuple(
            sorted(
                capability.name
                for capability in self._capabilities.all_capabilities()
                if self.can_do(capability.name)
            )
        )

    def observe_capability_gaps(self) -> tuple[CapabilityGap, ...]:
        """The recurring subjects Jarvis keeps failing to answer, from its own
        episode history (Odysseus self-initiated growth, Vision §34).

        Read-only detection: each gap reports a subject it could not conclude
        about more than once. Turning a gap into an evidence-grounded need is the
        caller's job (e.g. the surface records it via :meth:`recognise_need`), so
        this never writes state by itself.
        """
        return detect_capability_gaps(self.episodes.history())

    def unanswered_subjects(self) -> tuple[str, ...]:
        """The subjects Jarvis has noticed itself failing to answer about, as
        plain strings for the surface (Odysseus). Read-only; the gaps are the
        recurring failure subjects from the episode history.
        """
        return tuple(gap.subject for gap in self.observe_capability_gaps())

    @staticmethod
    def _need_statement(statement: str) -> str:
        return f"{_NEED_PREFIX}{statement}"

    @classmethod
    def persistent(
        cls,
        directory: str | Path,
        weighting_policy: EvidenceWeightingPolicy | None = None,
    ) -> Jarvis:
        """A Jarvis whose whole memory lives on disk under one directory.

        Wires every store -- beliefs, episodes, companion model, action learning,
        reversibility, goal reachability, sub-goal links, capability acquisitions
        (Odysseus), recognised capability needs and reflective-cycle
        refutations -- plus the decision-provenance trace to files under
        ``directory``, so a single call gives full continuity across restarts
        (Vision §3, §21, §26). It composes the JSON stores and the JSONL trace log.
        """
        base = Path(directory)
        source = build_agent_reach_source()
        return cls(
            beliefs=JsonBeliefStore(base / "beliefs.json", weighting_policy),
            episodes=JsonEpisodeStore(base / "episodes.json"),
            companion_store=JsonBeliefStore(base / "companion.json"),
            actions_store=JsonBeliefStore(base / "actions.json"),
            reversibility_store=JsonBeliefStore(base / "reversibility.json"),
            goals_store=JsonBeliefStore(base / "goals.json"),
            subgoals_store=JsonBeliefStore(base / "subgoals.json"),
            capabilities_store=JsonCapabilityStore(base / "capabilities.json"),
            needs_store=JsonBeliefStore(base / "needs.json"),
            refutations_store=JsonRefutationStore(base / "refutations.json"),
            trace=JsonEpisodeTrace(base / "trace.jsonl"),
            weighting_policy=weighting_policy,
            external_source=source,
            capability_providers=build_default_registry(source),
        )

    def think(
        self,
        trigger: str,
        evidence: Iterable[Evidence] = (),
        goal: Goal | None = None,
    ) -> CognitiveEpisode:
        """Run a cognitive episode for ``trigger``, grounded in ``evidence``.

        An optional ``goal`` names what the episode is *toward* (Vision §12, §26).
        With no evidence the episode completes with an honest "insufficient
        evidence" conclusion rather than a fabricated answer (Vision §37).
        """
        episode = CognitiveEpisode(trigger=trigger, goal=goal)
        return self._run(episode, evidence)

    def _run(
        self, episode: CognitiveEpisode, evidence: Iterable[Evidence] = ()
    ) -> CognitiveEpisode:
        """Run an episode through the executive and charge its cognitive cost
        (Vision §15). Every episode-running path goes through here so spent energy
        reflects all the thinking Jarvis actually did.
        """
        result = self._executive.run(episode, evidence, conserve=self._should_conserve())
        cost = self._energy_costs.for_attention(episode.attention)
        self._energy_spent += cost
        if self._energy_budget is not None:
            self._energy_available = max(0, self._energy_available - cost)
        return result

    def _should_conserve(self) -> bool:
        """True when the budget is low enough that a full episode should be avoided."""
        return (
            self._energy_budget is not None
            and self._energy_available < self._energy_costs.full
        )

    def energy_spent(self) -> int:
        """Total cognitive energy spent so far (Vision §15) — the accumulated cost of
        every episode run, FULL costing more than BRIEF. Read-only; zero for a fresh
        Jarvis. This is the lifetime tally, separate from the recoverable budget.
        """
        return self._energy_spent

    def energy_remaining(self) -> int | None:
        """Current energy left in the recoverable budget (Vision §15), or None when
        no budget is set. Depletes as episodes run; restored by :meth:`rest`.
        """
        return self._energy_available if self._energy_budget is not None else None

    def is_conserving(self) -> bool:
        """True when Jarvis is low enough on energy to answer briefly to conserve."""
        return self._should_conserve()

    def rest(self) -> None:
        """Restore energy to full (Vision §15) — this is fatigue, not a hard cap.
        A no-op when no budget is set.
        """
        if self._energy_budget is not None:
            self._energy_available = self._energy_budget

    def set_energy_budget(self, budget: int | None) -> None:
        """Set (or clear) the recoverable energy budget at runtime (Vision §15, §40).

        The seam a command center tunes to say how hard Jarvis should be willing to
        think: a smaller budget makes it conserve sooner (answering briefly), a
        larger one lets it run the full lifecycle for longer, and ``None`` clears the
        budget so nothing constrains attention. Available energy is refilled to the
        new budget — this sets capacity, it does not spend or penalise.
        """
        self._energy_budget = budget
        self._energy_available = budget if budget is not None else 0

    def perceive(
        self, observation: str, trigger: str | None = None, goal: Goal | None = None
    ) -> CognitiveEpisode:
        """Perceive a raw observation and reason over what it yields (Vision §32, §8).

        The observation is turned into evidence by the injected `PerceptionSource`
        (a dumb rule by default; a smarter perceiver drops in behind the same
        Protocol without touching the core, Vision §38), then reasoned over exactly
        like hand-supplied evidence. When the source makes nothing of it, the
        episode honestly concludes there is insufficient evidence (Vision §37).
        """
        evidence = self._perception.perceive(observation)
        return self.think(trigger or observation, evidence=evidence, goal=goal)

    def perceive_all(
        self,
        observations: Iterable[str],
        trigger: str | None = None,
        goal: Goal | None = None,
    ) -> CognitiveEpisode:
        """Perceive a stream of observations and reason over all of it at once
        (Vision §3, §8): a short exchange grounds one belief from everything it
        yields, weaker or contradicting lines pulling against stronger ones.

        Each observation is turned into evidence by the `PerceptionSource`; lines it
        makes nothing of contribute nothing. The trigger defaults to the first
        observation.
        """
        seen = list(observations)
        evidence = tuple(
            piece for observation in seen for piece in self._perception.perceive(observation)
        )
        resolved = trigger if trigger is not None else (seen[0] if seen else "")
        return self.think(resolved, evidence=evidence, goal=goal)

    def perceive_all_about_companion(
        self, trait: str, observations: Iterable[str]
    ) -> Belief | None:
        """Perceive a stream of observations about the companion, folding each into
        the lasting model of them (Vision §5, §3), or None if nothing is perceived.
        """
        belief: Belief | None = None
        for observation in observations:
            perceived = self.perceive_about_companion(trait, observation)
            if perceived is not None:
                belief = perceived
        return belief

    def observe_self(self) -> Belief | None:
        """Look back over past episodes and form a belief about Jarvis's own
        tendencies (Vision §6, §31), or None if there is too little history.

        The self-belief is grounded in the episode history and revisable like any
        other belief -- it is not a fixed personality trait.
        """
        return observe_evidence_habit(self.episodes.history())

    def observe_overconfidence(self) -> Belief | None:
        """A belief about whether Jarvis concludes confidently on thin evidence
        (Vision §6, §11), or None if there is too little grounded history.
        """
        return observe_overconfidence(self.episodes.history())

    def observe_prediction_accuracy(self) -> Belief | None:
        """A belief about whether Jarvis mispredicts its actions' outcomes
        (Vision §31), or None if it has judged too few kinds of action.
        """
        return observe_prediction_accuracy(self.actions.all_beliefs())

    def recurring_goals(self) -> tuple[tuple[str, int], ...]:
        """The goals Jarvis keeps returning to, from its episodic memory
        (Vision §26, §31), as ``(goal, count)`` pairs ordered by descending count.

        A plain count over remembered purposes -- not a belief, not a plan. It
        names what Jarvis has come back to often enough to be a pattern, saying
        nothing about whether pursuing it is wise. Empty when nothing recurs.
        """
        return recurring_goals(self.episodes.history())

    def reflection_effort(self, goal_statement: str) -> int:
        """How many times Jarvis has wondered about this goal on its own initiative
        (Vision §26, §31): the count of self-directed episodes recorded toward it.

        The mirror of the companion-side :meth:`recurring_goals`. It measures
        effort, not progress -- a high count with low reachability is honest.
        """
        return reflection_effort(self.episodes.history(), goal_statement)

    def stuck_goals(self) -> tuple[str, ...]:
        """Goals Jarvis has given up wondering about alone (Vision §16, §37): those
        it has learned are not reliably reachable *and* has already turned over to
        exhaustion. Ordered by recurrence (most-returned-to first). Empty when none.
        """
        return tuple(
            goal
            for goal, _ in self.recurring_goals()
            if self._is_exhausted_stuck_goal(goal)
        )

    def ask_for_help(self) -> str | None:
        """A spoken request for help with the most stuck goal, or None if there is
        none (Vision §18, §37).

        This is the companion turning outward *after* honest self-effort: it names a
        goal it keeps returning to but has not found how to reach, and asks. It only
        asks -- it asserts nothing and takes no action.
        """
        stuck = self.stuck_goals()
        if not stuck:
            return None
        goal = stuck[0]
        # The narrower the ask, the more actionable the help: if the stuck whole has
        # an identifiable blocking part, name it rather than the vague whole (§26).
        part = self._first_unreached_part(goal)
        if part is not None:
            reached, known = self.goal_progress(goal)
            detail = (
                f"I keep returning to {goal} — I've reached {reached} of {known} parts "
                f"but can't get past '{part}'"
            )
        else:
            detail = f"I keep returning to {goal} but haven't found how to reach it"
        # The relationship shapes the request: if Jarvis has confidently learned
        # this companion helps when it is stuck, the ask is warmer -- earned from
        # real evidence, not assumed (Vision §5, §18). Otherwise it stays neutral.
        helpful = self.companion.belief_about(HELPFUL_COMPANION_TRAIT)
        if helpful is not None and helpful.confidence.value >= 0.5:
            return f"You've helped me get unstuck before — {detail}; can you help again?"
        return f"{detail} on my own — can you help?"

    def self_beliefs(self) -> tuple[Belief, ...]:
        """Every self-tendency Jarvis currently holds about its own cognition
        (Vision §6): the ones it has enough history to judge.
        """
        candidates = (
            self.observe_self(),
            self.observe_overconfidence(),
            self.observe_prediction_accuracy(),
        )
        return tuple(belief for belief in candidates if belief is not None)

    def introspect(self) -> str:
        """A plain-language account of who Jarvis is, assembled from real state.

        Personality emerges from the actual state, not a prompt (Vision §29): the
        self-tendencies it has noticed (narrated), what it believes about its
        companion, and an honest note about how little it may still know
        (Vision §30, §40). Every line traces to a real belief -- nothing invented.
        """
        lines = ["This is what I currently understand about myself and my companion."]

        tendencies = [
            belief for belief in self.self_beliefs() if belief.confidence.value > 0.0
        ]
        if tendencies:
            lines.append("About myself:")
            for belief in sorted(
                tendencies, key=lambda b: b.confidence.value, reverse=True
            ):
                lines.append("  - " + belief.explain().narrate())
        else:
            lines.append(
                "About myself: I have not yet noticed any consistent tendencies."
            )

        companion = self.companion.summarise()
        if companion:
            lines.append("About my companion:")
            lines.extend("  - " + line for line in companion)
        else:
            lines.append("About my companion: I do not yet know much about them.")

        recurring = self.recurring_goals()
        if recurring:
            lines.append("What I keep returning to:")
            for goal, count in recurring:
                lines.append(
                    f"  - {goal} ({count} times)"
                    f"{self._reachability_note(goal)}{self._progress_note(goal)}"
                )

        acquired = [
            capability
            for capability in self._capabilities.all_capabilities()
            if capability.status.value == "acquired"
        ]
        if acquired:
            lines.append("What I can now do:")
            for capability in acquired:
                lines.append(f"  - {capability.description}")

        episodes = len(self.episodes.history())
        lines.append(
            f"This rests on {episodes} past episode(s); everything here is "
            "provisional and open to revision."
        )
        if self.is_conserving():
            lines.append(
                "I am low on energy right now, so I am thinking briefly to conserve."
            )
        return "\n".join(lines)

    def state_summary(self) -> StateSummary:
        """A compact, immutable snapshot of everything Jarvis currently holds.

        Assembled from the existing read surfaces (episodes, self-model, companion
        model, action learning); every field traces to real state (Vision §21).
        """
        return StateSummary(
            episode_count=len(self.episodes.history()),
            self_tendencies=tuple(
                (belief.statement, belief.confidence.value)
                for belief in self.self_beliefs()
                if belief.confidence.value > 0.0
            ),
            companion_traits=tuple(
                (belief.statement, belief.confidence.value)
                for belief in self.companion.beliefs()
            ),
            learned_actions=tuple(
                self._summarise_action(belief.statement, belief.confidence.value)
                for belief in self.actions.all_beliefs()
            ),
            recurring_goals=self.recurring_goals(),
            energy_spent=self._energy_spent,
            capabilities=tuple(
                (capability.name, capability.status.value)
                for capability in self._capabilities.all_capabilities()
            ),
            capability_needs=tuple(
                (statement.removeprefix(_NEED_PREFIX), confidence.value)
                for statement, confidence in self.capability_needs()
            ),
        )

    def _summarise_action(self, statement: str, confidence: float) -> LearnedAction:
        description = self._action_description(statement)
        return LearnedAction(
            description=description,
            confidence=confidence,
            stance=self.recommend_action_by_description(description).stance,
        )

    def feel_curious(self) -> CuriosityImpulse | None:
        """Decide whether any known self-tendency is worth investigating (Vision §16).

        Considers Jarvis's whole self-model and raises an impulse for the most
        confident weakness worth acting on -- a recommendation, not an action, or
        None if nothing is confident enough (Vision §28).
        """
        by_confidence = sorted(
            self.self_beliefs(), key=lambda belief: belief.confidence.value, reverse=True
        )
        for belief in by_confidence:
            impulse = wonder(belief)
            if impulse is not None:
                return impulse

        # A contested belief about the companion is a valuable unknown to reduce
        # (Vision §16, §18): the tension itself warrants curiosity, whatever the
        # exact confidence -- a balanced belief is the most worth resolving.
        for belief in self.companion.beliefs():
            explanation = belief.explain()
            if explanation.supporting and explanation.contradicting:
                return CuriosityImpulse(
                    trigger=f"Find out whether my companion really: {belief.statement}",
                    rationale=(
                        f'my belief that my companion "{belief.statement}" is contested'
                    ),
                    prompted_by_belief_id=belief.id,
                )

        # A belief Jarvis has reasoned to that is *contested* -- carrying both
        # supporting and contradicting evidence, e.g. from a mixed thing it perceived
        # (Vision §18, §32) -- is a live tension worth resolving, just like a contested
        # companion belief. The belief persists in the beliefs store under its trigger.
        contested = self._contested_working_belief()
        if contested is not None:
            topic = subject_of(contested.statement)
            return CuriosityImpulse(
                trigger=f"Resolve the tension in what I concluded about: {topic}",
                rationale=f'what I concluded about "{topic}" is contested by my evidence',
                prompted_by_belief_id=contested.id,
            )

        # An un-mined load-bearing observation is a pattern in the belief web worth
        # understanding (Vision §16, §31): several beliefs rest on one observation
        # and Jarvis has not yet reflected it into an insight. Pursuing this impulse
        # runs the reflective cycle. Prompted by a pattern in memory, not one belief.
        unmined = self._unmined_load_bearing()
        if unmined is not None:
            return CuriosityImpulse(
                trigger=f"Reflect on why several of my beliefs rest on: {unmined.observation}",
                rationale=(
                    f'"{unmined.observation}" underpins {unmined.load} of my beliefs '
                    "and I have not yet understood why"
                ),
                reflect_on=unmined.observation,
            )

        # A goal Jarvis keeps returning to is worth turning inward on (Vision §26,
        # §31): once self-reliability and companion tension are quiet, the pattern
        # in its own purposes becomes the most interesting unknown. Prompted by a
        # pattern in memory, not a single belief, so no belief id.
        recurring = self.recurring_goals()
        if recurring:
            # Sharpest tension first: a goal it keeps returning to yet has learned
            # it keeps *failing* to reach is more worth wondering about than one it
            # already knows it can reach -- but only while it has not already been
            # turned over to exhaustion (a stuck door worth one more push). `recurring`
            # is count-ordered, so the first such goal is also the most recurrent.
            for goal, count in recurring:
                if self._is_open_stuck_goal(goal):
                    # If the stuck whole has parts, the honest question is narrower:
                    # which specific part is blocking it? (Vision §26). The impulse
                    # still carries the parent goal, so effort accrues to the whole.
                    part = self._first_unreached_part(goal)
                    if part is not None:
                        reached, known = self.goal_progress(goal)
                        return CuriosityImpulse(
                            trigger=(
                                f"I've reached {reached} of {known} parts of {goal}; "
                                f"why can't I reach '{part}'?"
                            ),
                            rationale=(
                                f'the part "{part}" of goal "{goal}" is still unreached'
                            ),
                            goal=goal,
                        )
                    return CuriosityImpulse(
                        trigger=f"Why do I keep returning to {goal} without reaching it?",
                        rationale=(
                            f'I have pursued the goal "{goal}" {count} times '
                            "without reaching it"
                        ),
                        goal=goal,
                    )
            # Fallback: the most recurrent goal that is not an exhausted stuck goal
            # (a reachable or as-yet-unjudged recurring purpose still bears wondering).
            for goal, count in recurring:
                if not self._is_exhausted_stuck_goal(goal):
                    return CuriosityImpulse(
                        trigger=f"Why do I keep returning to: {goal}?",
                        rationale=f'I have pursued the goal "{goal}" {count} times',
                        goal=goal,
                    )

        # A capability Jarvis confidently needs but does not yet have is a growth
        # worth acting on (Odysseus, Vision §34, §28): the need is *earned* by
        # evidence, not a random want, so pursuing it acquires a real tool. The
        # evaluator's SUGGEST stance already encodes "confidently needed, not yet
        # held", so this reuses the derived recommendation rather than re-deciding.
        for need_statement, confidence in self.capability_needs():
            if confidence.value < _INSIGHT_CONFIDENCE:
                continue
            need = self._needs.get_by_statement(need_statement)
            for capability in self._capabilities.all_capabilities():
                if (
                    recommend_capability(need, capability).stance
                    is CapabilityStance.SUGGEST
                ):
                    subject = need_statement.removeprefix(_NEED_PREFIX)
                    return CuriosityImpulse(
                        trigger=f"Acquire the capability to: {subject}",
                        rationale=(
                            f'I need "{subject}" (need confidence '
                            f"{confidence.value:.2f}) and do not have "
                            f"'{capability.name}' yet"
                        ),
                        capability_to_acquire=capability.name,
                    )
        return None

    @staticmethod
    def _is_contested(belief: Belief) -> bool:
        """True when a belief carries both supporting and contradicting evidence
        *and* still leans neither way (confidence below the grounded threshold) --
        a genuine live tension, not a belief that merely records an old doubt while
        clearly settled (Vision §18). Strong enough guidance later resolves it.
        """
        explanation = belief.explain()
        return bool(
            explanation.supporting
            and explanation.contradicting
            and belief.confidence.value < 0.5
        )

    def _contested_working_belief(self) -> Belief | None:
        """A working belief that is a live tension worth resolving (Vision §18)."""
        for belief in self.beliefs.all_beliefs():
            if self._is_contested(belief):
                return belief
        return None

    def ask_about(self, topic: str) -> str | None:
        """Voice an unresolved tension so the companion can settle it (Vision §18,
        §37), or None when Jarvis holds no contested belief about ``topic``.

        When what Jarvis has concluded about ``topic`` is genuinely contested, it
        names both sides it has heard and asks which holds -- it only asks; it
        asserts nothing. Feed the answer back with :meth:`resolve`.
        """
        belief = self.beliefs.get_by_statement(working_statement(topic))
        if belief is None or not self._is_contested(belief):
            return None
        explanation = belief.explain()
        for_it = explanation.supporting[0].content
        against_it = explanation.contradicting[0].content
        return (
            f'About "{topic}", I have heard both "{for_it}" and "{against_it}" — '
            "which is it?"
        )

    def resolve(self, topic: str, guidance: str, supports: bool = True) -> Belief | None:
        """Take the companion's guidance on a contested topic as evidence (Vision §18,
        §20), tipping the working belief toward one side -- derived, never set.

        The guidance becomes a strong-provenance (`USER_STATEMENT`) piece of evidence
        on the belief for ``topic``; enough of it can move a contested belief past
        the grounded threshold so it is no longer a live tension. Returns the updated
        working belief.
        """
        episode = self.think(
            topic,
            evidence=[
                Evidence(
                    content=guidance,
                    source=EvidenceSource.USER_STATEMENT,
                    weight=Confidence(1.0),
                    supports=supports,
                    context="companion guidance on a contested topic",
                )
            ],
        )
        return episode.working_belief

    def confirm(self, trigger: str, affirm: bool = True) -> Belief | None:
        """Take the companion's confirmation (or correction) of a reasoned answer as
        evidence (Vision §18, §20) -- the learning loop's second half.

        A provisional answer Jarvis reasoned (weak `INFERENCE` evidence) matures when the
        companion weighs in: affirming adds strong `USER_STATEMENT` support so it becomes
        a grounded belief; correcting adds contradiction so it weakens. Confidence stays
        derived, never set. Returns the updated belief, or None if Jarvis holds no view on
        ``trigger`` to confirm.
        """
        if self.beliefs.get_by_statement(working_statement(trigger)) is None:
            return None
        verb = "confirmed" if affirm else "corrected"
        episode = self.think(
            trigger,
            evidence=[
                Evidence(
                    content=f"the companion {verb} this",
                    source=EvidenceSource.USER_STATEMENT,
                    weight=Confidence(1.0),
                    supports=affirm,
                    context="companion confirmation of a reasoned answer",
                )
            ],
        )
        return episode.working_belief

    def connections(self) -> tuple[Connection, ...]:
        """Beliefs that rest on the same evidence, linked (Vision §4, §31) — the
        first step beyond isolated memory, strongest connection first.

        Purely derived from shared evidence; stores nothing, asserts nothing. This
        is the raw material the reflective cycle's later stages work on.
        """
        return find_connections(list(self.beliefs.all_beliefs()))

    def related_beliefs(self, trigger: str) -> tuple[Connection, ...]:
        """The connections involving the belief Jarvis holds about ``trigger`` —
        what else it believes that rests on the same evidence (Vision §4).
        """
        statement = working_statement(trigger)
        return tuple(
            connection
            for connection in self.connections()
            if connection.involves(statement)
        )

    def reflect(self) -> tuple[Reflection, ...]:
        """Look across the belief web and notice load-bearing observations — a
        single piece of evidence that several beliefs rest on (Vision §19, §31),
        most load-bearing first. Cycle stage two, after Connect.

        A pure read-model: it *notices*, it does not conclude. Empty when no
        observation grounds more than one belief. Feeds autonomous hypotheses.
        """
        return find_reflections(list(self.beliefs.all_beliefs()), self._refutations.all())

    def hypothesise(self) -> HypothesisSet | None:
        """Brew a hypothesis from reflection (Vision §17, §31), or None when nothing
        is load-bearing to explain. Cycle stage three, after Reflect.

        Autonomously proposes that the most load-bearing observation may be a common
        cause of the beliefs resting on it, against the null that it is coincidence —
        a competing `HypothesisSet` whose confidence is derived, never asserted.
        """
        hypotheses = generate_hypotheses(self.reflect())
        if hypotheses is not None:
            hypotheses.pull_events()  # read-model: drain without dispatching
        return hypotheses

    def challenge(self) -> Challenge | None:
        """Name what would refute the leading hypothesis (Vision §11, §17, §37), or
        None when there is no hypothesis to challenge. Cycle stage four.

        Self-adversarial: rather than seek only confirmation, Jarvis states the
        concrete test — if a belief resting on the observation would still hold
        without it, the common cause is wrong. It asserts nothing false; :meth:`refute`
        records a counterexample, which removes that belief from the pattern and can
        dethrone the hypothesis.
        """
        hypotheses = self.hypothesise()
        if hypotheses is None:
            return None
        leading = hypotheses.leading()
        if leading is None:
            return None
        finding = self.reflect()[0]
        target = finding.beliefs[0]
        falsifier = (
            f'if "{target}" would still hold without "{finding.observation}", '
            "then it is not the common cause after all."
        )
        return Challenge(
            hypothesis=leading.statement,
            observation=finding.observation,
            falsifier=falsifier,
            beliefs=finding.beliefs,
        )

    def learn_from_reflection(self) -> Belief | None:
        """Adopt a reflective insight that survived challenge as a belief (Vision §20,
        §31) — cycle stage five, where the loop closes on itself. Returns the adopted
        belief, or None when nothing has earned it.

        When `hypothesise()` still leads with a common-cause explanation confidently
        (i.e. it was not dethroned by `refute`), Jarvis reasons a new belief stating
        that common cause, grounded in the same evidence. That belief enters the
        beliefs store like any conclusion — ordinary, derived, revisable — so the
        next Connect/Reflect can build on it, and it can itself be challenged later.
        """
        hypotheses = self.hypothesise()
        if hypotheses is None:
            return None
        leading = hypotheses.leading()
        if (
            leading is None
            or "common cause" not in leading.statement
            or leading.confidence.value < _INSIGHT_CONFIDENCE
        ):
            return None
        finding = self.reflect()[0]
        evidence = [
            Evidence(
                content=f"a belief rests on it: {statement}",
                source=EvidenceSource.SYSTEM_OBSERVATION,
                weight=Confidence(1.0),
            )
            for statement in finding.beliefs
        ]
        return self.think(
            self._insight_trigger(finding.observation), evidence=evidence
        ).working_belief

    @staticmethod
    def _insight_trigger(observation: str) -> str:
        return f'"{observation}" is a common cause behind several of my beliefs'

    def act_on_insight(self) -> ActionRecommendation | None:
        """Let a learned insight reach behaviour (Vision §27, §28, §31) — cycle stage
        six, Act. When Jarvis has confidently learned that one observation is a common
        cause, it proposes a graded action to verify that observation still holds and
        returns the recommended stance, or None when there is no such insight.

        It only *recommends* — it performs nothing (autonomy is earned, §28). The
        stance is derived from the existing action machinery; a brand-new action kind
        is asked-first, and experience with it can later earn a suggestion.
        """
        for finding in self.reflect():
            statement = working_statement(self._insight_trigger(finding.observation))
            belief = self.beliefs.get_by_statement(statement)
            if belief is not None and belief.confidence.value >= _INSIGHT_CONFIDENCE:
                action = Action(
                    description=f'verify that "{finding.observation}" still holds',
                    expected="the observation is confirmed",
                    confidence=belief.confidence,
                    reversible=True,
                )
                return self.recommend_action(action)
        return None

    def reflect_cycle(self) -> ReflectiveCycle:
        """Run the whole reflective cycle once and report what it produced (Vision
        §31): Connect → Reflect → Hypothesise → Challenge → Learn → Act, end to end.

        One honest action for "think about what I know" — it *calls* the existing
        stage methods in order (it does not re-implement them), and returns a
        summary of each stage's result, empty where nothing was load-bearing. Note
        it is not purely a read-model: the Learn stage adopts a surviving insight as
        a belief. Act runs *after* Learn so the just-learned insight is the one it
        acts on, and it only *recommends* (autonomy is earned, §28). This is the seam
        a future autonomous trigger will call.
        """
        connections = self.connections()
        reflections = self.reflect()
        reflection = reflections[0] if reflections else None
        hypotheses = self.hypothesise()
        leading = hypotheses.leading() if hypotheses is not None else None
        challenge = self.challenge()
        learned = self.learn_from_reflection()
        action = self.act_on_insight()
        return ReflectiveCycle(
            connections=connections,
            reflection=reflection,
            hypothesis=leading.statement if leading is not None else None,
            challenge=challenge,
            learned=learned.statement if learned is not None else None,
            action=action,
        )

    def _unmined_load_bearing(self) -> Reflection | None:
        """The top load-bearing observation not yet turned into a learned insight."""
        for finding in self.reflect():
            if not self._already_mined(finding.observation):
                return finding
        return None

    def _already_mined(self, observation: str) -> bool:
        marker = f'"{observation}" is a common cause'
        return any(marker in belief.statement for belief in self.beliefs.all_beliefs())

    def refute(self, observation: str, belief_statement: str) -> None:
        """Record that a belief would hold *without* an observation (Vision §17, §37):
        a counterexample answering :meth:`challenge`. The belief no longer rests on
        the observation, weakening — and, when enough are refuted, dethroning — the
        common-cause hypothesis. Derived, revisable; changes nothing about the belief
        itself, only that it no longer counts toward this pattern.
        """
        self._refutations.add(observation, belief_statement)

    def pursue(self, impulse: CuriosityImpulse) -> CognitiveEpisode:
        """Run a self-triggered episode for a curiosity impulse (Vision §16, §31).

        This is the first episode Jarvis initiates on its own rather than in
        response to the companion; it is marked with a CURIOSITY origin. When the
        impulse concerns a goal, the episode is recorded *toward* that goal (Vision
        §26), so wondering about a stuck goal leaves a trace on the goal itself --
        this records the reflection, not that the goal was reached. When the impulse
        wants to reflect on a load-bearing observation, the reflective cycle is run
        first (Increment 80) -- so Jarvis pursuing curiosity actually thinks about
        what it knows.
        """
        if impulse.reflect_on is not None:
            self.reflect_cycle()
        if impulse.capability_to_acquire is not None:
            self.acquire_capability(impulse.capability_to_acquire)
        goal = Goal(statement=impulse.goal) if impulse.goal is not None else None
        episode = CognitiveEpisode(
            trigger=impulse.trigger, origin=TriggerOrigin.CURIOSITY, goal=goal
        )
        return self._run(episode)

    def consider(
        self, observation: str, options: Mapping[str, Sequence[Evidence]]
    ) -> Deliberation:
        """Weigh competing explanations for ``observation`` (Vision §17).

        ``options`` maps each candidate explanation to the evidence bearing on it.
        Runs as a first-class deliberation episode (recorded and traceable) and
        returns the ranking plus the leading explanation -- or, when the top two
        are tied, no leader and a request for evidence that would decide.
        """
        return self._executive.deliberate(observation, options)

    def trace_of(self, episode: CognitiveEpisode) -> tuple[CognitiveEvent, ...]:
        """The ordered cognitive events of ``episode`` -- its decision provenance
        (Vision §26): started, the evidence and belief changes, then completed.
        """
        return self._trace.for_correlation(episode.id)

    def trace(self, correlation_id: str) -> tuple[CognitiveEvent, ...]:
        """The ordered cognitive events of a process by correlation id -- e.g. a
        deliberation's ``episode_id`` (Vision §26).
        """
        return self._trace.for_correlation(correlation_id)

    def act(
        self,
        description: str,
        expected: str,
        *,
        confidence: Confidence | None = None,
        reversible: bool = True,
    ) -> Action:
        """Declare an intention to act, with its expected outcome (Vision §27).

        This only *records* the intention -- it performs nothing in the world.
        Close the loop later with :meth:`record_outcome`.
        """
        return Action(
            description=description,
            expected=expected,
            confidence=confidence or Confidence(0.5),
            reversible=reversible,
        )

    def record_outcome(
        self, action: Action, actual: str, met_expectation: bool
    ) -> Belief:
        """Record what actually happened and learn from expected-vs-actual (Vision §20).

        The outcome becomes evidence for a belief about actions of this kind, so
        repeated matches build confidence and repeated mismatches erode it.
        """
        statement = self._action_statement(action.description)
        belief = self.actions.get_by_statement(statement) or Belief(statement=statement)
        belief.add_evidence(
            Evidence(
                content=(
                    f"acted '{action.description}': expected '{action.expected}', "
                    f"got '{actual}'"
                ),
                source=EvidenceSource.ACTION_OUTCOME,
                weight=Confidence(1.0),
                supports=met_expectation,
            )
        )
        self.actions.save(belief)
        self._remember_reversibility(action)
        for event in belief.pull_events():
            self.nervous_system.publish(event)
        self.nervous_system.publish(
            ActionOutcomeRecorded(
                action_id=action.id,
                description=action.description,
                met_expectation=met_expectation,
            )
        )
        self.nervous_system.dispatch()
        return belief

    def belief_about_action(self, description: str) -> Belief | None:
        """What Jarvis believes about how actions of this kind turn out."""
        return self.actions.get_by_statement(self._action_statement(description))

    def mark_goal_reached(self, goal: Goal, reached: bool = True) -> Belief:
        """Record that a goal was (or was not) reached, and learn from it (Vision §26, §27).

        The companion asserts the outcome -- Jarvis does not evaluate the goal's
        ``success_criterion`` itself yet. The outcome becomes evidence for a belief
        that goals of this kind are *reachable*, so repeated successes build
        confidence and repeated failures erode it (derived, revisable, exactly like
        action-outcome learning). Reaching it also supplies the criterion, if any,
        as context.
        """
        statement = self._goal_statement(goal.statement)
        belief = self._goals.get_by_statement(statement) or Belief(statement=statement)
        outcome = "reached" if reached else "not reached"
        belief.add_evidence(
            Evidence(
                content=f"goal '{goal.statement}' was {outcome}",
                source=EvidenceSource.ACTION_OUTCOME,
                weight=Confidence(1.0),
                supports=reached,
                context=goal.success_criterion,
            )
        )
        self._goals.save(belief)
        for event in belief.pull_events():
            self.nervous_system.publish(event)
        self.nervous_system.dispatch()

        # Progress on a part is honest evidence about the whole (Vision §12, §26):
        # reaching a sub-goal credits its parent's reachability -- but softly (a
        # DIRECT_OBSERVATION, weaker than reaching the whole directly), and the
        # parent is never "done" because a child is; its reachability stays derived.
        if goal.part_of is not None:
            self._credit_parent(goal.part_of, goal.statement, reached)
        return belief

    def _credit_parent(self, parent: str, child: str, reached: bool) -> None:
        statement = self._goal_statement(parent)
        belief = self._goals.get_by_statement(statement) or Belief(statement=statement)
        outcome = "reached" if reached else "not reached"
        belief.add_evidence(
            Evidence(
                content=f"its part '{child}' was {outcome}",
                source=EvidenceSource.DIRECT_OBSERVATION,
                weight=Confidence(1.0),
                supports=reached,
            )
        )
        self._goals.save(belief)
        for event in belief.pull_events():
            self.nervous_system.publish(event)
        self.nervous_system.dispatch()
        self._record_subgoal_link(parent, child, reached)

    def _record_subgoal_link(self, parent: str, child: str, reached: bool) -> None:
        """Make the parent→child structure queryable (Vision §26). A bookkeeping
        belief per link; its own confidence is unused -- what matters is the set of
        known children and which have been reached at least once.
        """
        statement = self._subgoal_statement(parent, child)
        belief = self._subgoals.get_by_statement(statement) or Belief(statement=statement)
        outcome = "reached" if reached else "not reached"
        belief.add_evidence(
            Evidence(
                content=f"'{child}' was {outcome}",
                source=EvidenceSource.DIRECT_OBSERVATION,
                weight=Confidence(1.0),
                supports=reached,
            )
        )
        belief.pull_events()  # bookkeeping link -- events are not dispatched
        self._subgoals.save(belief)

    @staticmethod
    def _subgoal_statement(parent: str, child: str) -> str:
        return f"The goal '{child}' is a part of '{parent}'"

    def sub_goals(self, parent: str) -> tuple[str, ...]:
        """The parts recorded for ``parent`` (Vision §26), in the order first seen."""
        prefix = "The goal '"
        suffix = f"' is a part of '{parent}'"
        return tuple(
            belief.statement[len(prefix) : -len(suffix)]
            for belief in self._subgoals.all_beliefs()
            if belief.statement.endswith(suffix)
        )

    def _first_unreached_part(self, parent: str) -> str | None:
        """The first recorded part of ``parent`` never yet reached, or None.

        Consistent with :meth:`goal_progress`: a part counts as reached once it has
        any supporting evidence, so an unreached part is one with none.
        """
        prefix = "The goal '"
        suffix = f"' is a part of '{parent}'"
        for belief in self._subgoals.all_beliefs():
            if belief.statement.endswith(suffix) and not belief.explain().supporting:
                return belief.statement[len(prefix) : -len(suffix)]
        return None

    def goal_progress(self, parent: str) -> tuple[int, int]:
        """How far along a decomposed goal is, as ``(parts reached, parts known)``
        (Vision §26, §30). A part counts as reached once it has been reached at
        least once; truthful about partials -- it is not progress toward "done",
        just a count over recorded structure.
        """
        suffix = f"' is a part of '{parent}'"
        children = [
            belief
            for belief in self._subgoals.all_beliefs()
            if belief.statement.endswith(suffix)
        ]
        reached = sum(1 for belief in children if belief.explain().supporting)
        return (reached, len(children))

    def receive_help(self, goal: Goal, helpful: bool = True) -> Belief:
        """Take in the companion's guidance on a goal and learn from it (Vision §18, §26).

        Closes the ask→answer→learn loop opened by :meth:`ask_for_help`: the
        companion's guidance becomes strong-provenance evidence (a `USER_STATEMENT`,
        the highest source weight) on the goal's reachability belief. Genuinely
        helpful guidance can, over time, lift a goal Jarvis had given up on above
        the reachable threshold and so clear the suppression. Help is *evidence*,
        not a guarantee: an unhelpful answer contradicts, and reachability stays
        derived, never set.
        """
        statement = self._goal_statement(goal.statement)
        belief = self._goals.get_by_statement(statement) or Belief(statement=statement)
        outcome = "helped" if helpful else "did not help"
        belief.add_evidence(
            Evidence(
                content=f"the companion's guidance on '{goal.statement}' {outcome}",
                source=EvidenceSource.USER_STATEMENT,
                weight=Confidence(1.0),
                supports=helpful,
                context=goal.success_criterion,
            )
        )
        self._goals.save(belief)
        for event in belief.pull_events():
            self.nervous_system.publish(event)
        self.nervous_system.dispatch()

        # The same act says something about the companion, not only the goal: help
        # that worked is evidence they are helpful when Jarvis is stuck (Vision §5,
        # §20). A distinct, revisable belief about the companion -- provenance-
        # grounded relationship learning, not programmed gratitude. Unhelpful
        # guidance contradicts it, exactly as any companion contradiction does.
        self._record_companion(
            HELPFUL_COMPANION_TRAIT,
            Evidence(
                content=f"the companion's guidance on '{goal.statement}' {outcome}",
                source=EvidenceSource.USER_STATEMENT,
                weight=Confidence(1.0),
                supports=helpful,
            ),
        )

        # If the ask named a specific blocking part (Increment 60), helpful guidance
        # got Jarvis past *that* part: credit the part directly (Vision §26), so it
        # stops being the unreached blocker. Only on real help, and only the one
        # part that was actually named -- nothing is asserted "done".
        if helpful:
            part = self._first_unreached_part(goal.statement)
            if part is not None:
                self._credit_helped_part(goal.statement, part)
        return belief

    def _credit_helped_part(self, parent: str, part: str) -> None:
        statement = self._goal_statement(part)
        belief = self._goals.get_by_statement(statement) or Belief(statement=statement)
        belief.add_evidence(
            Evidence(
                content=f"the companion's guidance helped reach the part '{part}'",
                source=EvidenceSource.USER_STATEMENT,
                weight=Confidence(1.0),
                supports=True,
            )
        )
        self._goals.save(belief)
        for event in belief.pull_events():
            self.nervous_system.publish(event)
        self.nervous_system.dispatch()
        # The link now counts as reached, so goal_progress advances and the part is
        # no longer the blocker curiosity/ask fixate on.
        self._record_subgoal_link(parent, part, True)

    def belief_about_goal(self, goal: Goal | str) -> Belief | None:
        """What Jarvis has learned about whether a goal of this kind is reachable,
        or None if it has never been told an outcome for it (Vision §26).
        """
        statement = goal.statement if isinstance(goal, Goal) else goal
        return self._goals.get_by_statement(self._goal_statement(statement))

    @staticmethod
    def _goal_statement(goal_statement: str) -> str:
        return f"The goal '{goal_statement}' is reachable"

    def _is_stuck_goal(self, goal_statement: str) -> bool:
        """True when Jarvis has *learned* this goal is not reliably reachable."""
        belief = self.belief_about_goal(goal_statement)
        return belief is not None and belief.confidence.value < 0.5

    def _is_open_stuck_goal(self, goal_statement: str) -> bool:
        """A stuck goal still worth wondering about: not yet turned over to exhaustion."""
        return (
            self._is_stuck_goal(goal_statement)
            and self.reflection_effort(goal_statement) < _MAX_GOAL_REFLECTIONS
        )

    def _is_exhausted_stuck_goal(self, goal_statement: str) -> bool:
        """A stuck goal wondered about enough for now (suppressed until something changes)."""
        return (
            self._is_stuck_goal(goal_statement)
            and self.reflection_effort(goal_statement) >= _MAX_GOAL_REFLECTIONS
        )

    def _reachability_note(self, goal_statement: str) -> str:
        """A truthful annotation of what Jarvis has learned about reaching a goal.

        Empty when no outcome is known yet; otherwise it reports learned
        reachability from the derived confidence -- never asserting more than the
        evidence supports (mirrors the grounded threshold, D14).
        """
        belief = self.belief_about_goal(goal_statement)
        if belief is None:
            return ""
        confidence = belief.confidence.value
        if confidence >= 0.5:
            return f" — I have learned I can reach this (confidence {confidence:.2f})"
        note = f" — I have not reliably reached this yet (confidence {confidence:.2f})"
        effort = self.reflection_effort(goal_statement)
        if effort > 0:
            times = "time" if effort == 1 else "times"
            note += f", and have turned it over {effort} {times}"
        return note

    def _progress_note(self, goal_statement: str) -> str:
        """A truthful annotation of how many of a goal's known parts are reached."""
        reached, known = self.goal_progress(goal_statement)
        if known == 0:
            return ""
        return f" ({reached} of {known} parts reached)"

    def recommend_action_by_description(self, description: str) -> ActionRecommendation:
        """Recommend a stance for a *remembered* kind of action (Vision §28).

        Unlike :meth:`recommend_action`, this needs no live `Action`: it reads
        both the learned outcome belief and the learned reversibility belief, so
        the stance survives a restart. Reversibility unknown is treated
        conservatively (not reversible → ask first).
        """
        outcome = self.belief_about_action(description)
        reversible = self._believed_reversible(description)
        return recommend_stance(outcome, reversible=reversible)

    def _remember_reversibility(self, action: Action) -> None:
        statement = self._reversibility_statement(action.description)
        belief = self._reversibility.get_by_statement(statement) or Belief(
            statement=statement
        )
        manner = "reversibly" if action.reversible else "irreversibly"
        belief.add_evidence(
            Evidence(
                content=f"acted '{action.description}' ({manner})",
                source=EvidenceSource.ACTION_OUTCOME,
                weight=Confidence(1.0),
                supports=action.reversible,
            )
        )
        belief.pull_events()  # bookkeeping belief -- its events are not dispatched
        self._reversibility.save(belief)

    def _believed_reversible(self, description: str) -> bool:
        belief = self._reversibility.get_by_statement(
            self._reversibility_statement(description)
        )
        return belief is not None and belief.confidence.value >= 0.5

    @staticmethod
    def _reversibility_statement(description: str) -> str:
        return f"The action '{description}' is reversible"

    def recommend_action(self, action: Action) -> ActionRecommendation:
        """Recommend a stance toward ``action`` from experience (Vision §28).

        Suggests only a confidently-learned, reversible action; asks first when
        unproven or irreversible; withholds one the record contradicts. It only
        recommends -- it performs nothing (autonomy is earned).
        """
        belief = self.belief_about_action(action.description)
        return recommend_stance(belief, reversible=action.reversible)

    @staticmethod
    def _action_statement(description: str) -> str:
        return f"My predictions about the action '{description}' hold"

    @staticmethod
    def _action_description(statement: str) -> str:
        # Exact inverse of _action_statement (a controlled template, not free text).
        return statement.removeprefix(
            "My predictions about the action '"
        ).removesuffix("' hold")

    def observe_companion(self, trait: str, evidence: Evidence) -> Belief:
        """Record an observation about the companion and evolve Jarvis's model of
        them (Vision §5). Returns the (revisable) belief; its events flow through
        the nervous system.
        """
        belief, _ = self._record_companion(trait, evidence)
        return belief

    def perceive_about_companion(self, trait: str, observation: str) -> Belief | None:
        """Perceive an observation about the companion and let it shape the lasting
        model of them (Vision §5, §32), or None if nothing is perceived.

        Bridges perception (Increment 63) to the companion model: the observation is
        turned into evidence by the `PerceptionSource`, and each piece is folded into
        the derived, revisable belief about ``trait`` -- so perceived praise builds it
        and a perceived denial contradicts it, exactly like hand-built evidence. An
        observation the source makes nothing of leaves the model untouched (§37).
        """
        belief: Belief | None = None
        for piece in self._perception.perceive(observation):
            belief = self.observe_companion(trait, piece)
        return belief

    def acknowledge_companion(self, trait: str, evidence: Evidence) -> str:
        """Record an observation and acknowledge it in conversation (Vision §18).

        When the observation contradicts a belief Jarvis actually held, it says
        so plainly -- the person has contradicted its model, and it holds the
        belief less firmly now. A first or consistent observation is just noted.
        """
        _, contradicted = self._record_companion(trait, evidence)
        if contradicted:
            return (
                f'You have contradicted what I believed about "{trait}". '
                "I may be wrong, so I am holding it less firmly now."
            )
        return f'Noted about "{trait}".'

    def _record_companion(self, trait: str, evidence: Evidence) -> tuple[Belief, bool]:
        belief = self.companion.observe(trait, evidence)
        events = self.companion.pull_events()
        contradicted = any(isinstance(event, ContradictionDetected) for event in events)
        for event in events:
            self.nervous_system.publish(event)
        self.nervous_system.dispatch()
        return belief, contradicted

    def explain_companion(self, trait: str) -> str:
        """Explain *why* Jarvis believes ``trait`` about its companion (Vision §5, §8).

        Returns the belief's provenance narrated -- the evidence for and against
        it, its confidence, and, when contested, an honest "I may be wrong". If no
        such belief is held yet, says so plainly (Vision §37).
        """
        belief = self.companion.belief_about(trait)
        if belief is None:
            return f'I don\'t hold a view on "{trait}" about my companion yet.'
        return belief.explain().narrate()
