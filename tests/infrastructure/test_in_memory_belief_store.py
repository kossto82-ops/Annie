"""Behavioural tests for the in-memory belief store."""

from __future__ import annotations

from jarvis.domain.entities.belief import Belief
from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore


class TestStore:
    def test_unknown_statement_returns_none(self) -> None:
        assert InMemoryBeliefStore().get_by_statement("unknown") is None

    def test_saved_belief_is_retrievable_by_statement(self) -> None:
        store = InMemoryBeliefStore()
        belief = Belief(statement="the user prefers simplicity")
        store.save(belief)
        assert store.get_by_statement("the user prefers simplicity") is belief

    def test_saving_the_same_statement_updates_in_place(self) -> None:
        store = InMemoryBeliefStore()
        first = Belief(statement="x")
        store.save(first)
        again = Belief(statement="x")
        store.save(again)
        assert store.get_by_statement("x") is again
