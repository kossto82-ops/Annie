"""ResearchSource: the seam between Jarvis and deep research (Vision §38).

Deep research is broader than a single :class:`ExternalSource` lookup: it asks a
source to go *look in depth* at a question and come back with a structured
:class:`ResearchReport` -- a summary plus the cited documents behind it rather
than one flat answer page.

This domain Protocol mirrors :class:`ExternalSource` and :class:`PerceptionSource`
(Vision §32, §38): it is the *capability* that gathers external material, and it
deliberately does not decide anything:

* It runs the plan-as-asked: it searches, retrieves, summarises and returns
  candidates carrying provenance.
* It does not weigh beliefs, assert facts, derive confidence, or decide when the
  investigation is *conclusive*.
* Turning the gathered documents into standing evidence, and reasoning over the
  whole report, stays in the cognitive core (D6).

A `ResearchSource` *gathers*; it is not a mind. Its report must never write to
Jarvis's beliefs or memory directly. The summary it produces is a plain-language
description of *what was found*, never a conclusion about what is true.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jarvis.domain.value_objects.research_report import ResearchReport


@runtime_checkable
class ResearchSource(Protocol):
    """Gives Jarvis in-depth investigation of a question, as a structured report."""

    def deep_research(self, query: str, *, depth: int = 1) -> ResearchReport:
        """Investigate ``query`` in depth and return a structured report.

        ``depth`` scales how much effort the source should invest (more queries,
        more documents). The returned :class:`ResearchReport` always carries its
        cited documents so the core can weigh each one; the summary is a
        plain-language account of what was found, never a verdict.

        Raises only on a real failure of the underlying source, so the absence of
        findings is reported honestly inside the (possibly sparse) report rather
        than as an exception.
        """
        ...