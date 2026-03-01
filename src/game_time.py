"""
Game timekeeping system.

Tracks elapsed game-time as total minutes from a fixed epoch.
Provides day-of-week, day-of-month, month, hour, minute, and
8-phase lunar cycle.

Calendar follows the Britannian model:
  12 months of 28 days each (336 days per year).
  One full lunar cycle = 28 days = one month.

Default start: Sunday 12:00 PM, 1st of January (minute 0 of epoch).
Each overworld step advances time by 10 minutes.
"""

_DAYS_OF_WEEK = [
    "Sunday", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday",
]

_DAY_ABBREV = {
    "Sunday": "SUN", "Monday": "MON", "Tuesday": "TUE",
    "Wednesday": "WED", "Thursday": "THU", "Friday": "FRI",
    "Saturday": "SAT",
}

# Britannian months (standard names, as used in the Ultima series)
MONTHS = [
    "January", "February", "March", "April",
    "May", "June", "July", "August",
    "September", "October", "November", "December",
]

_MONTH_ABBREV = [
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
]

DAYS_PER_MONTH = 28
MONTHS_PER_YEAR = 12
DAYS_PER_YEAR = DAYS_PER_MONTH * MONTHS_PER_YEAR  # 336

LUNAR_PHASES = [
    "New Moon",
    "Waxing Crescent",
    "First Quarter",
    "Waxing Gibbous",
    "Full Moon",
    "Waning Gibbous",
    "Last Quarter",
    "Waning Crescent",
]

# Duration of one full lunar cycle in minutes (28 days = 1 month)
_LUNAR_CYCLE_MINUTES = DAYS_PER_MONTH * 24 * 60

# Starting hour offset — epoch minute 0 = Sunday 12:00 PM
_START_HOUR = 12

# Minutes in a day
_MINUTES_PER_DAY = 24 * 60


class GameClock:
    """Tracks game time as total elapsed minutes from epoch."""

    def __init__(self, total_minutes=0):
        self.total_minutes = total_minutes

    # ── time advancement ──────────────────────────────────────

    def advance(self, minutes=10):
        """Advance the clock by the given number of minutes."""
        self.total_minutes += minutes

    # ── derived properties ────────────────────────────────────

    @property
    def _absolute_minutes(self):
        """Minutes since midnight Sunday Jan 1 (includes start-hour offset)."""
        return self.total_minutes + _START_HOUR * 60

    @property
    def day_index(self):
        """Total days elapsed since epoch start (0-based)."""
        return self._absolute_minutes // _MINUTES_PER_DAY

    @property
    def day_of_week(self):
        """Current day name (e.g. 'Sunday')."""
        return _DAYS_OF_WEEK[self.day_index % 7]

    @property
    def day_abbrev(self):
        """Three-letter day abbreviation (e.g. 'SUN')."""
        return _DAY_ABBREV[self.day_of_week]

    @property
    def hour(self):
        """Current hour (0–23)."""
        return (self._absolute_minutes % _MINUTES_PER_DAY) // 60

    @property
    def minute(self):
        """Current minute (0–59)."""
        return self._absolute_minutes % 60

    # ── calendar (month / day-of-month / year) ────────────────

    @property
    def year(self):
        """Current year (1-based)."""
        return self.day_index // DAYS_PER_YEAR + 1

    @property
    def day_of_year(self):
        """Day within the current year (0-based)."""
        return self.day_index % DAYS_PER_YEAR

    @property
    def month_index(self):
        """Current month as 0-based index (0 = January)."""
        return self.day_of_year // DAYS_PER_MONTH

    @property
    def month_name(self):
        """Current month name (e.g. 'January')."""
        return MONTHS[self.month_index]

    @property
    def month_abbrev(self):
        """Three-letter month abbreviation (e.g. 'JAN')."""
        return _MONTH_ABBREV[self.month_index]

    @property
    def day_of_month(self):
        """Day within the current month (1-based)."""
        return (self.day_of_year % DAYS_PER_MONTH) + 1

    # ── formatted strings ─────────────────────────────────────

    @property
    def time_str(self):
        """Formatted time, e.g. '12:00PM'."""
        h = self.hour
        m = self.minute
        period = "AM" if h < 12 else "PM"
        display_h = h % 12
        if display_h == 0:
            display_h = 12
        return f"{display_h}:{m:02d}{period}"

    @property
    def date_str(self):
        """Formatted date, e.g. 'JAN 1 SUN'."""
        return f"{self.month_abbrev} {self.day_of_month} {self.day_abbrev}"

    @property
    def full_str(self):
        """Full date+time, e.g. 'JAN 1 SUN 12:00PM'."""
        return f"{self.date_str} {self.time_str}"

    # ── time-of-day classification ────────────────────────────

    @property
    def is_night(self):
        """True if between 8 PM and 5 AM."""
        return self.hour >= 20 or self.hour < 5

    @property
    def is_dawn(self):
        """True if between 5 AM and 7 AM."""
        return 5 <= self.hour < 7

    @property
    def is_dusk(self):
        """True if between 7 PM and 8 PM (19:00-20:00)."""
        return 19 <= self.hour < 20

    @property
    def is_day(self):
        """True if daytime (7 AM to 7 PM)."""
        return 7 <= self.hour < 19

    # ── lunar phase ───────────────────────────────────────────

    @property
    def lunar_phase_index(self):
        """Current lunar phase as an integer 0–7."""
        return int((self.total_minutes % _LUNAR_CYCLE_MINUTES)
                   / _LUNAR_CYCLE_MINUTES * 8) % 8

    @property
    def lunar_phase_name(self):
        """Current lunar phase as a human-readable string."""
        return LUNAR_PHASES[self.lunar_phase_index]

    # ── serialization ─────────────────────────────────────────

    def to_dict(self):
        """Serialize to a JSON-safe dict."""
        return {"total_minutes": self.total_minutes}

    @classmethod
    def from_dict(cls, data):
        """Reconstruct from a saved dict."""
        return cls(total_minutes=data.get("total_minutes", 0))
