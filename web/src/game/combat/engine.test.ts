/**
 * Tests for combat engine — direct port of tests/test_combat_engine.py.
 *
 * Each `describe` block matches a class in the Python suite. Where the
 * Python tests use `random.seed(...)` to force a specific roll, we use
 * the seedable mulberry32 RNG so the same idea works here.
 */

import { describe, it, expect } from "vitest";
import {
  rollDice,
  rollD20,
  getModifier,
  rollInitiative,
  rollAttack,
  rollDamage,
  formatModifier,
} from "./engine";
import { mulberry32 } from "../rng";

// ── Dice rolling ──────────────────────────────────────────────────────

describe("dice rolling", () => {
  it("rolls 2d6 within range", () => {
    for (let i = 0; i < 100; i++) {
      const result = rollDice(2, 6);
      expect(result).toBeGreaterThanOrEqual(2);
      expect(result).toBeLessThanOrEqual(12);
    }
  });

  it("rolls d20 within range", () => {
    for (let i = 0; i < 100; i++) {
      const result = rollD20();
      expect(result).toBeGreaterThanOrEqual(1);
      expect(result).toBeLessThanOrEqual(20);
    }
  });

  it("rolls 1d4 within range", () => {
    for (let i = 0; i < 50; i++) {
      const result = rollDice(1, 4);
      expect(result).toBeGreaterThanOrEqual(1);
      expect(result).toBeLessThanOrEqual(4);
    }
  });
});

// ── Ability modifier ──────────────────────────────────────────────────

describe("ability modifier", () => {
  it("returns 0 for stat 10", () => {
    expect(getModifier(10)).toBe(0);
  });

  it("is negative below 10", () => {
    expect(getModifier(8)).toBe(-1);
    expect(getModifier(6)).toBe(-2);
  });

  it("is positive above 10", () => {
    expect(getModifier(14)).toBe(2);
    expect(getModifier(18)).toBe(4);
  });

  it("uses Python-style floor division for odd negatives", () => {
    // Python: (9 - 10) // 2 == -1, not 0 (which Math.trunc would give).
    expect(getModifier(9)).toBe(-1);
    expect(getModifier(7)).toBe(-2);
  });

  it("formats positive modifier with +", () => {
    expect(formatModifier(3)).toBe("+3");
  });

  it("formats negative modifier with -", () => {
    expect(formatModifier(-2)).toBe("-2");
  });

  it("formats zero as +0", () => {
    expect(formatModifier(0)).toBe("+0");
  });
});

// ── Initiative ────────────────────────────────────────────────────────

describe("initiative", () => {
  it("returns total and raw with total = raw + mod", () => {
    const { total, raw } = rollInitiative(2);
    expect(typeof total).toBe("number");
    expect(typeof raw).toBe("number");
    expect(total).toBe(raw + 2);
  });

  it("equals raw when modifier is zero", () => {
    for (let i = 0; i < 100; i++) {
      const { total, raw } = rollInitiative(0);
      expect(raw).toBeGreaterThanOrEqual(1);
      expect(raw).toBeLessThanOrEqual(20);
      expect(total).toBe(raw);
    }
  });
});

// ── Attack resolution ─────────────────────────────────────────────────

describe("attack resolution", () => {
  it("returns the four expected fields", () => {
    const result = rollAttack(5, 15);
    expect(typeof result.hit).toBe("boolean");
    expect(typeof result.roll).toBe("number");
    expect(typeof result.total).toBe("number");
    expect(typeof result.critical).toBe("boolean");
  });

  it("treats natural 1 as an automatic miss (not a crit)", () => {
    // Force nat-1s with a seeded RNG that's heavily biased toward 0.
    // We try up to 200 rolls to observe at least one nat-1 — very high
    // probability with a fixed seed; the assertion holds for every nat-1
    // we do see, so coverage is what matters here.
    const rng = mulberry32(42);
    let foundNat1 = false;
    for (let i = 0; i < 400; i++) {
      const result = rollAttack(100, 1, rng);
      if (result.roll === 1) {
        expect(result.hit).toBe(false);
        expect(result.critical).toBe(false);
        foundNat1 = true;
        break;
      }
    }
    expect(foundNat1).toBe(true);
  });

  it("treats natural 20 as an automatic critical hit", () => {
    const rng = mulberry32(7);
    let foundNat20 = false;
    for (let i = 0; i < 400; i++) {
      const result = rollAttack(-100, 999, rng);
      if (result.roll === 20) {
        expect(result.hit).toBe(true);
        expect(result.critical).toBe(true);
        foundNat20 = true;
        break;
      }
    }
    expect(foundNat20).toBe(true);
  });

  it("hits when total meets or exceeds AC for non-extreme rolls", () => {
    // Attack bonus +5 vs AC 10 — every roll 5..19 should hit.
    // We can't easily force a specific d20 without a custom RNG, so use
    // a seeded sequence and just assert internal consistency.
    const rng = mulberry32(123);
    for (let i = 0; i < 200; i++) {
      const r = rollAttack(5, 10, rng);
      if (r.roll !== 1 && r.roll !== 20) {
        expect(r.hit).toBe(r.total >= 10);
      }
    }
  });
});

// ── Damage rolling ────────────────────────────────────────────────────

describe("damage rolling", () => {
  it("guarantees minimum 1 damage", () => {
    for (let i = 0; i < 50; i++) {
      const dmg = rollDamage(1, 4, 0);
      expect(dmg).toBeGreaterThanOrEqual(1);
    }
  });

  it("doubles dice on critical (not bonus)", () => {
    // Same seed for both — crit version rolls twice the dice so the sum
    // should be strictly higher across many rolls.
    const sumNormal = (() => {
      const rng = mulberry32(99);
      let s = 0;
      for (let i = 0; i < 50; i++) s += rollDamage(1, 6, 0, false, rng);
      return s;
    })();
    const sumCrit = (() => {
      const rng = mulberry32(99);
      let s = 0;
      for (let i = 0; i < 50; i++) s += rollDamage(1, 6, 0, true, rng);
      return s;
    })();
    expect(sumCrit).toBeGreaterThan(sumNormal);
  });

  it("adds bonus on top of dice", () => {
    const seed = 42;
    const noBonus = rollDamage(1, 6, 0, false, mulberry32(seed));
    const withBonus = rollDamage(1, 6, 5, false, mulberry32(seed));
    expect(withBonus).toBe(noBonus + 5);
  });
});
