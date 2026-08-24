"""Language in, cognition out: the perception seam (no LLM involved).

Run from the repo root:

    PYTHONPATH=src python examples/perceiving.py

Where the other tours hand Jarvis structured `Evidence`, this shows the seam
opened in Increments 63-64: a raw observation (a string) is turned into evidence
by a `PerceptionSource`, then reasoned over. The default perceiver is a
deliberately dumb keyword rule -- and because it sits behind a Protocol, a
smarter one (an LLM-backed perceiver, one day) drops in without the cognitive
core changing (Vision §32, §38). Perception only makes evidence; confidence is
still derived and the executive still decides.
"""

from __future__ import annotations

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def main() -> None:
    jarvis = Jarvis()

    print("== perceive raw observations ==")
    for observation in (
        "the approach is definitely sound",  # a cue -> grounds a belief
        "the base case is definitely not right",  # a negated cue -> contradicting
        "the weather is nice today",  # no cue -> honest silence
    ):
        episode = jarvis.perceive(observation)
        print(f"  {observation!r}\n    -> {episode.result}")

    print("\n== perceive things about the companion ==")
    trait = "prefers simplicity"
    jarvis.perceive_about_companion(trait, "you definitely prefer simplicity")
    jarvis.perceive_about_companion(trait, "you clearly prefer simplicity")
    print(" ", jarvis.explain_companion(trait))
    jarvis.perceive_about_companion(trait, "you definitely do not prefer simplicity")
    print(" after a perceived denial:", jarvis.explain_companion(trait))

    print("\n== a smarter perceiver is a drop-in ==")

    class UppercaseIsCertain:
        """A different rule entirely: an ALL-CAPS word means strong agreement."""

        def perceive(self, observation: str) -> tuple[Evidence, ...]:
            if not any(w.isupper() and w.isalpha() for w in observation.split()):
                return ()
            return (
                Evidence(
                    content=observation.strip(),
                    source=EvidenceSource.USER_STATEMENT,
                    weight=Confidence(1.0),
                ),
            )

    custom = Jarvis(perception=UppercaseIsCertain())
    print(" ", custom.perceive("this is TRUE").result)
    print(" ", custom.perceive("this is quiet").result)  # no caps -> silence


if __name__ == "__main__":
    main()
