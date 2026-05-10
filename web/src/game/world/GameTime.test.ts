import { describe, it, expect } from "vitest";
import {
  makeClock,
  advanceClock,
  clockFromDate,
  hour,
  minute,
  dayIndex,
  dayOfWeek,
  monthAbbrev,
  monthName,
  dayOfMonth,
  year,
  timeStr,
  dateStr,
  fullStr,
  isDay,
  isDusk,
  isDawn,
  isNight,
  lunarPhaseIndex,
  lunarPhaseName,
  clockDarknessParams,
  MINUTES_PER_DAY,
  MINUTES_PER_LUNAR_CYCLE,
  MINUTES_PER_STEP,
  DAYS_PER_YEAR,
} from "./GameTime";

describe("GameClock — derived calendar", () => {
  it("epoch 0 = Sunday, Jan 1, year 1, 12:00 PM", () => {
    const c = makeClock(0);
    expect(hour(c)).toBe(12);
    expect(minute(c)).toBe(0);
    expect(dayIndex(c)).toBe(0);
    expect(dayOfWeek(c)).toBe("Sunday");
    expect(monthAbbrev(c)).toBe("JAN");
    expect(monthName(c)).toBe("January");
    expect(dayOfMonth(c)).toBe(1);
    expect(year(c)).toBe(1);
    expect(timeStr(c)).toBe("12:00PM");
    expect(dateStr(c)).toBe("JAN 1 SUN");
    expect(fullStr(c)).toBe("JAN 1 SUN 12:00PM");
  });

  it("advances 5 minutes per step by default", () => {
    const c = makeClock(0);
    advanceClock(c);
    expect(minute(c)).toBe(5);
    expect(c.totalMinutes).toBe(MINUTES_PER_STEP);
  });

  it("rolls over hours / days correctly", () => {
    // 5 hours past noon → 5 PM Sunday.
    const c = makeClock(5 * 60);
    expect(hour(c)).toBe(17);
    expect(timeStr(c)).toBe("5:00PM");

    // 12 more hours → 5 AM Monday.
    advanceClock(c, 12 * 60);
    expect(hour(c)).toBe(5);
    expect(dayOfWeek(c)).toBe("Monday");
    expect(timeStr(c)).toBe("5:00AM");
  });

  it("rolls into a new month on the 28th day", () => {
    // 28 days after epoch noon → still noon, Sunday Jan 29? No — 28
    // days later we wrap to Feb 1. (Months are exactly 28 days.)
    const c = makeClock(28 * MINUTES_PER_DAY);
    expect(monthAbbrev(c)).toBe("FEB");
    expect(dayOfMonth(c)).toBe(1);
  });

  it("rolls into a new year after 336 days", () => {
    const c = makeClock(DAYS_PER_YEAR * MINUTES_PER_DAY);
    expect(year(c)).toBe(2);
    expect(monthAbbrev(c)).toBe("JAN");
    expect(dayOfMonth(c)).toBe(1);
  });
});

describe("time-of-day classification", () => {
  function clockAtHour(h: number): ReturnType<typeof makeClock> {
    // totalMinutes adjusted so that hour(c) === h. Epoch is 12:00 PM,
    // so we need (h - 12) * 60 (mod 24h) of forward time.
    let delta = (h - 12) * 60;
    if (delta < 0) delta += MINUTES_PER_DAY;
    return makeClock(delta);
  }

  it("isDay for 7 AM through 6 PM, exclusive of 19:00", () => {
    expect(isDay(clockAtHour(7))).toBe(true);
    expect(isDay(clockAtHour(12))).toBe(true);
    expect(isDay(clockAtHour(18))).toBe(true);
    expect(isDay(clockAtHour(19))).toBe(false);
  });

  it("isDusk for 19:00–19:59 only", () => {
    expect(isDusk(clockAtHour(19))).toBe(true);
    expect(isDusk(clockAtHour(20))).toBe(false);
    expect(isDusk(clockAtHour(18))).toBe(false);
  });

  it("isNight for 20:00–04:59", () => {
    expect(isNight(clockAtHour(20))).toBe(true);
    expect(isNight(clockAtHour(0))).toBe(true);
    expect(isNight(clockAtHour(4))).toBe(true);
    expect(isNight(clockAtHour(5))).toBe(false);
    expect(isNight(clockAtHour(19))).toBe(false);
  });

  it("isDawn for 5:00–6:59", () => {
    expect(isDawn(clockAtHour(5))).toBe(true);
    expect(isDawn(clockAtHour(6))).toBe(true);
    expect(isDawn(clockAtHour(7))).toBe(false);
    expect(isDawn(clockAtHour(4))).toBe(false);
  });
});

describe("lunar phase", () => {
  it("starts at New Moon at epoch 0", () => {
    const c = makeClock(0);
    expect(lunarPhaseIndex(c)).toBe(0);
    expect(lunarPhaseName(c)).toBe("New Moon");
  });

  it("advances through all 8 phases over a 28-day cycle", () => {
    const eighth = MINUTES_PER_LUNAR_CYCLE / 8;
    for (let i = 0; i < 8; i++) {
      const c = makeClock(i * eighth);
      expect(lunarPhaseIndex(c)).toBe(i);
    }
  });

  it("wraps around after a full cycle", () => {
    const c = makeClock(MINUTES_PER_LUNAR_CYCLE);
    expect(lunarPhaseIndex(c)).toBe(0);
  });
});

