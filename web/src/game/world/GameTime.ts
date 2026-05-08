/**
 * Game timekeeping — port of `src/game_time.py`.
 *
 * The clock stores a single `totalMinutes` counter (minutes since the
 * epoch start). All other readouts — hour, day, lunar phase, etc. —
 * are derived. Each overworld step advances 5 minutes.
 *
 * Calendar:
 *   - 12 months × 28 days each = 336 days/year (Britannian model)
 *   - One full lunar cycle = 28 days = one month
 *   - Epoch start (totalMinutes = 0) = Sunday Jan 1, year 1, 12:00 PM
 */

export interface GameClock {
  /** Minutes elapsed since the epoch start. Always >= 0. */
  totalMinutes: number;
}

export const DAYS_OF_WEEK = [
  "Sunday", "Monday", "Tuesday", "Wednesday",
  "Thursday", "Friday", "Saturday",
] as const;

export const DAY_ABBREV = [
  "SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT",
] as const;

export const MONTHS = [
  "January", "February", "March", "April",
  "May", "June", "July", "August",
  "September", "October", "November", "December",
] as const;

export const MONTH_ABBREV = [
  "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
  "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
] as const;

export const LUNAR_PHASES = [
  "New Moon",
  "Waxing Crescent",
  "First Quarter",
  "Waxing Gibbous",
  "Full Moon",
  "Waning Gibbous",
  "Last Quarter",
  "Waning Crescent",
] as const;

export const DAYS_PER_MONTH = 28;
export const MONTHS_PER_YEAR = 12;
export const DAYS_PER_YEAR = DAYS_PER_MONTH * MONTHS_PER_YEAR; // 336
export const MINUTES_PER_DAY = 24 * 60;
export const MINUTES_PER_LUNAR_CYCLE = DAYS_PER_MONTH * MINUTES_PER_DAY;

/** Per-step minute advance — matches `src/states/overworld.py:922`. */
export const MINUTES_PER_STEP = 5;

const START_HOUR = 12; // epoch minute 0 = 12:00 PM

export function makeClock(totalMinutes = 0): GameClock {
  return { totalMinutes: Math.max(0, totalMinutes | 0) };
}

export function advanceClock(c: GameClock, minutes = MINUTES_PER_STEP): void {
  c.totalMinutes += Math.max(0, minutes);
}

function abs(c: GameClock): number {
  return c.totalMinutes + START_HOUR * 60;
}

export function dayIndex(c: GameClock): number {
  return Math.floor(abs(c) / MINUTES_PER_DAY);
}

export function dayOfWeek(c: GameClock): string {
  return DAYS_OF_WEEK[dayIndex(c) % 7];
}

export function dayAbbrev(c: GameClock): string {
  return DAY_ABBREV[dayIndex(c) % 7];
}

export function hour(c: GameClock): number {
  return Math.floor((abs(c) % MINUTES_PER_DAY) / 60);
}

export function minute(c: GameClock): number {
  return abs(c) % 60;
}

export function year(c: GameClock): number {
  return Math.floor(dayIndex(c) / DAYS_PER_YEAR) + 1;
}

export function dayOfYear(c: GameClock): number {
  return dayIndex(c) % DAYS_PER_YEAR;
}

export function monthIndex(c: GameClock): number {
  return Math.floor(dayOfYear(c) / DAYS_PER_MONTH);
}

export function monthName(c: GameClock): string {
  return MONTHS[monthIndex(c)];
}

export function monthAbbrev(c: GameClock): string {
  return MONTH_ABBREV[monthIndex(c)];
}

export function dayOfMonth(c: GameClock): number {
  return (dayOfYear(c) % DAYS_PER_MONTH) + 1;
}

export function timeStr(c: GameClock): string {
  const h = hour(c);
  const m = minute(c);
  const period = h < 12 ? "AM" : "PM";
  const display = h % 12 === 0 ? 12 : h % 12;
  return `${display}:${m.toString().padStart(2, "0")}${period}`;
}

export function dateStr(c: GameClock): string {
  return `${monthAbbrev(c)} ${dayOfMonth(c)} ${dayAbbrev(c)}`;
}

export function fullStr(c: GameClock): string {
  return `${dateStr(c)} ${timeStr(c)}`;
}

// ── Time-of-day classification (matches game_time.py) ──────────────

/** True between 8 PM (20:00) and 5 AM. */
export function isNight(c: GameClock): boolean {
  const h = hour(c);
  return h >= 20 || h < 5;
}

/** True between 5 AM and 7 AM. */
export function isDawn(c: GameClock): boolean {
  const h = hour(c);
  return h >= 5 && h < 7;
}

/** True between 7 PM (19:00) and 8 PM. */
export function isDusk(c: GameClock): boolean {
  const h = hour(c);
  return h >= 19 && h < 20;
}

/** True between 7 AM and 7 PM. */
export function isDay(c: GameClock): boolean {
  const h = hour(c);
  return h >= 7 && h < 19;
}

// ── Lunar phase ────────────────────────────────────────────────────

export function lunarPhaseIndex(c: GameClock): number {
  const cycle = ((c.totalMinutes % MINUTES_PER_LUNAR_CYCLE)
    + MINUTES_PER_LUNAR_CYCLE) % MINUTES_PER_LUNAR_CYCLE;
  return Math.floor((cycle / MINUTES_PER_LUNAR_CYCLE) * 8) % 8;
}

export function lunarPhaseName(c: GameClock): string {
  return LUNAR_PHASES[lunarPhaseIndex(c)];
}

// ── Clock-darkness parameters (port of _resolve_clock_params) ─────

export interface ClockDarknessParams {
  /** RGB tint in 0xRRGGBB. */
  tint: number;
  /** Maximum overlay opacity, 0..1. */
  maxAlpha: number;
  /** Tiles of full-bright party-light radius (only meaningful at night). */
  partyRadius: number;
  /** Tiles of soft-fade falloff outside the party radius. */
  fade: number;
}

/**
 * Return the clock-driven darkness parameters for the current phase,
 * or `null` for daytime (no overlay needed). Mirrors
 * `lighting.py:_resolve_clock_params`.
 */
export function clockDarknessParams(c: GameClock): ClockDarknessParams | null {
  if (isDusk(c)) {
    // Cool purple wash, low opacity — silhouette of sunset.
    return { tint: 0x14082b, maxAlpha: 100 / 255, partyRadius: 10, fade: 4 };
  }
  if (isDawn(c)) {
    // Warm orange wash, low opacity — sunrise glow.
    return { tint: 0x28140a, maxAlpha: 80 / 255, partyRadius: 10, fade: 4 };
  }
  if (isNight(c)) {
    // Full black; party-light pool punches a hole.
    return { tint: 0x000000, maxAlpha: 1.0, partyRadius: 0, fade: 1.5 };
  }
  return null;
}
