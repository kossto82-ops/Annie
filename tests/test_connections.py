"""Tests for Connect: beliefs linked by shared evidence (Vision §4, §31)."""

from __future__ import annotations

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _ev(content: str) -> Evidence:
    return Evidence(
        content=content,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(0.9),
    )


class TestConnections:
    def test_beliefs_grounded_in_the_same_evidence_are_connected(self) -> None:
        jarvis = Jarvis()
        shared = "chose the simpler design"
        jarvis.think("does the companion prefer simplicity?", evidence=[_ev(shared)])
        jarvis.think("should the design be simple?", evidence=[_ev(shared)])

        connections = jarvis.connections()
        assert len(connections) == 1
        assert connections[0].shared_evidence == ("chose the simpler design",)
        assert connections[0].strength == 1

    def test_beliefs_with_no_shared_evidence_are_not_connected(self) -> None:
        jarvis = Jarvis()
        jarvis.think("question one", evidence=[_ev("observation A")])
        jarvis.think("question two", evidence=[_ev("observation B")])
        assert jarvis.connections() == ()

    def test_a_belief_with_no_evidence_connects_to_nothing(self) -> None:
        jarvis = Jarvis()
        jarvis.think("grounded", evidence=[_ev("shared thing")])
        jarvis.think("empty")  # no evidence
        assert jarvis.connections() == ()

    def test_related_beliefs_returns_connections_involving_a_trigger(self) -> None:
        jarvis = Jarvis()
        jarvis.think("A", evidence=[_ev("same observation")])
        jarvis.think("B", evidence=[_ev("same observation")])
        jarvis.think("C", evidence=[_ev("unrelated")])

        related = jarvis.related_beliefs("A")
        assert len(related) == 1
        assert related[0].involves("Working conclusion about: A")
        assert related[0].involves("Working conclusion about: B")
        assert jarvis.related_beliefs("C") == ()

    def test_more_shared_evidence_means_a_stronger_connection(self) -> None:
        jarvis = Jarvis()
        jarvis.think("X", evidence=[_ev("obs one"), _ev("obs two")])
        jarvis.think("Y", evidence=[_ev("obs one"), _ev("obs two")])
        jarvis.think("Z", evidence=[_ev("obs one")])

        # X–Y share two observations, X–Z (and Y–Z) share one: X–Y is strongest.
        strongest = jarvis.connections()[0]
        assert strongest.strength == 2
        assert set(strongest.shared_evidence) == {"obs one", "obs two"}
