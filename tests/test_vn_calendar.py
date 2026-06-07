"""VN trading calendar: weekends, fixed holidays, Tet, and unknown-year safety."""

import unittest
from datetime import date

import pytest

from tradingagents.dataflows.vn_calendar import (
    UnknownTetYearError,
    is_trading_day,
    tet_dates,
    vn_holidays,
)


@pytest.mark.unit
class VNCalendarTests(unittest.TestCase):
    def test_normal_weekday_is_trading_day(self):
        self.assertTrue(is_trading_day(date(2024, 6, 3)))   # Monday
        self.assertTrue(is_trading_day("2026-02-23"))        # post-Tet Monday

    def test_weekend_is_not_trading_day(self):
        self.assertFalse(is_trading_day(date(2024, 6, 1)))   # Saturday
        self.assertFalse(is_trading_day(date(2024, 6, 2)))   # Sunday

    def test_fixed_holidays_close_market(self):
        self.assertFalse(is_trading_day("2024-01-01"))       # New Year
        self.assertFalse(is_trading_day("2024-04-30"))       # Reunification
        self.assertFalse(is_trading_day("2024-05-01"))       # Labour
        self.assertFalse(is_trading_day("2024-09-02"))       # National Day

    def test_tet_closures_verified_years(self):
        self.assertFalse(is_trading_day(date(2024, 2, 12)))  # Tet 2024
        self.assertFalse(is_trading_day(date(2025, 1, 29)))  # Tet 2025
        self.assertFalse(is_trading_day(date(2026, 2, 18)))  # Tet 2026

    def test_tet_set_bounds(self):
        self.assertEqual(min(tet_dates(2024)), date(2024, 2, 8))
        self.assertEqual(max(tet_dates(2024)), date(2024, 2, 14))

    def test_vn_holidays_union(self):
        h = vn_holidays(2026)
        self.assertIn(date(2026, 4, 30), h)
        self.assertIn(date(2026, 2, 16), h)

    def test_unknown_year_raises_not_guesses(self):
        with self.assertRaises(UnknownTetYearError):
            tet_dates(2099)
        with self.assertRaises(UnknownTetYearError):
            is_trading_day(date(2099, 3, 3))


if __name__ == "__main__":
    unittest.main()
