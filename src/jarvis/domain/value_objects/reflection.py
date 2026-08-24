"""Reflection: something Jarvis notices about its own beliefs (Vision §19, §31).

Where Connect (Increment 74) links two beliefs that share an observation, Reflect
looks across the whole web and names a *pattern*: an observation that is
load-bearing -- one piece of evidence several beliefs all rest on. That is worth
noticing, because if that single observation is wrong, everything resting on it is
in doubt at once (the input to Challenge, later).

A Reflection *notices*, it does not conclude: it is a structured pointer to a
cluster (the shared observation and the beliefs it grounds), derived purely from
the evidence, asserting nothing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Reflection:
    """A load-bearing observation and the beliefs that rest on it."""

    observation: str  # the shared piece of evidence
    beliefs: tuple[str, ...]  # statements of the beliefs it grounds (two or more)

    @property
    def load(self) -> int:
        """How many beliefs rest on this single observation."""
        return len(self.beliefs)

    def describe(self) -> str:
        return (
            f'The observation "{self.observation}" is load-bearing — '
            f"{self.load} of my beliefs rest on it."
        )
