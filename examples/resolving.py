"""Hearing a contradiction, asking, and resolving it (no LLM involved).

Run from the repo root:

    PYTHONPATH=src python examples/resolving.py

This walks the full epistemic-social loop of Increments 70-71: Jarvis perceives a
self-contradicting exchange, which grounds a *contested* belief (it leans neither
way); the tension makes it curious; it asks the companion, naming both sides it
heard; the companion answers; that answer is taken as evidence and tips the
belief; and the tension is gone. Nothing is asserted -- confidence is derived
throughout, and the belief remains revisable.
"""

from __future__ import annotations

from jarvis import Jarvis


def main() -> None:
    jarvis = Jarvis()
    topic = "is the base case right?"

    print("== perceive a self-contradicting exchange ==")
    episode = jarvis.perceive_all(
        [
            "the base case is definitely right",
            "actually the base case is definitely not right",
        ],
        trigger=topic,
    )
    print(" conclusion:", episode.result)

    print("\n== the tension makes Jarvis curious ==")
    impulse = jarvis.feel_curious()
    assert impulse is not None
    print(" curious:", impulse.trigger)

    print("\n== so it asks the companion, naming both sides ==")
    print(" ", jarvis.ask_about(topic))

    print("\n== the companion answers; the answer is taken as evidence ==")
    belief = jarvis.resolve(topic, "I checked it myself — the base case is correct")
    assert belief is not None
    print(" resolved confidence:", round(belief.confidence.value, 2))

    print("\n== the tension is gone ==")
    print(" still curious?:", jarvis.feel_curious())
    print(" still asking? :", jarvis.ask_about(topic))


if __name__ == "__main__":
    main()
