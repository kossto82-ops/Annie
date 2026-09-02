"""RegistryModelComparator: a ModelComparator over Jarvis's LLM registry.

Gathers N models' blind replies to one prompt (Vision §33, §38). Each named model is
a :class:`LanguageModel` -- built from the open provider registry
(:mod:`jarvis.infrastructure.language_model_registry`) -- and every reply comes back
as a :class:`ModelRun` carrying the model that produced it.

Blind evaluation means the *use* is un-biased, and that is kept honest here: this
source returns text only. It never ranks, scores, or picks a "best" reply; turning
the runs into evidence, or synthesising over them, is the cognitive core's job (D6).
Each run names its model, so provenance survives and nothing is ever hidden.

Network stays out of the seam exactly like the other sources: whichever
:class:`LanguageModel` the caller injected does its own I/O (injectable transport),
so offline tests hand in a stub and never touch the wire (D7, D8).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from jarvis.domain.services.model_compare import ModelRun
from jarvis.infrastructure.language_model import LanguageModel


class RegistryModelComparator:
    """Compares a known set of language models by calling each with one prompt."""

    def __init__(self, models: Mapping[str, LanguageModel]) -> None:
        if not models:
            raise ValueError("a model comparator needs at least one model")
        self._models: Mapping[str, LanguageModel] = dict(models)

    def compare(
        self, prompt: str, *, models: Sequence[str] | None = None
    ) -> tuple[ModelRun, ...]:
        """Return one :class:`ModelRun` per model's reply to ``prompt``.

        ``models`` selects a subset by label; ``None`` compares all configured. A
        missing label or a failing model raises a clear error -- nothing is silently
        skipped or fabricated, so the compare stays an honest sample.
        """
        labels = tuple(models) if models is not None else tuple(self._models)
        runs: list[ModelRun] = []
        for label in labels:
            model = self._models.get(label)
            if model is None:
                raise ValueError(
                    f"unknown comparison model {label!r}; known: {', '.join(self._models)}"
                )
            try:
                response = model.complete(prompt)
            except Exception as exc:
                raise RuntimeError(
                    f"comparison model {label!r} failed on the prompt: {exc}"
                ) from exc
            runs.append(ModelRun(model=label, response=response))
        return tuple(runs)


def build_model_compare_source(
    models: Mapping[str, LanguageModel] | None = None,
) -> RegistryModelComparator | None:
    """Build a :class:`RegistryModelComparator` when models are configured, else None.

    ``None`` means "no model comparison configured" -- a Jarvis built from this
    simply has no blind-comparison capability and stays fully offline (D8). Passing
    a non-empty mapping opts in; an empty/``None`` mapping yields ``None``.
    """
    if not models:
        return None
    return RegistryModelComparator(models)