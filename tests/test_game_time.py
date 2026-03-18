"""
Tests for src/game_time.py — the in-game clock and calendar.

Covers: advancement, calendar properties, time-of-day classification,
lunar phases, serialization, and the from_date factory.
"""
import pytest
from src.game_time import GameClock, DAYS_PER_MONTH, DAYS_PER_YEAR


# ── Basic clock behaviour ──────────────────────────────────────────


class TestBasicClock:

    def test_initial_time_is_noon(self):
        c = GameClock()
        assert c.hour == 12
        assert c.minute == 0

    def test_advance_increases_total_minutes(self):
        c = GameClock()
        c.advance(10)
        assert c.total_minutes == 10

    def test_advance_default_is_10_minutes(self):
        c = GameClock()
        c.advance()
        assert c.total_minutes == 10

    def test_time_str_format_at_noon(self):
        c = GameClock()
        assert c.time_str == "12:00PM"

    def test_time_str_format_at_midnight(self):
        # Advance from noon (12:00) by 12 hours to reach midnight
        c = GameClock()
        c.advance(12 * 60)
        assert c.hour == 0
        assert c.time_str == "12:00AM"


# ── Calendar ───────────────────────────────────────────────────────


class TestCalendar:

    def test_day_1_month_1_year_1(self):
        c = GameClock()
        assert c.year == 1
        assert c.month_index == 0
        assert c.month_name == "January"
        assert c.day_of_month == 1

    def test_day_of_week_starts_sunday(self):
        c = GameClock()
        assert c.day_of_week == "Sunday"
        assert c.day_abbrev == "SUN"

    def test_advance_one_day(self):
        c = GameClock()
        c.advance(24 * 60)  # 1 day
        assert c.day_of_month == 2
        assert c.day_of_week == "Monday"

    def test_advance_one_month(self):
        c = GameClock()
        c.advance(DAYS_PER_MONTH * 24 * 60)
        assert c.month_index == 1
        assert c.month_name == "February"

    def test_advance_one_year(self):
        c = GameClock()
        c.advance(DAYS_PER_YEAR * 24 * 60)
        assert c.year == 2
        assert c.month_index == 0
        assert c.day_of_month == 1

    def test_date_str_format(self):
        c = GameClock()
        assert c.date_str == "JAN 1 SUN"

    def test_full_str_format(self):
        c = GameClock()
        assert c.full_str == "JAN 1 SUN 12:00PM"


# ── Time-of-day classification ─────────────────────────────────────


class TestTimeOfDay:

    def test_noon_is_day(self):
        c = GameClock()
        assert c.is_day is True
        assert c.is_night is False

    def test_night(self):
        c = GameClock()
        c.advance(9 * 60)  # noon + 9h = 9 PM
        assert c.hour == 21
        assert c.is_night is True
        assert c.is_day is False

    def test_dawn(self):
        # From noon, advance 17 hours to 5 AM next day
        c = GameClock()
        c.advance(17 * 60)
        assert c.hour == 5
        assert c.is_dawn is True

    def test_dusk(self):
        # From noon, advance 7 hours to 7 PM
        c = GameClock()
        c.advance(7 * 60)
        assert c.hour == 19
        assert c.is_dusk is True


# ── Lunar phases ───────────────────────────────────────────────────


class TestLunarPhases:

    def test_initial_phase(self):
        c = GameClock()
        assert 0 <= c.lunar_phase_index <= 7
        assert isinstance(c.lunar_phase_name, str)

    def test_full_cycle_returns_to_same_phase(self):
        c = GameClock()
        initial = c.lunar_phase_index
        c.advance(DAYS_PER_MONTH * 24 * 60)  # one full cycle
        assert c.lunar_phase_index == initial

    def test_half_cycle_different_phase(self):
        c = GameClock()
        initial = c.lunar_phase_index
        c.advance(14 * 24 * 60)  # half month
        assert c.lunar_phase_index != initial


# ── from_date factory ──────────────────────────────────────────────


class TestFromDate:

    def test_roundtrip_default(self):
        c = GameClock.from_date()
        assert c.year == 1
        assert c.month_index == 0
        assert c.day_of_month == 1
        assert c.hour == 12
        assert c.minute == 0

    def test_specific_date(self):
        c = GameClock.from_date(year=2, month=3, day=15, hour=8, minute=30)
        assert c.year == 2
        assert c.month_name == "March"
        assert c.day_of_month == 15
        assert c.hour == 8
        assert c.minute == 30

    def test_from_date_january_first(self):
        c = GameClock.from_date(year=1, month=1, day=1, hour=12, minute=0)
        assert c.total_minutes == 0


# ── Serialization ──────────────────────────────────────────────────


class TestSerialization:

    def test_to_dict(self):
        c = GameClock(total_minutes=500)
        d = c.to_dict()
        assert d == {"total_minutes": 500}

    def test_from_dict(self):
        c = GameClock.from_dict({"total_minutes": 500})
        assert c.total_minutes == 500

    def test_roundtrip(self):
        c1 = GameClock(total_minutes=12345)
        c2 = GameClock.from_dict(c1.to_dict())
        assert c1.total_minutes == c2.total_minutes
        assert c1.full_str == c2.full_str

    def test_from_dict_missing_key_defaults_to_zero(self):
        c = GameClock.from_dict({})
        assert c.total_minutes == 0
