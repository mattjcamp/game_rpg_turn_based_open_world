/**
 * Tests for the XP / level-up math.
 */

import { describe, it, expect } from "vitest";
import { awardXp, xpForNextLevel } from "./Leveling";
import type { PartyMember } from "./Party";
import type { ClassTemplate, RaceInfo } from "./Classes";

function member(overrides: Partial<PartyMember> = {}): PartyMember {
  return {
    name: "Test",
    class: "Fighter",
    race: "Human",
    gender: "M",
    hp: 30, maxHp: 30,
    mp: undefined, maxMp: undefined,
    strength: 14, dexterity: 12, constitution: 10, intelligence: 10, wisdom: 10,
    level: 1,
    exp: 0,
    equipped: { rightHand: null, leftHand: null, body: null, head: null },
    equippedDurability: { right_hand: null, left_hand: null, body: null, head: null },
    inventory: [],
    sprite: "",
    ...overrides,
  };
}

const fighterTpl: ClassTemplate = {
  name: "Fighter", hpPerLevel: 15, mpPerLevel: 0, expPerLevel: 1500, range: 4,
};
const wizardTpl: ClassTemplate = {
  name: "Wizard", hpPerLevel: 4, mpPerLevel: 15, expPerLevel: 1500, range: 2,
  mpSource: { ability: "intelligence" },
};
const druidTpl: ClassTemplate = {
  name: "Druid", hpPerLevel: 5, mpPerLevel: 8, expPerLevel: 1500, range: 2,
  mpSource: { abilities: ["intelligence", "wisdom"], mode: "average" },
};
const human: RaceInfo = { name: "Human", expPerLevel: 750 };

describe("xpForNextLevel", () => {
  it("uses the class default when the race has no override", () => {
    expect(xpForNextLevel(member({ level: 1 }), fighterTpl, null)).toBe(1500);
    expect(xpForNextLevel(member({ level: 3 }), fighterTpl, null)).toBe(4500);
  });
  it("prefers the race override over the class default", () => {
    expect(xpForNextLevel(member({ level: 2 }), fighterTpl, human)).toBe(1500);
    expect(xpForNextLevel(member({ level: 4 }), fighterTpl, human)).toBe(3000);
  });
});

describe("awardXp", () => {
  it("does nothing on a non-positive award", () => {
    const m = member();
    expect(awardXp(m, 0, fighterTpl, null)).toEqual([]);
    expect(m.exp).toBe(0);
    expect(m.level).toBe(1);
  });

  it("accumulates XP without leveling up below the threshold", () => {
    const m = member({ level: 1, exp: 0 });
    expect(awardXp(m, 500, fighterTpl, null)).toEqual([]);
    expect(m.exp).toBe(500);
    expect(m.level).toBe(1);
  });

  it("levels up a fighter and bumps HP by hp_per_level + CON mod", () => {
    const m = member({ level: 1, exp: 0, constitution: 14, hp: 30, maxHp: 30 });
    const events = awardXp(m, 1500, fighterTpl, null);
    // CON 14 → +2 mod, hp_per_level 15 → gain 17
    expect(m.level).toBe(2);
    expect(m.maxHp).toBe(47);
    expect(m.hp).toBe(47);
    expect(events).toHaveLength(1);
    expect(events[0].hpGain).toBe(17);
    expect(events[0].mpGain).toBe(0);
    expect(events[0].message).toMatch(/Level 2.*HP\+17/);
    expect(events[0].message).not.toMatch(/MP/);
  });

  it("levels up a caster with MP gains driven by the casting stat", () => {
    const m = member({
      class: "Wizard", level: 1, exp: 0, constitution: 8, intelligence: 18,
      hp: 8, maxHp: 8, mp: 15, maxMp: 15,
    });
    const events = awardXp(m, 1500, wizardTpl, null);
    // CON 8 → -1, hp_per_level 4 → gain max(1, 4 + -1) = 3
    // INT 18 → +4, mp_per_level 15 → gain 15 + 4 = 19
    expect(m.level).toBe(2);
    expect(events[0].hpGain).toBe(3);
    expect(events[0].mpGain).toBe(19);
    expect(m.maxMp).toBe(34);
    expect(m.mp).toBe(34);
    expect(events[0].message).toMatch(/HP\+3.*MP\+19/);
  });

  it("processes multiple level-ups in a single award", () => {
    const m = member({ level: 1, exp: 0, constitution: 14, hp: 30, maxHp: 30 });
    // Thresholds 1500, 3000, 4500: all three are met by 4500 XP, so the
    // member ends at level 4 with three level-up events.
    const events = awardXp(m, 4500, fighterTpl, null);
    expect(m.level).toBe(4);
    expect(events).toHaveLength(3);
    expect(events[0].newLevel).toBe(2);
    expect(events[2].newLevel).toBe(4);
  });

  it("respects race exp_per_level override (Humans → 750)", () => {
    const m = member({ level: 1, exp: 0 });
    awardXp(m, 750, fighterTpl, human);
    expect(m.level).toBe(2); // would not have leveled with 1500-default
  });

  it("uses the average INT/WIS mod for dual-stat casters (Druid)", () => {
    const m = member({
      class: "Druid", level: 1, exp: 0,
      intelligence: 16, wisdom: 14, hp: 6, maxHp: 6, mp: 8, maxMp: 8,
    });
    // average((16+14)/2) = 15 → +2 mod, mp_per_level 8 → 10
    const events = awardXp(m, 1500, druidTpl, null);
    expect(events[0].mpGain).toBe(10);
    expect(m.maxMp).toBe(18);
  });

  it("never lets HP gain drop below 1 even when CON mod would cancel it", () => {
    const m = member({ level: 1, exp: 0, constitution: 4, hp: 8, maxHp: 8 });
    // CON 4 → -3 mod; for a hypothetical class with hp_per_level 2, gain
    // would be max(1, 2 + -3) = 1.
    const tpl: ClassTemplate = { name: "Tiny", hpPerLevel: 2, mpPerLevel: 0, expPerLevel: 1500, range: 4 };
    const events = awardXp(m, 1500, tpl, null);
    expect(events[0].hpGain).toBe(1);
    expect(m.maxHp).toBe(9);
  });

  it("partially heals a wounded member up to the new max HP", () => {
    const m = member({ level: 1, exp: 0, constitution: 10, hp: 20, maxHp: 30 });
    awardXp(m, 1500, fighterTpl, null);
    // hp_per_level 15 + CON mod 0 → +15 to both max and current
    expect(m.maxHp).toBe(45);
    expect(m.hp).toBe(35);
  });
});
