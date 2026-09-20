"""End-to-end memory across a real restart (the reported failure, P1).

"Le cuento algo hoy, reinicio, y mañana pregunto sin repetirlo" -- the thing
must be *stored when said*, survive a real restart of the runtime, and surface
in an indirect follow-up question. Nothing here is mocked: every assertion runs
through ``handle(jarvis, "say", …)`` on the *database* composition (the shipped
SQLite path, D10) with the default offline voice, and session B is a brand-new
Jarvis built on the same directory -- the same as closing and reopening the app.

Increment 168 adds the semantic recall demonstration: a later question that
rephrases the memory, or asks in another language, still lands on the stored
meaning -- the offline concept channel (``CONCEPT_MAP``) bridges paraphrase and
language without any embeddings or hardcoded test phrases.
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


class TestSemanticRecallMemorizesMeaning:
    """Increment 168 -- Jarvis recalls the *meaning* of what was said.

    Every pair stores an ordinary sentence in session A and asks in session B a
    question that shares none of the keywords -- a paraphrase or another language.
    The answer must quote the right stored memory, never a wrong cousin.
    """

    # Test 1 -- same-language paraphrase.
    def test_same_language_paraphrase_still_finds_the_stored_meaning(
        self, tmp_path: Path
    ) -> None:
        session_a = Jarvis.database(tmp_path)
        stated = (
            "Estoy construyendo Jarvis porque quiero tener un compañero "
            "intelectual que recuerde nuestra historia."
        )
        _say(session_a, stated)

        session_b = Jarvis.database(tmp_path)
        result = _say(session_b, "¿Qué clase de sistema estoy intentando crear?")
        assert result["stance"] == "memory"
        assert stated in str(result["reply"])

    # Test 2 -- a decision about how Jarvis should correct the companion survives
    # a question that describes the situation instead of quoting the words.
    def test_a_contradiction_preference_is_recalled_by_the_situation(
        self, tmp_path: Path
    ) -> None:
        session_a = Jarvis.database(tmp_path)
        decision = (
            "No quiero que Jarvis me dé la razón automáticamente. Quiero que "
            "me contradiga cuando tenga argumentos."
        )
        _say(session_a, decision)

        session_b = Jarvis.database(tmp_path)
        result = _say(
            session_b,
            "¿Cómo quieres interactuar conmigo cuando creas que estoy equivocado?",
        )
        assert result["stance"] == "memory"
        assert "me contradiga" in str(result["reply"])

    # Test 3 -- the project's *purpose* is recalled through a change of framing
    # ("el propósito de Jarvis" vs. "un proyecto a largo plazo").
    def test_the_project_purpose_is_recalled_from_a_rephrased_question(
        self, tmp_path: Path
    ) -> None:
        session_a = Jarvis.database(tmp_path)
        stated = (
            "Jarvis es un proyecto a largo plazo. Quiero construir una "
            "inteligencia que conozca mi historia, recuerde lo que hacemos "
            "juntos y pueda crecer conmigo."
        )
        _say(session_a, stated)

        session_b = Jarvis.database(tmp_path)
        result = _say(session_b, "¿Cuál es el propósito de Jarvis?")
        assert result["stance"] == "memory"
        assert "proyecto a largo plazo" in str(result["reply"])

    # Test 4 -- Spanish memory, English question: new words, same meaning.
    def test_a_spanish_memory_answers_an_english_question(self, tmp_path: Path) -> None:
        session_a = Jarvis.database(tmp_path)
        stated = (
            "Estoy construyendo Jarvis como un compañero intelectual que "
            "recuerde nuestra historia."
        )
        _say(session_a, stated)

        session_b = Jarvis.database(tmp_path)
        result = _say(session_b, "What am I trying to build?")
        assert result["stance"] == "memory"
        assert stated in str(result["reply"])

    # Test 5 -- English memory, Spanish question: the decision clause is met by
    # meaning, not by the single shared word.
    def test_an_english_memory_answers_a_spanish_question(self, tmp_path: Path) -> None:
        session_a = Jarvis.database(tmp_path)
        stated = (
            "I want Jarvis to challenge me when my reasoning is wrong instead "
            "of simply agreeing with me."
        )
        _say(session_a, stated)

        session_b = Jarvis.database(tmp_path)
        result = _say(
            session_b,
            "¿Qué quieres hacer cuando pienses que estoy equivocado?",
        )
        assert result["stance"] == "memory"
        assert stated in str(result["reply"])

    # Test 6 -- false-positive isolation: among several first-person memories
    # about different topics, only the one that means what was asked is used.
    def test_a_specific_question_isolates_its_own_memory(self, tmp_path: Path) -> None:
        session_a = Jarvis.database(tmp_path)
        others = [
            "Quiero construir Jarvis, mi propio asistente.",
            "Estoy investigando un viaje a Japón.",
            "Quiero que Jarvis me contradiga cuando sea necesario.",
        ]
        for memory in others:
            _say(session_a, memory)
        _say(session_a, "Quiero aprender programación.")

        session_b = Jarvis.database(tmp_path)
        result = _say(session_b, "¿Qué quiero aprender?")
        assert result["stance"] == "memory"
        reply = str(result["reply"])
        assert "aprender programación" in reply
        for wrong in ("mi propio asistente", "viaje a Japón", "me contradiga"):
            assert wrong not in reply

    # Test 7 -- a changed opinion resolves temporally: the newest stance becomes
    # the single current trait and the superseded one is archived as its
    # precedent (still honest history, no longer an answerable current decision).
    def test_a_changed_opinion_is_resolved_not_parallel(
        self, tmp_path: Path
    ) -> None:
        session_a = Jarvis.database(tmp_path)
        older = (
            "Quiero que Jarvis sea muy minimalista y no tenga demasiadas "
            "herramientas."
        )
        newer = (
            "He cambiado de opinión. Quiero que Jarvis pueda utilizar muchas "
            "herramientas y ejecutar tareas reales."
        )
        _say(session_a, older)
        _say(session_a, newer)

        # The change is first-class: one current trait carrying its own precedent,
        # never two parallel "current" decisions.
        (current,) = session_a.companion.beliefs()
        assert current.statement == (
            "Quiero que Jarvis pueda utilizar muchas herramientas y "
            "ejecutar tareas reales."
        )
        assert current.precedents == [older]
        assert len(current.evidence) == 2

        # Restart keeps the resolution: the superseded statement must not be
        # rehydrated as a parallel trait.
        session_b = Jarvis.database(tmp_path)
        (current_b,) = session_b.companion.beliefs()
        assert current_b.statement == current.statement
        assert current_b.precedents == [older]
        assert older in session_b.companion.superseded_texts()

        # A self-question about the decision answers with the current stance.
        result = _say(session_b, "¿Qué quieres que pueda hacer Jarvis?")
        assert result["stance"] == "memory"
        reply = str(result["reply"])
        assert "muchas herramientas" in reply
        assert "minimalista" not in reply

        # The earlier stance is honest history -- an archived episode, not a
        # current memory.
        assert older in [e.trigger for e in session_b.episodes.history()]

    # Test 8 -- temporal resolution survives a probe that quotes the superseded
    # words (even in another language): the archived stance never answers as
    # current.
    def test_a_superseded_stance_cannot_be_recalled_as_current(
        self, tmp_path: Path
    ) -> None:
        session_a = Jarvis.database(tmp_path)
        older = "Quiero que Jarvis sea minimalista, con pocas herramientas."
        newer = "I changed my mind. I want Jarvis to be able to use many tools."
        _say(session_a, older)
        _say(session_a, newer)
        session_b = Jarvis.database(tmp_path)
        (current,) = session_b.companion.beliefs()
        assert current.statement == "I want Jarvis to be able to use many tools."
        assert current.precedents == [older]
        assert older in session_b.companion.superseded_texts()
        candidates = [
            m.content
            for m in session_b.recall("wants Jarvis minimalist few tools")
        ]
        assert not any(
            older.strip().lower() == c.strip().lower() for c in candidates
        )

    # Test 9 -- re-affirming the current stance through a change-of-mind marker is
    # confirmation, not another revision: one statement, growing evidence, no
    # duplicate precedent recorded.
    def test_reaffirming_the_current_stance_is_confirmation_not_a_revision(
        self, tmp_path: Path
    ) -> None:
        session_a = Jarvis.database(tmp_path)
        stance = "Quiero que Jarvis use muchas herramientas para poder ayudarme mejor."
        _say(session_a, stance)
        _say(session_a, f"He cambiado de opinión. {stance}")
        (current,) = session_a.companion.beliefs()
        assert current.statement == stance
        assert current.precedents == []
        assert len(current.evidence) == 2
        assert session_a.companion.superseded_texts() == frozenset()