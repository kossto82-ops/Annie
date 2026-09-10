"""Cron schedules: plain-text validation and next-run computation (Odysseus #7).

A task's ``cron`` is five whitespace-separated fields (minute hour day month
weekday) in the standard shape: ``*``, ``*/n``, ``a-b``, ``a-b/n``, lists and
numbers, with month/weekday names accepted (``JAN``–``DEC``, ``MON``–``SUN``,
case-insensitive; Sunday is 0 or 7). An empty string means "no schedule" and is
always valid. Anything else is a clear :class:`ValueError` naming the field and
what was expected -- never a silent mis-schedule.

:func:`next_run_after` walks forward minute by minute (capped at one year, then
``None``) with the usual day match: day-of-month OR day-of-week when both are
restricted, AND otherwise. Pure date math, deterministic and offline.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}
_WEEKDAYS = {
    "MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6, "SUN": 0,
}
# (field name, minimum, maximum, name table or None)
_FIELDS: tuple[tuple[str, int, int, dict[str, int] | None], ...] = (
    ("minute", 0, 59, None),
    ("hour", 0, 23, None),
    ("day", 1, 31, None),
    ("month", 1, 12, _MONTHS),
    ("weekday", 0, 7, _WEEKDAYS),
)
_MAX_STEPS = 366 * 24 * 60  # give up after about a year of minutes


def _expand_names(field: str, names: dict[str, int] | None) -> str:
    """Replace month/weekday names with their numbers (upper-cased first)."""
    text = field.upper()
    if names:
        for word, number in names.items():
            text = text.replace(word, str(number))
    return text


def _parse_field(raw: str, name: str, low: int, high: int) -> set[int]:
    """The matching values of one cron field, or a clear error."""
    values: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"cron {name} has an empty list item in {raw!r}")
        step = 1
        if "/" in part:
            base, _, step_raw = part.partition("/")
            try:
                step = int(step_raw)
            except ValueError:
                raise ValueError(
                    f"cron {name} has a bad step in {part!r} (expected '/n')"
                ) from None
            if step < 1:
                raise ValueError(f"cron {name} has a bad step in {part!r} (n >= 1)")
            part = base
        if part in ("", "*"):
            start, end = low, high
        elif "-" in part:
            first, _, last = part.partition("-")
            try:
                start, end = int(first), int(last)
            except ValueError:
                raise ValueError(
                    f"cron {name} has a bad range in {part!r}"
                ) from None
        else:
            try:
                start = end = int(part)
            except ValueError:
                raise ValueError(
                    f"cron {name} has a bad value in {part!r}"
                ) from None
        if start < low or end > high or start > end:
            raise ValueError(
                f"cron {name} value {part!r} is outside {low}-{high}"
            )
        values.update(range(start, end + 1, step))
    return values


def parse_cron(cron: str) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    """Parse five cron fields into matching-value sets, or raise clearly."""
    parts = cron.split()
    if len(parts) != 5:
        raise ValueError(
            f"cron {cron!r} is not valid: expected 5 fields "
            "(minute hour day month weekday), e.g. '0 9 * * *'"
        )
    parsed: list[set[int]] = []
    for raw, (name, low, high, names) in zip(parts, _FIELDS, strict=True):
        parsed.append(_parse_field(_expand_names(raw, names), name, low, high))
    minutes, hours, days, months, weekdays = parsed
    if 7 in weekdays:  # Sunday may be written as 7; the clock reads 0-6.
        weekdays = (weekdays | {0}) - {7}
    return minutes, hours, days, months, weekdays


def _is_open(raw: str) -> bool:
    """Whether a raw cron field is unrestricted (exactly ``*``)."""
    return raw.strip() == "*"


def validate_cron(cron: str) -> None:
    """Accept an empty (unscheduled) or well-formed cron, else a clear error."""
    if not cron.strip():
        return
    parse_cron(cron)


def _day_matches(
    candidate: datetime,
    days: set[int],
    months: set[int],
    weekdays: set[int],
    *,
    dom_open: bool,
    dow_open: bool,
) -> bool:
    """Day match with the usual OR rule for two restricted day fields."""
    if candidate.month not in months:
        return False
    dom_hit = candidate.day in days
    if dom_open and dow_open:
        return True
    if dom_open:
        return (candidate.weekday() + 1) % 7 in weekdays
    if dow_open:
        return dom_hit
    return dom_hit or (candidate.weekday() + 1) % 7 in weekdays


def next_run_after(cron: str, after: datetime) -> datetime | None:
    """The next minute matching ``cron`` strictly after ``after`` (UTC kept).

    ``None`` for an empty cron (unscheduled) or when nothing matches within
    about a year (e.g. February 30th). Never raises on a valid cron.
    """
    if not cron.strip():
        return None
    parts = cron.split()
    minutes, hours, days, months, weekdays = parse_cron(cron)
    dom_open = _is_open(parts[2])
    dow_open = _is_open(parts[4])
    candidate = (after.astimezone(UTC).replace(second=0, microsecond=0)
                 + timedelta(minutes=1))
    for _ in range(_MAX_STEPS):
        if (
            candidate.minute in minutes
            and candidate.hour in hours
            and _day_matches(
                candidate, days, months, weekdays,
                dom_open=dom_open, dow_open=dow_open,
            )
        ):
            return candidate
        candidate += timedelta(minutes=1)
    return None
