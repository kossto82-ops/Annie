"""DecidedScript: an already-decided multi-step act plan (Vision §28, 06_TOOLS_AGENCY).

Earned-agency execution decides *material* acts in the core and lets an executor
present them. The offline charitable executor never reasons (D4, D6): it can only
run *decided* multi-step acts, so a decided-script is that plan in a small
deterministic grammar — one tool-call per line, quote-aware ``key=value``
arguments:

    filesystem operation=write path="notas.txt" content="revisar el doc"
    echo text=hecho

Each line is ``tool_name key=value ...``; a value containing spaces is wrapped in
double quotes. ``parse`` validates shape only — it never runs anything, and lines
that do not parse are reported honestly instead of being fabricated. Whether a
step may *run* is the :class:`ToolRegistry` policy gate's decision, not this
document's.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass


def split_script_line(line: str) -> tuple[list[str], str | None]:
    """Split one script line into quote-aware tokens; an error when unparseable."""
    try:
        tokens = shlex.split(line, posix=True)
    except ValueError as exc:
        return [], f"cannot parse {line!r}: {exc}"
    if not tokens:
        return [], "empty line"
    return tokens, None


def script_arguments(tokens: list[str], line: str) -> tuple[dict[str, str], str | None]:
    """Turn ``key=value`` tokens into an argument dict, one ``=`` per token."""
    arguments: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            return {}, f"malformed argument {token!r} in {line!r}"
        key, _, value = token.partition("=")
        if not key:
            return {}, f"malformed argument {token!r} in {line!r}"
        arguments[key] = value
    return arguments, None


@dataclass(frozen=True, slots=True, kw_only=True)
class DecidedStep:
    """One tool-call of a decided script, without any interpretation."""

    tool: str
    arguments: tuple[tuple[str, str], ...]
    line: str

    def as_call(self) -> dict[str, str]:
        """The arguments as a plain mapping for the registry gate."""
        return dict(self.arguments)


@dataclass(frozen=True, slots=True)
class DecidedScript:
    """A parsed decided-script: valid steps plus honest parse errors.

    A malformed line is skipped charitably so the rest of the script can still
    run; every skipped line is reported in ``errors``. ``is_empty`` plus an error
    tuple means the text was *not* a decidable script — the honest decline.
    """

    steps: tuple[DecidedStep, ...]
    errors: tuple[str, ...] = ()

    @classmethod
    def parse(cls, text: str) -> DecidedScript:
        """Parse the script grammar without executing anything.

        Blank and ``#``-comment lines are skipped. Line order is preserved.
        """
        steps: list[DecidedStep] = []
        errors: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            tokens, error = split_script_line(line)
            if error is not None:
                errors.append(error)
                continue
            arguments, error = script_arguments(tokens[1:], line)
            if error is not None:
                errors.append(error)
                continue
            steps.append(
                DecidedStep(
                    tool=tokens[0],
                    arguments=tuple(arguments.items()),
                    line=line,
                )
            )
        return cls(steps=tuple(steps), errors=tuple(errors))

    @property
    def is_empty(self) -> bool:
        """No step survived parsing — nothing here is executable."""
        return not self.steps

    def unknown_tools(self, known: tuple[str, ...]) -> tuple[str, ...]:
        """Step tool names that ``known`` does not contain (ordering preserved)."""
        return tuple(step.tool for step in self.steps if step.tool not in known)