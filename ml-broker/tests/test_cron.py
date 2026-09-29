"""Unit tests for the scheduler's minimal cron parser.

Run from the repo root (no Docker, no DB):
    ~/venvs/lct-ml/bin/python -m pytest ml-broker/tests -q
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.cron import CronError, matches, next_after, parse

UTC = timezone.utc


def at(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# ---- parsing ---------------------------------------------------------------


def test_wildcard_fields():
    cron = parse("0 * * * *")
    assert cron.minutes == frozenset({0})
    assert cron.hours == frozenset(range(24))
    assert cron.days == frozenset(range(1, 32))
    assert cron.months == frozenset(range(1, 13))
    assert cron.weekdays == frozenset(range(7))
    assert not cron.days_restricted and not cron.weekdays_restricted


def test_lists_ranges_and_steps():
    cron = parse("1,5-7/2 */2 * * *")
    assert cron.minutes == frozenset({1, 5, 7})
    assert cron.hours == frozenset(range(0, 24, 2))


def test_bare_value_with_step_means_value_to_max():
    assert parse("0/15 * * * *").minutes == frozenset({0, 15, 30, 45})


def test_range_with_step():
    assert parse("0-30/10 * * * *").minutes == frozenset({0, 10, 20, 30})


def test_sunday_is_both_zero_and_seven():
    assert parse("0 0 * * 0").weekdays == parse("0 0 * * 7").weekdays == frozenset({0})
    assert parse("0 0 * * 5-7").weekdays == frozenset({0, 5, 6})


def test_restricted_flags_track_non_wildcard_fields():
    cron = parse("0 0 1 * *")
    assert cron.days_restricted and not cron.weekdays_restricted
    cron = parse("0 0 * * 1")
    assert not cron.days_restricted and cron.weekdays_restricted


@pytest.mark.parametrize(
    "expr",
    [
        "",
        "0 * * *",  # four fields
        "0 * * * * *",  # six fields
        "60 * * * *",  # minute 60
        "* 24 * * *",  # hour 24
        "* * 0 * *",  # day-of-month 0
        "* * * 13 *",  # month 13
        "* * * * 8",  # day-of-week 8
        "*/0 * * * *",  # zero step
        "5-1 * * * *",  # reversed range
        "0 0 * * MON",  # names are not supported
        "abc * * * *",
    ],
)
def test_rejects_bad_expressions(expr):
    with pytest.raises(CronError):
        parse(expr)


def test_rejects_non_string():
    with pytest.raises(CronError):
        parse(None)  # type: ignore[arg-type]


# ---- matching --------------------------------------------------------------


def test_matches_minute_precision():
    cron = parse("30 4 * * *")
    assert matches(cron, at(2026, 9, 29, 4, 30))
    assert not matches(cron, at(2026, 9, 29, 4, 31))
    assert not matches(cron, at(2026, 9, 29, 5, 30))


def test_either_day_field_matches_when_both_restricted():
    """Vixie rule: `0 0 1 * 1` fires on the 1st AND on every Monday."""
    cron = parse("0 0 1 * 1")
    assert matches(cron, at(2026, 10, 1))  # Thursday the 1st
    assert matches(cron, at(2026, 10, 5))  # a Monday, not the 1st
    assert not matches(cron, at(2026, 10, 6))  # Tuesday the 6th


def test_day_restricted_weekday_wildcard_fires_only_that_day():
    cron = parse("0 0 1 * *")
    assert matches(cron, at(2026, 10, 1))
    assert not matches(cron, at(2026, 10, 5))


# ---- next_after ------------------------------------------------------------


def test_next_after_hourly():
    assert next_after(parse("0 * * * *"), at(2026, 9, 29, 6, 30)) == at(2026, 9, 29, 7, 0)


def test_next_after_quarter_hour():
    assert next_after(parse("*/15 * * * *"), at(2026, 9, 29, 6, 31)) == at(2026, 9, 29, 6, 45)


def test_next_after_is_strictly_after():
    """The current minute is never returned, or a job would re-fire forever."""
    assert next_after(parse("30 4 * * *"), at(2026, 9, 29, 4, 30)) == at(2026, 9, 30, 4, 30)


def test_next_after_daily_rolls_to_the_next_day():
    assert next_after(parse("30 4 * * *"), at(2026, 9, 29, 6, 30)) == at(2026, 9, 30, 4, 30)


def test_next_after_crosses_a_month_boundary():
    assert next_after(parse("0 0 1 * *"), at(2026, 9, 29, 12, 0)) == at(2026, 10, 1)


def test_next_after_weekday_zero_is_sunday():
    nxt = next_after(parse("0 0 * * 0"), at(2026, 1, 31, 12, 0))
    assert nxt == at(2026, 2, 1)
    assert nxt.weekday() == 6  # Python numbers Sunday 6


def test_next_after_uses_the_either_day_rule():
    """From Tue 2026-09-29 the next `1st or Monday` is Thu Oct 1, not Mon Oct 5."""
    assert next_after(parse("0 0 1 * 1"), at(2026, 9, 29, 12, 0)) == at(2026, 10, 1)


def test_next_after_keeps_the_timezone():
    moment = next_after(parse("0 12 * * *"), at(2026, 9, 29, 6, 0))
    assert moment.tzinfo is not None
    assert moment - at(2026, 9, 29, 6, 0) == timedelta(hours=6)


def test_next_after_requires_tz_aware_input():
    with pytest.raises(CronError):
        next_after(parse("0 * * * *"), datetime(2026, 9, 29, 6, 30))


def test_expression_that_never_fires_is_reported_not_looped():
    """31 February parses fine but can never fire: bounded search, clear error."""
    with pytest.raises(CronError):
        next_after(parse("30 4 31 2 *"), at(2026, 9, 29))
