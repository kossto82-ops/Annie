"""A conversation becomes a grounded, revisable belief (no LLM involved).

Run from the repo root:

    PYTHONPATH=src python examples/conversation.py

This is the perception seam at conversation scale (Increments 63-68): a short
multi-line exchange is perceived all at once and grounds one belief, weaker and
contradicting lines pulling against stronger ones, and a line the perceiver makes
nothing of is silently skipped. A second exchange in a later "session" -- a fresh
persistent Jarvis on the same directory -- strengthens the belief across a
restart, showing perception and continuity together. The default perceiver is a
deliberately dumb keyword rule; a smarter one drops in behind the same Protocol.
"""

from __future__ import annotations

import tempfile

from jarvis import Jarvis


def _narrate(jarvis: Jarvis, trigger: str) -> str:
    belief = jarvis.beliefs.get_by_statement(f"Working conclusion about: {trigger}")
    return belief.explain().narrate() if belief is not None else "(no belief yet)"


def main() -> None:
    directory = tempfile.mkdtemp()
    question = "is my proof sound?"

    print("== session one: a first exchange ==")
    jarvis = Jarvis.persistent(directory)
    first = jarvis.perceive_all(
        [
            "the base case is definitely right",
            "the weather is lovely today",  # no cue -> skipped
            "the recursive step is clearly correct",
            "the edge cases are maybe not covered",  # a weaker doubt
        ],
        trigger=question,
    )
    print(" conclusion:", first.result)
    explanation = first.explain()
    assert explanation is not None
    print(" why       :", explanation.narrate())

    print("\n== what the exchange said about my companion ==")
    jarvis.perceive_all_about_companion(
        "values rigor",
        ["you definitely value rigor", "you clearly value rigor"],
    )
    print(" ", jarvis.explain_companion("values rigor"))

    print("\n== session two: same topic, later, after a restart ==")
    reopened = Jarvis.persistent(directory)
    print(" belief on reopen:", _narrate(reopened, question))
    second = reopened.perceive_all(
        ["the edge cases are definitely handled now"], trigger=question
    )
    print(" conclusion:", second.result)


if __name__ == "__main__":
    main()