describe("clockDarknessParams", () => {
  function clockAtHour(h: number) {
    let delta = (h - 12) * 60;
    if (delta < 0) delta += MINUTES_PER_DAY;
    return makeClock(delta);
  }

  it("returns null during daytime", () => {
    expect(clockDarknessParams(clockAtHour(12))).toBeNull();
    expect(clockDarknessParams(clockAtHour(15))).toBeNull();
  });

  it("returns a low-opacity purple wash at dusk", () => {
    const p = clockDarknessParams(clockAtHour(19));
    expect(p?.tint).toBe(0x14082b);
    expect(p?.maxAlpha).toBeGreaterThan(0);
    expect(p?.maxAlpha).toBeLessThan(0.5);
  });

  it("returns a low-opacity warm wash at dawn", () => {
    const p = clockDarknessParams(clockAtHour(6));
    expect(p?.tint).toBe(0x28140a);
    expect(p?.maxAlpha).toBeGreaterThan(0);
    expect(p?.maxAlpha).toBeLessThan(0.5);
  });

  it("returns full black at night", () => {
    const p = clockDarknessParams(clockAtHour(22));
    expect(p?.tint).toBe(0);
    expect(p?.maxAlpha).toBe(1.0);
  });
});

describe("clockFromDate", () => {
  it("seeds the epoch when called with no fields", () => {
    const c = clockFromDate({});
    expect(c.totalMinutes).toBe(0);
    expect(hour(c)).toBe(12);
    expect(minute(c)).toBe(0);
    expect(year(c)).toBe(1);
    expect(monthAbbrev(c)).toBe("JAN");
    expect(dayOfMonth(c)).toBe(1);
  });

  it("round-trips a module's start_time block", () => {
    // The Dragon of Dagorn ships year 10, month 6 (June), day 1, noon.
    const c = clockFromDate({ year: 10, month: 6, day: 1, hour: 12, minute: 0 });
    expect(year(c)).toBe(10);
    expect(monthAbbrev(c)).toBe("JUN");
    expect(dayOfMonth(c)).toBe(1);
    expect(hour(c)).toBe(12);
    expect(minute(c)).toBe(0);
  });

  it("honours mid-day hour + minute", () => {
    // Year 2 / Jan 1 — comfortably past the year-1 epoch so 9:30 AM
    // is representable. Year 1's first day starts at the noon epoch
    // and clamps anything before it; downstream tests / authors are
    // expected to specify start dates after that boundary.
    const c = clockFromDate({ year: 2, month: 1, day: 1, hour: 9, minute: 30 });
    expect(hour(c)).toBe(9);
    expect(minute(c)).toBe(30);
    expect(timeStr(c)).toBe("9:30AM");
  });

  it("handles midnight and end-of-day rollover", () => {
    // Year 1 day 1 only spans noon→midnight (game epoch); pick day 2
    // so midnight on that day is fully representable in the clock.
    const cMidnight = clockFromDate({ year: 1, month: 1, day: 2, hour: 0, minute: 0 });
    expect(hour(cMidnight)).toBe(0);
    expect(timeStr(cMidnight)).toBe("12:00AM");
    const cLate = clockFromDate({ year: 1, month: 1, day: 1, hour: 23, minute: 59 });
    expect(hour(cLate)).toBe(23);
    expect(minute(cLate)).toBe(59);
  });

  it("rolls month boundaries correctly", () => {
    // Month 12, day 28 = last day of year. Make sure the calendar
    // getters resolve back to that.
    const c = clockFromDate({ year: 2, month: 12, day: 28, hour: 12, minute: 0 });
    expect(year(c)).toBe(2);
    expect(monthAbbrev(c)).toBe("DEC");
    expect(dayOfMonth(c)).toBe(28);
  });

  it("clamps out-of-range fields rather than crashing", () => {
    const c = clockFromDate({ year: 1, month: 99, day: 99, hour: 99, minute: 99 });
    // month clamps to 12, day to 28, hour to 23, minute to 59.
    expect(monthAbbrev(c)).toBe("DEC");
    expect(dayOfMonth(c)).toBe(28);
    expect(hour(c)).toBe(23);
    expect(minute(c)).toBe(59);
  });

  it("clamps below-minimum fields to the legal range", () => {
    // Field-level clamping pulls each value into its legal range.
    // The combined date (year 1, day 1, midnight) sits before the
    // game's noon epoch and is therefore unrepresentable — the clock
    // pins to the epoch (year 1, Jan 1 SUN, 12:00 PM) rather than
    // crashing. That's the intentional fallback for any time the
    // author specified before the epoch.
    const c = clockFromDate({ year: 0, month: 0, day: 0, hour: -1, minute: -1 });
    expect(year(c)).toBe(1);
    expect(monthAbbrev(c)).toBe("JAN");
    expect(dayOfMonth(c)).toBe(1);
    expect(c.totalMinutes).toBe(0);
    expect(hour(c)).toBe(12); // clamped to epoch noon (not midnight)
  });

  it("year 1 / Jan 1 / noon matches the epoch exactly", () => {
    const c = clockFromDate({ year: 1, month: 1, day: 1, hour: 12, minute: 0 });
    expect(c.totalMinutes).toBe(0);
  });
});
