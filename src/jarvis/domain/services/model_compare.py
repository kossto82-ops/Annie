"""ModelCompare: blind evaluation of language models (Vision §33, §38).

Jarvis should not depend on any single model's personality or opinions (Vision §33);
one honest way to keep that check is to ask several models the *same* question and
reason over what they agree or disagree on. This is the seam for that:

* :class:`ModelRun` -- one model's blind reply to a prompt, kept as a small
  immutable value object.
* :class:`ModelComparator` -- the capability that gathers the replies.

Because each reply is only ever *candidate evidence* (D6: the LLM extracts, it does
not judge), a comparator deliberately:

* **Gathers, never concludes.** It returns each reply as text plus the model that
  produced it. It does not rank them, pick a "best", or synthesise a verdict.
* **Keeps provenance.** Each run names its model, so Jarvis can attribute a
  response -- and later weigh it -- without hiding where it came from.
* **Writes nothing.** Comparing does not write to memory, beliefs, or stores.

Blindness lives in *how the runs are used*: the core reasons over the replies as
evidence, not over the prestige of a model name. The seam itself stays neutral, so
the same total can serve a surface ("compare") or a future cognitive step
("synthesise") without changing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelRun:
    """One model's blind reply to a comparison prompt (candidate evidence)."""

    model: str
    response: str

    def __post_init__(self) -> None:
        if not self.model or not self.model.strip():
            raise ValueError("a ModelRun requires a non-empty model label")


@runtime_checkable
class ModelComparator(Protocol):
    """Gathers several language models' blind replies to one prompt."""

    def compare(
        self, prompt: str, *, models: Sequence[str] | None = None
    ) -> tuple[ModelRun, ...]:
        """Return one :class:`ModelRun` per model's reply to ``prompt``.

        ``models`` selects a subset of the comparator's known models; ``None`` asks
        for all of them. The runs are candidate evidence only: no ranking, no
        verdict, no writes. Raises when a named model is unknown or a reply fails.

        A model that returns empty text is an honest empty reply, kept as-is; a real
        failure of the underlying model raises so the compare never fabricates.
        """
        ...