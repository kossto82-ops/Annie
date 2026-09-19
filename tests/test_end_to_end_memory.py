"""End-to-end memory across a real restart (the reported failure, P1).

"Le cuento algo hoy, reinicio, y mañana pregunto sin repetirlo" -- the thing
must be *stored when said*, survive a real restart of the runtime, and surface
in an indirect follow-up question. Nothing here is mocked: every assertion runs
through ``handle(jarvis, "say", …)`` on the *database* composition (the shipped
SQLite path, D10) with the default offline voice, and session B is a brand-new
Jarvis built on the same directory -- the same as closing and reopening the app.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.interface.command_center import handle
from jarvis.jarvis import Jarvis


def _say(jarvis: Jarvis, text: str) -> dict[str, object]:
    return handle(jarvis, "say", {"text": text})


class TestMemorySurvivesTheRestart:
    def test_a_fact_told_today_surfaces_in_an_indirect_question_tomorrow(
        self, tmp_path: Path
    ) -> None:
        # Today (session A): the companion states a plan. No "remember", no
        # fixtures -- the everyday sentence is the teach.
        session_a = Jarvis.database(tmp_path)
        stated = "Voy a crear Jarvis para que sea mi compañero."
        _say(session_a, stated)
        assert session_a.episodes.history()
        assert session_a.beliefs.all_beliefs()
        assert [t.statement for t in session_a.companion.beliefs()] == [stated]

        # Restart: a brand-new runtime on the same database.
        session_b = Jarvis.database(tmp_path)
        assert len(session_b.episodes.history()) == 1
        assert [t.statement for t in session_b.companion.beliefs()] == [stated]

        # Tomorrow (session B): the companion asks *indirectly*, without restating the
        # fact. Jarvis answers from memory.
        result = _say(session_b, "What exactly am I trying to build?")
        assert result["stance"] == "memory"
        assert stated in str(result["reply"])

    def test_a_decision_about_jarvis_survives_and_guides_an_indirect_answer(
        self, tmp_path: Path
    ) -> None:
        session_a = Jarvis.database(tmp_path)
        decision = (
            "Para Jarvis no quiero un robot que esté ahí y ya, quiero un "
            "compañero que tenga una vida interior. Cuando yo digo compañero, "
            "quiero decir alguien con conciencia percibida."
        )
        _say(session_a, decision)

        session_b = Jarvis.database(tmp_path)
        result = _say(
            session_b,
            "¿Cómo quieres que te responda cuando tengas razón o cuando creas "
            "que estoy equivocado?",
        )
        assert result["stance"] == "memory"
        reply = str(result["reply"])
        assert "no quiero un robot" in reply
        assert "conciencia percibida" in reply

    def test_who_i_am_survives_and_answers_a_question_without_restating(
        self, tmp_path: Path
    ) -> None:
        # Session A states identity as an ordinary sentence, "as if just talking".
        session_a = Jarvis.database(tmp_path)
        _say(session_a, "Me llamo Raúl.")

        # After the restart the name comes back from memory, not from the prompt
        # or the ephemeral session.
        session_b = Jarvis.database(tmp_path)
        result = _say(session_b, "¿Cuál es mi nombre?")
        assert result["stance"] == "memory"
        assert "Raúl" in str(result["reply"])