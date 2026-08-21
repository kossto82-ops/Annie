"""An end-to-end tour of Jarvis's cognitive loop (no LLM involved).

Run from the repo root:

    PYTHONPATH=src python examples/main_loop.py

It exercises the main verbs: reason from evidence, model the companion, weigh
competing explanations, act and learn from the outcome, then introspect.
"""

from __future__ import annotations

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def evidence(content: str, weight: float, *, supports: bool = True) -> Evidence:
    return Evidence(
        content=content,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(weight),
        supports=supports,
    )


def main() -> None:
    jarvis = Jarvis()

    print("== reason from evidence ==")
    question = "Does my companion prefer simplicity?"
    print(" no evidence :", jarvis.think(question).result)
    grounded = jarvis.think(
        question,
        evidence=[
            evidence("chose the simpler design", 0.9),
            evidence("said: I do not want another assistant", 0.8),
        ],
    )
    print(" grounded    :", grounded.result)

    print("\n== model the companion ==")
    trait = "prefers simplicity"
    jarvis.observe_companion(trait, evidence("chose the simpler design", 0.9))
    jarvis.observe_companion(trait, evidence("asked for advanced mode", 0.6, supports=False))
    print(" ", jarvis.explain_companion(trait))

    print("\n== weigh competing explanations ==")
    result = jarvis.consider(
        "My companion went quiet mid-project",
        {
            "they are busy": [evidence("came back the next day", 0.8)],
            "they lost interest": [
                evidence("kept engaging elsewhere", 0.4, supports=False)
            ],
        },
    )
    print(" leading:", result.leading)

    print("\n== act, then learn from the outcome ==")
    action = jarvis.act("send the weekly summary", expected="the companion reads it")
    jarvis.record_outcome(action, actual="they read it", met_expectation=True)
    print(" recommendation next time:", jarvis.recommend_action(action).stance.value)

    print("\n== introspect ==")
    print(jarvis.introspect())


if __name__ == "__main__":
    main()
