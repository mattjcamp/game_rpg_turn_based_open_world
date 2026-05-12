/**
 * D&D-style combat engine.
 *
 * Direct TypeScript port of `src/combat_engine.py` in the Python project.
 * Preserves the contract of every function; the test file is a port of
 * `tests/test_combat_engine.py`. If behaviour ever diverges from the
 * Python version, this file is the canonical reference for the web build.
 *
 * Each function takes an optional `rng` argument so tests can pass a
 * seeded RNG. Production callers omit it and get Math.random.
 */

import { defaultRng, type RNG } from "../rng";

/** Roll <count>d<sides> and return the total. */
export function rollDice(count: number, sides: number, rng: RNG = defaultRng): number {
  let total = 0;
  for (let i = 0; i < count; i++) {
    total += Math.floor(rng() * sides) + 1;
  }
  return total;
}

/** Roll a single d20. */
export function rollD20(rng: RNG = defaultRng): number {
  return Math.floor(rng() * 20) + 1;
}

/**
 * D&D ability modifier: floor((stat - 10) / 2).
 *
 * Note Python's `//` is a floor-div, which differs from JS's `Math.trunc`
 * for negative dividends. `Math.floor` here matches Python exactly:
 * get_modifier(8)  → -1   (Python: (8-10)//2 = -1, JS trunc would give 0)
 */
export function getModifier(statValue: number): number {
  return Math.floor((statValue - 10) / 2);
}

/** Roll initiative: d20 + DEX modifier. Returns total and the raw roll. */
export function rollInitiative(
  dexMod: number,
  rng: RNG = defaultRng
): { total: number; raw: number } {
  const raw = rollD20(rng);
  return { total: raw + dexMod, raw };
}

export interface AttackRollResult {
  hit: boolean;
  roll: number;
  total: number;
  critical: boolean;
}

/**
 * Roll a melee attack: d20 + attackBonus vs defenderAc.
 *
 * Natural 20 always hits and is a critical. Natural 1 always misses and
 * is never a critical. Otherwise a hit lands when the total ≥ defender AC.
 */
export function rollAttack(
  attackBonus: number,
  defenderAc: number,
  rng: RNG = defaultRng
): AttackRollResult {
  const roll = rollD20(rng);
  const total = roll + attackBonus;
  if (roll === 1) {
    return { hit: false, roll, total, critical: false };
  }
  if (roll === 20) {
    return { hit: true, roll, total, critical: true };
  }
  return { hit: total >= defenderAc, roll, total, critical: false };
}

/**
 * Roll damage: <diceCount>d<diceSides> + bonus.
 *
 * On a critical hit the dice are doubled (the bonus is not).
 * Minimum damage on a hit is 1.
 */
export function rollDamage(
  diceCount: number,
  diceSides: number,
  bonus: number,
  critical = false,
  rng: RNG = defaultRng
): number {
  const multiplier = critical ? 2 : 1;
  const damage = rollDice(diceCount * multiplier, diceSides, rng) + bonus;
  return Math.max(1, damage);
}

/**
 * Roll a magic-item `bonus_damage` spec — Sun Sword's `"1d6"`, an
 * Elixir-of-Power weapon's flat `+3`, etc. Mirrors the Python game's
 * `_roll_bonus_damage`:
 *
 *   - Number → flat extra damage. Crits double the value.
 *   - "NdM" string → roll N d-sided dice (N defaults to 1 when the
 *     part before "d" is empty, so "d4" works as "1d4"). Crits double
 *     the dice count, not the per-die maximum.
 *   - "N" string (no "d") → parsed as a flat number, doubled on crit.
 *   - Anything unparseable → 0 (bad data shouldn't crash a swing).
 *
 * Returns the extra damage to add on top of the base weapon roll —
 * deliberately *not* min-clamped to 1, because a zero result here just
 * means "the magic part of the weapon didn't add anything this swing"
 * and the base roll already covers the "minimum 1 on a hit" rule.
 */
export function rollBonusDamage(
  spec: string | number,
  critical = false,
  rng: RNG = defaultRng,
): number {
  const multiplier = critical ? 2 : 1;
  if (typeof spec === "number") {
    return Math.max(0, Math.floor(spec) * multiplier);
  }
  const trimmed = spec.trim().toLowerCase();
  if (trimmed.includes("d")) {
    const [nStr, mStr] = trimmed.split("d", 2);
    const n = nStr === "" ? 1 : parseInt(nStr, 10);
    const m = parseInt(mStr, 10);
    if (!Number.isFinite(n) || !Number.isFinite(m) || n <= 0 || m <= 0) return 0;
    return rollDice(n * multiplier, m, rng);
  }
  const flat = parseInt(trimmed, 10);
  if (!Number.isFinite(flat)) return 0;
  return Math.max(0, flat * multiplier);
}

/** Format a modifier as +N or -N. Zero formats as "+0". */
export function formatModifier(mod: number): string {
  return mod >= 0 ? `+${mod}` : String(mod);
}
