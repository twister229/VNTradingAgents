"""Vietnamese market trading calendar (HOSE / HNX / UPCOM).

The agents' trading-day check is data-driven (a price row means the market
traded that day), so this module is a standalone helper for explicit validity
checks, look-ahead windowing, and labeling — not a replacement for that logic.

Tet (Lunar New Year) is the hard part: its Gregorian dates shift every year and
a wrong guess silently corrupts any date logic that depends on it. So the Tet
closures here are an explicit, maintained table derived from actual VN-Index
trading gaps (verified, not recalled). Years outside the table raise
``UnknownTetYearError`` rather than guessing — a loud failure beats a silent
wrong answer.

Maintenance: when a new year is needed, derive its Tet closure from the days
VN-Index has no trading row (or the official HOSE holiday announcement) and add
a row to ``_TET_CLOSURES``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Union

DateLike = Union[date, str]


class UnknownTetYearError(ValueError):
    """Raised when Tet dates are requested for a year not in the maintained table."""


# Tet (Lunar New Year) market closures, verified against VN-Index trading gaps.
# Each value is the inclusive (start, end) of the closure; weekends inside the
# range are covered by the weekday check anyway but are kept for completeness.
#   2024: Feb 8-14   (verified: VNINDEX has no rows Feb 8,9,12,13,14)
#   2025: Jan 27-31  (verified: trading stops after Jan 24, resumes Feb 3)
#   2026: Feb 16-20  (verified: VNINDEX has no rows Feb 16-20)
_TET_CLOSURES: dict[int, tuple[date, date]] = {
    2024: (date(2024, 2, 8), date(2024, 2, 14)),
    2025: (date(2025, 1, 27), date(2025, 1, 31)),
    2026: (date(2026, 2, 16), date(2026, 2, 20)),
}


def _coerce(d: DateLike) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return datetime.strptime(d, "%Y-%m-%d").date()


def tet_dates(year: int) -> set[date]:
    """Return the set of Tet closure dates for ``year``.

    Raises ``UnknownTetYearError`` for years not in the maintained table, so a
    silent wrong-year bug is impossible.
    """
    if year not in _TET_CLOSURES:
        raise UnknownTetYearError(
            f"Tet closure for {year} is not in the maintained table. "
            f"Add it to vn_calendar._TET_CLOSURES (derive from VN-Index trading "
            f"gaps or the official HOSE holiday announcement)."
        )
    start, end = _TET_CLOSURES[year]
    days = set()
    cur = start
    while cur <= end:
        days.add(cur)
        cur = date.fromordinal(cur.toordinal() + 1)
    return days


def _fixed_holidays(year: int) -> set[date]:
    """VN public holidays with fixed Gregorian dates that close the market.

    Hung Kings' Commemoration (10th day of the 3rd lunar month) is lunar and is
    intentionally omitted from the fixed set; add it to ``_TET_CLOSURES``-style
    tables if precise coverage is needed. The fixed-date set covers the
    market-closing national holidays:
      - Jan 1   New Year's Day
      - Apr 30  Reunification Day
      - May 1   International Labour Day
      - Sep 2   National Day
    """
    return {
        date(year, 1, 1),
        date(year, 4, 30),
        date(year, 5, 1),
        date(year, 9, 2),
    }


def vn_holidays(year: int) -> set[date]:
    """All known market-closing holidays for ``year`` (fixed + Tet)."""
    return _fixed_holidays(year) | tet_dates(year)


def is_trading_day(d: DateLike) -> bool:
    """True when the VN market is open on ``d`` (not a weekend or holiday).

    Raises ``UnknownTetYearError`` if ``d`` falls in a year with no Tet table
    entry, because the answer would otherwise be an unverified guess.
    """
    day = _coerce(d)
    if day.weekday() >= 5:  # Sat=5, Sun=6
        return False
    return day not in vn_holidays(day.year)
