"""Guard: the documented public surface of Jarvis stays present and callable.

A cheap tripwire against silent removal or renaming of a public method. It checks
existence and callability only -- behaviour is covered by the focused test modules.
"""

from __future__ import annotations

from jarvis import Jarvis

# Grouped as the README Vocabulary presents them; keep the two in sync.
_PUBLIC_METHODS = (
    # Perceive
    "perceive",
    "perceive_all",
    "perceive_about_companion",
    "perceive_all_about_companion",
    "ask_about",
    "resolve",
    # Reason
    "think",
    "consider",
    # Connect / Reflect / Hypothesise
    "connections",
    "related_beliefs",
    "reflect",
    "hypothesise",
    # Act & learn
    "act",
    "record_outcome",
    "belief_about_action",
    "recommend_action",
    "recommend_action_by_description",
    # Model of itself
    "observe_self",
    "observe_overconfidence",
    "observe_prediction_accuracy",
    "self_beliefs",
    "feel_curious",
    "pursue",
    "introspect",
    "state_summary",
    # Goals & relationship
    "recurring_goals",
    "reflection_effort",
    "mark_goal_reached",
    "belief_about_goal",
    "sub_goals",
    "goal_progress",
    "stuck_goals",
    "ask_for_help",
    "receive_help",
    # Model of its companion
    "observe_companion",
    "acknowledge_companion",
    "explain_companion",
    # Memory & provenance
    "trace_of",
    "trace",
)


def test_all_documented_public_methods_are_callable() -> None:
    jarvis = Jarvis()
    for name in _PUBLIC_METHODS:
        attribute = getattr(jarvis, name, None)
        assert attribute is not None, f"missing public method: {name}"
        assert callable(attribute), f"public attribute not callable: {name}"


def test_persistent_constructor_exists() -> None:
    assert callable(Jarvis.persistent)
