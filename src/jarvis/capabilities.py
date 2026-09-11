"""Odysseus capability acquisition surface.

Methods that manage capability needs, scouting, acquisition, and live
provider mapping.  The Jarvis class retains thin delegator methods that
forward here.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from jarvis.domain.enums.capability_stance import CapabilityStance
from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.capability_evaluator import recommend as recommend_capability
from jarvis.domain.services.capability_gap_observation import (
    CapabilityGap,
    detect_capability_gaps,
)
from jarvis.domain.services.capability_scout import catalog, scout
from jarvis.domain.value_objects.capability import Capability
from jarvis.domain.value_objects.capability_need import CapabilityNeed
from jarvis.domain.value_objects.capability_recommendation import CapabilityRecommendation
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence

if TYPE_CHECKING:
    from jarvis.domain.entities.belief import Belief
    from jarvis.jarvis import Jarvis

_NEED_PREFIX = "I need the ability to: "


class CapabilitySurface:
    """Odysseus capability acquisition surface."""

    def __init__(self, jarvis: Jarvis) -> None:
        self._jarvis = jarvis

    @staticmethod
    def _need_statement(statement: str) -> str:
        return f"{_NEED_PREFIX}{statement}"

    def _need_for_capability(self, capability_name: str) -> Belief | None:
        """The need belief bearing on a named capability, if Jarvis recorded one.

        Needs are keyed by their statement; this asks the one that most plausibly
        names the capability's work. Best effort: it looks for any recorded need
        whose plain-text subject mentions ``capability_name``, else None.
        """
        prefix = _NEED_PREFIX
        candidates = self._jarvis._needs.all_beliefs()
        if not candidates:
            return None
        for belief in candidates:
            subject = belief.statement[len(prefix) :] if belief.statement.startswith(
                prefix
            ) else belief.statement
            if capability_name.lower() in subject.lower():
                return belief
        return max(candidates, key=lambda b: b.confidence.value)

    def need_capability(
        self, statement: str, rationale: str
    ) -> tuple[Capability, ...]:
        need = CapabilityNeed(statement=statement, rationale=rationale)
        return scout(need)

    def recognise_need(
        self,
        statement: str,
        rationale: str,
        evidence: Iterable[Evidence] | None = None,
    ) -> tuple[Capability, ...]:
        need_statement = self._need_statement(statement)
        belief = self._jarvis._needs.get_by_statement(
            need_statement
        ) or self._jarvis._fresh_belief(need_statement)
        for piece in evidence or ():
            belief.add_evidence(piece)
        self._jarvis._needs.save(belief)
        for event in belief.pull_events():
            self._jarvis.nervous_system.publish(event)
        self._jarvis.nervous_system.dispatch()

        need = CapabilityNeed(statement=statement, rationale=rationale)
        candidates = scout(need)
        for capability in candidates:
            self._jarvis._capabilities.save(capability)
        return candidates

    def capability_needs(self) -> tuple[tuple[str, Confidence], ...]:
        needs = [
            (belief.statement, belief.confidence)
            for belief in self._jarvis._needs.all_beliefs()
        ]
        needs.sort(key=lambda pair: pair[1].value, reverse=True)
        return tuple(needs)

    def recommend_capability(self, name: str) -> CapabilityRecommendation:
        need = self._need_for_capability(name)
        capability = self._jarvis._capabilities.get_by_name(name)
        return recommend_capability(need, capability)

    def capability_stance(self, name: str) -> CapabilityStance:
        return recommend_capability(
            self._need_for_capability(name),
            self._jarvis._capabilities.get_by_name(name),
        ).stance

    def acquire_capability(self, name: str) -> Capability | None:
        current = self._jarvis._capabilities.get_by_name(name)
        if current is None:
            return None
        acquired = current.mark_acquired()
        self._jarvis._capabilities.save(acquired)
        return acquired

    def reject_capability(self, name: str) -> Capability | None:
        current = self._jarvis._capabilities.get_by_name(name)
        if current is None:
            return None
        rejected = current.mark_rejected()
        self._jarvis._capabilities.save(rejected)
        return rejected

    def remember_capability(self, capability: Capability) -> None:
        self._jarvis._capabilities.save(capability)

    def capabilities(self) -> tuple[Capability, ...]:
        return self._jarvis._capabilities.all_capabilities()

    def can_do(self, capability: str) -> bool:
        current = self._jarvis._capabilities.get_by_name(capability)
        if current is None or current.status is not CapabilityStatus.ACQUIRED:
            return False
        provider = (
            self._jarvis._capability_providers.provider_for(capability)
            if self._jarvis._capability_providers is not None
            else None
        )
        return provider is not None and provider.is_available()

    def usable_capabilities(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                capability.name
                for capability in self._jarvis._capabilities.all_capabilities()
                if self.can_do(capability.name)
            )
        )

    def provision_live_capabilities(self) -> tuple[Capability, ...]:
        registry = self._jarvis._capability_providers
        if registry is None:
            return ()
        provisioned: list[Capability] = []
        for candidate in catalog():
            provider = registry.provider_for(candidate.name)
            if provider is None or not provider.is_available():
                continue
            current = self._jarvis._capabilities.get_by_name(candidate.name)
            if current is None:
                acquired = candidate.mark_acquired()
                self._jarvis._capabilities.save(acquired)
                provisioned.append(acquired)
            elif current.status is CapabilityStatus.PROPOSED:
                acquired = current.mark_acquired()
                self._jarvis._capabilities.save(acquired)
                provisioned.append(acquired)
        return tuple(provisioned)

    def observe_capability_gaps(self) -> tuple[CapabilityGap, ...]:
        return detect_capability_gaps(
            self._jarvis.episodes.history(), knobs=self._jarvis._knobs
        )

    def unanswered_subjects(self) -> tuple[str, ...]:
        return tuple(gap.subject for gap in self.observe_capability_gaps())

    def auto_scout_gaps(self) -> tuple[Capability, ...]:
        proposals: list[Capability] = []
        for gap in self.observe_capability_gaps():
            statement = f"answer repeated questions about {gap.subject}"
            rationale = (
                f"I noticed I keep failing to conclude about '{gap.subject}' "
                f"({len(gap.episodes)} ungrounded attempt(s))"
            )
            evidence = [
                Evidence(
                    content=(
                        f"episode about '{record.trigger}' concluded ungrounded "
                        f"(confidence {record.conclusion_confidence.value:.2f})"
                    ),
                    source=EvidenceSource.SYSTEM_OBSERVATION,
                    weight=Confidence(1.0),
                    supports=True,
                )
                for record in gap.episodes
            ]
            need = self._jarvis._needs.get_by_statement(
                self._need_statement(statement)
            )
            if need is not None:
                existing = {piece.content for piece in need.evidence}
                evidence = [p for p in evidence if p.content not in existing]
            if not evidence:
                continue
            proposals.extend(
                self.recognise_need(statement, rationale, evidence)
            )
        return tuple(proposals)
