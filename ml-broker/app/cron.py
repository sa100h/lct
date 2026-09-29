"""Minimal 5-field cron parsing for ``ml_schedule.cron_expr``.

The broker needs exactly two things: "is this schedule due?" and "when is its
next occurrence?" — which is a fraction of what a full cron library does, so
this module implements the standard 5-field grammar directly and stays
dependency-free:

    minute hour day-of-month month day-of-week

Supported per field: ``*``, ``*/step``, comma lists (``1,15``), ranges
(``1-5``), ranges with a step (``1-5/2``), a bare value with a step (``0/15``
= ``0-max/15``), and bare values. Names (``JAN``, ``MON``) are NOT supported —
``ml_schedule`` holds numeric expressions only.

Two deliberate Vixie-cron rules:

* day-of-week accepts 0-7 with both 0 and 7 meaning Sunday;
* when BOTH day-of-month and day-of-week are restricted, a date matches if
  EITHER matches (``0 0 1 * 1`` = the 1st of the month *and* every Monday).

All arithmetic is done on timezone-aware datetimes; a cron expression carries
no timezone of its own, so the caller supplies UTC (see
``SCHEDULER_TIMEZONE`` in the broker config).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

__all__ = ["CronError", "Cron", "parse", "matches", "next_after"]

_FIELD_BOUNDS = {
    # field index -> (name, min, max)
    0: ("minute", 0, 59),
    1: ("hour", 0, 23),
    2: ("day-of-month", 1, 31),
    3: ("month", 1, 12),
    4: ("day-of-week", 0, 7),
}

# A valid 5-field expression fires at least once every 4 years (the only way to
# exceed that is a day-of-month/day-of-week pair that never coincides, e.g.
# "30 4 31 2 *"), so the search is bounded instead of looping forever.
_MAX_SEARCH_DAYS = 366 * 4 + 1


class CronError(ValueError):
    """Raised for an expression this parser cannot honour."""


@dataclass(frozen=True)
class Cron:
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    # Restricted = the raw field was not exactly "*". Both day fields being
    # restricted triggers Vixie's "either day matches" rule.
    days_restricted: bool
    weekdays_restricted: bool


def _parse_field(raw: str, index: int) -> tuple[frozenset[int], bool]:
    name, low, high = _FIELD_BOUNDS[index]
    field = raw.strip()
    if not field:
        raise CronError(f"empty {name} field")
    restricted = field != "*"
    values: set[int] = set()
    for token in field.split(","):
        token = token.strip()
        if not token:
            raise CronError(f"empty item in {name} field: {raw!r}")
        step = 1
        body = token
        if "/" in token:
            body, _, step_raw = token.partition("/")
            try:
                step = int(step_raw)
            except ValueError:
                raise CronError(f"bad step in {name} field: {token!r}") from None
            if step < 1:
                raise CronError(f"step must be >= 1 in {name} field: {token!r}")
        if body == "*":
            start, end = low, high
        elif "-" in body:
            start_raw, _, end_raw = body.partition("-")
            try:
                start, end = int(start_raw), int(end_raw)
            except ValueError:
                raise CronError(f"bad range in {name} field: {token!r}") from None
        else:
            try:
                start = int(body)
            except ValueError:
                raise CronError(f"bad value in {name} field: {token!r}") from None
            # "a/step" means a..max, but a bare "a" is a single value.
            end = high if "/" in token else start
        if start < low or end > high or start > end:
            raise CronError(
                f"{name} out of range in {token!r}: expected {low}-{high}"
            )
        values.update(range(start, end + 1, step))
    if index == 4:
        # Vixie allows 7 as Sunday; normalise onto 0 so comparisons are simple.
        values = {0 if value == 7 else value for value in values}
    if not values:
        raise CronError(f"{name} field matches nothing: {raw!r}")
    return frozenset(values), restricted


def parse(expr: str) -> Cron:
    """Parse a 5-field cron expression. Raises :class:`CronError`."""
    if not isinstance(expr, str):
        raise CronError(f"cron expression must be a string, got {type(expr).__name__}")
    fields = expr.split()
    if len(fields) != 5:
        raise CronError(
            f"expected 5 fields (minute hour day-of-month month day-of-week), "
            f"got {len(fields)} in {expr!r}"
        )
    minutes, _ = _parse_field(fields[0], 0)
    hours, _ = _parse_field(fields[1], 1)
    days, days_restricted = _parse_field(fields[2], 2)
    months, _ = _parse_field(fields[3], 3)
    weekdays, weekdays_restricted = _parse_field(fields[4], 4)
    return Cron(
        minutes=minutes,
        hours=hours,
        days=days,
        months=months,
        weekdays=weekdays,
        days_restricted=days_restricted,
        weekdays_restricted=weekdays_restricted,
    )


def _cron_weekday(day: date) -> int:
    """date.weekday() is Mon=0..Sun=6; cron numbers Sun=0..Sat=6."""
    return (day.weekday() + 1) % 7


def _date_matches(cron: Cron, day: date) -> bool:
    if day.month not in cron.months:
        return False
    day_ok = day.day in cron.days
    weekday_ok = _cron_weekday(day) in cron.weekdays
    if cron.days_restricted and cron.weekdays_restricted:
        return day_ok or weekday_ok
    if cron.days_restricted:
        return day_ok
    if cron.weekdays_restricted:
        return weekday_ok
    return True


def matches(cron: Cron, moment: datetime) -> bool:
    """True when ``moment`` (to the minute) satisfies ``cron``."""
    return (
        moment.minute in cron.minutes
        and moment.hour in cron.hours
        and _date_matches(cron, moment.date())
    )


def next_after(cron: Cron, after: datetime) -> datetime:
    """First matching minute strictly after ``after``.

    ``after`` must be timezone-aware; the result carries the same timezone.
    Walks day by day (cheap) and only then over the matching hours/minutes, so
    a daily schedule costs a single loop iteration, not 1440.
    """
    if after.tzinfo is None:
        raise CronError("next_after needs a timezone-aware datetime")
    start = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    hours = sorted(cron.hours)
    minutes = sorted(cron.minutes)
    day = start.date()
    last_day = day + timedelta(days=_MAX_SEARCH_DAYS)
    while day <= last_day:
        if _date_matches(cron, day):
            midnight = datetime.combine(day, time.min, tzinfo=start.tzinfo)
            for hour in hours:
                for minute in minutes:
                    candidate = midnight.replace(hour=hour, minute=minute)
                    if candidate >= start:
                        return candidate
        day += timedelta(days=1)
    raise CronError("no matching time within 4 years; expression never fires")
