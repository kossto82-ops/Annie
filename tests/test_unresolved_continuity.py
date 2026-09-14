"""Unresolved state: open questions live, recover, resolve and matter (P1).

Required lifecycle:

    created -> active -> retrieved -> attention candidate
      -> investigated -> resolved -> history preserved

Restart experiment: Day 1 opens a question; after a restart Day 2 recovers
it (and curiosity surfaces it); resolving grounds the answer as evidence;
after another restart Day 3 reasoning uses the resolution.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.domain.value_objects.unresolved_item import UnresolvedStatus
from jarvis.jarvis import Jarvis


class TestUnresolvedLifecycle:
    def test_full_lifecycle_across_restarts(self, tmp_path: Path) -> None:
        # Day 1: an unanswerable question is noted, honestly unresolved.
        day_one = Jarvis.persistent(tmp_path)
        item = day_one.note_open_question("why do the swallows return?")
        assert item.status is UnresolvedStatus.OPEN
        assert day_one.open_questions()[0].question == "why do the swallows return?"
        assert (tmp_path / "unresolved.json").exists()

        # Restart: Day 2 recovers it...
        day_two = Jarvis.persistent(tmp_path)
        recovered = day_two.open_questions()
        assert [i.question for i in recovered] == ["why do the swallows return?"]

        # ...as an attention candidate (nothing else competes for attention).
        impulse = day_two.feel_curious()
        assert impulse is not None
        assert "why do the swallows return?" in impulse.trigger

        # Investigated, then resolved: the answer grounds as real evidence.
        day_two.think("why do the swallows return?")
        resolved = day_two.resolve_open_question(
            "why do the swallows return?", "they follow the warm winds north"
        )
        assert resolved.status is UnresolvedStatus.RESOLVED
        assert resolved.resolution == "they follow the warm winds north"
        assert day_two.open_questions() == ()

        # Restart: history is preserved and the resolution informs cognition.
        day_three = Jarvis.persistent(tmp_path)
        history = {
            item.question: item.status for item in day_three.unresolved_history()
        }
        assert history == {"why do the swallows return?": UnresolvedStatus.RESOLVED}
        belief = day_three.beliefs.beliefs_about("swallows")
        assert belief, "the resolution must live on as a belief"
        assert any(
            "warm winds" in piece.content for piece in belief[0].evidence
        ), "later reasoning must reach the recorded answer"

    def test_resolving_unknown_raises_honestly(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        with pytest.raises(KeyError):
            jarvis.resolve_open_question("never asked", "nope")

    def test_empty_question_is_rejected(self, tmp_path: Path) -> None:
        jarvis = Jarvis.persistent(tmp_path)
        with pytest.raises(ValueError):
            jarvis.note_open_question("   ")

    def test_database_backend_preserves_history(self, tmp_path: Path) -> None:
        first_run = Jarvis.database(tmp_path)
        first_run.note_open_question("why do the swallows return?")
        first_run.resolve_open_question(
            "why do the swallows return?", "they follow the warm winds north"
        )

        second_run = Jarvis.database(tmp_path)
        assert second_run.open_questions() == ()
        history = {
            item.question: item.status for item in second_run.unresolved_history()
        }
        assert history == {"why do the swallows return?": UnresolvedStatus.RESOLVED}
