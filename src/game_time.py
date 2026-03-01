"""
Game timekeeping system.

Tracks elapsed game-time as total minutes from a fixed epoch.
Provides day-of-week, hour, minute, and 8-phase lunar cycle.

Default start: Sunday 12:00 PM (minute 0 of the epoch).
Each overworld step advances time by 10 minutes.
Full lunar cycle: 28 game-days.
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

# Duration of one full lunar cycle in minutes (28 days)
_LUNAR_CYCLE_MINUTES = 28 * 24 * 60

# Starting hour offset — epoch minute 0 = Sunday 12:00 PM
_START_HOUR = 12


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
        """Minutes since midnight Sunday (includes start-hour offset)."""
        return self.total_minutes + _START_HOUR * 60

    @property
    def day_index(self):
        """Days elapsed since epoch start (0-based)."""
        return self._absolute_minutes // (24 * 60)

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
        return (self._absolute_minutes % (24 * 60)) // 60

    @property
    def minute(self):
        """Current minute (0–59)."""
        return self._absolute_minutes % 60

    @property
    def time_str(self):
        """Formatted time string, e.g. 'SUN 12:00PM'."""
        h = self.hour
        m = self.minute
        period = "AM" if h < 12 else "PM"
        display_h = h % 12
        if display_h == 0:
            display_h = 12
        return f"{self.day_abbrev} {display_h}:{m:02d}{period}"

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
