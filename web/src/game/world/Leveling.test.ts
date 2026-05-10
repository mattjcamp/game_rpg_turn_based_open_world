/**
 * Tests for the XP / level-up math.
 */

import { describe, it, expect } from "vitest";
import {
  awardXp,
  xpForNextLevel,
  spellsUnlockedAt,
  abilitiesUnlockedAt,
} from "./Leveling";
import type { PartyMember } from "./Party";
import type { ClassTemplate, RaceInfo } from "./Classes";
import type { Spell } from "./Spells";

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

  it("populates newSpells / newAbilities arrays even when empty", () => {
    // Default Fighter has no class abilities and we pass no spells —
    // the dialog still wants empty arrays rather than undefined so
    // it can `.length === 0` cleanly.
    const m = member({ level: 1, exp: 0 });
    const events = awardXp(m, 1500, fighterTpl, null);
    expect(events[0].newSpells).toEqual([]);
    expect(events[0].newAbilities).toEqual([]);
  });
});

describe("spellsUnlockedAt", () => {
  // Two spell fixtures: Heal (Cleric L1 / Paladin L3) and Turn Undead
  // (Cleric L2 / Paladin L5). The per-class override is the
  // interesting case — spellsUnlockedAt has to honour it.
  const heal: Spell = {
    id: "heal", name: "Heal", description: "Restore HP.",
    allowable_classes: ["Cleric", "Paladin"],
    casting_type: "priest", min_level: 1,
    class_min_levels: { Paladin: 3 },
    mp_cost: 4, duration: "instant", effect_type: "heal", usable_in: ["battle"],
  };
  const turnUndead: Spell = {
    id: "turn_undead", name: "Turn Undead", description: "Channel holy power.",
    allowable_classes: ["Cleric", "Paladin"],
    casting_type: "priest", min_level: 2,
    class_min_levels: { Paladin: 5 },
    mp_cost: 0, duration: "instant", effect_type: "undead_damage",
    targeting: "auto_monster", usable_in: ["battle"],
  };
  const magicDart: Spell = {
    id: "magic_dart", name: "Magic Dart", description: "Bolt of force.",
    allowable_classes: ["Wizard"],
    casting_type: "sorcerer", min_level: 1,
    mp_cost: 2, duration: "instant", effect_type: "damage", usable_in: ["battle"],
  };
  const all = [heal, turnUndead, magicDart];

  it("returns spells whose effective min_level matches the given level", () => {
    // Cleric reaches L2 — Turn Undead unlocks (its base min_level is 2).
    const out = spellsUnlockedAt("Cleric", 2, all);
    expect(out.map((s) => s.name)).toEqual(["Turn Undead"]);
  });

  it("respects class_min_levels overrides (Paladin L5 Turn Undead)", () => {
    // At Paladin L5, Turn Undead unlocks via the per-class override.
    const out5 = spellsUnlockedAt("Paladin", 5, all);
    expect(out5.map((s) => s.name)).toEqual(["Turn Undead"]);
    // At Paladin L2 nothing unlocks — base min_level wouldn't apply,
    // and the override hasn't kicked in yet.
    const out2 = spellsUnlockedAt("Paladin", 2, all);
    expect(out2).toEqual([]);
    // At Paladin L3 Heal unlocks via the override.
    const out3 = spellsUnlockedAt("Paladin", 3, all);
    expect(out3.map((s) => s.name)).toEqual(["Heal"]);
  });

  it("filters out spells the class can't cast", () => {
    // Wizard at L2 doesn't get any of these (only Magic Dart, which
    // unlocked at L1).
    expect(spellsUnlockedAt("Wizard", 2, all)).toEqual([]);
    // At L1, the Wizard picks up Magic Dart.
    expect(spellsUnlockedAt("Wizard", 1, all).map((s) => s.name))
      .toEqual(["Magic Dart"]);
  });

  it("is case-insensitive on the class match", () => {
    expect(spellsUnlockedAt("cleric", 2, all).map((s) => s.name))
      .toEqual(["Turn Undead"]);
  });

  it("surfaces the spell's MP cost + description for the dialog", () => {
    const out = spellsUnlockedAt("Wizard", 1, all);
    expect(out[0]).toEqual({
      name: "Magic Dart",
      mpCost: 2,
      description: "Bolt of force.",
    });
  });
});

describe("abilitiesUnlockedAt", () => {
  const ranger: ClassTemplate = {
    name: "Ranger", hpPerLevel: 10, mpPerLevel: 3, expPerLevel: 1500, range: 6,
    classAbilities: [
      { name: "Herbalism",   minLevel: 1, description: "Spot reagents." },
      { name: "Pick Locks",  minLevel: 3, description: "Pick mundane locks." },
      { name: "Detect Traps", minLevel: 3, description: "See traps before stepping on them." },
    ],
  };
  const fighter: ClassTemplate = {
    name: "Fighter", hpPerLevel: 15, mpPerLevel: 0, expPerLevel: 1500, range: 4,
  };

  it("returns abilities whose minLevel matches exactly", () => {
    expect(abilitiesUnlockedAt(ranger, 3).map((a) => a.name).sort())
      .toEqual(["Detect Traps", "Pick Locks"]);
  });

  it("returns the level-1 abilities at level 1 (character-creation grants)", () => {
    expect(abilitiesUnlockedAt(ranger, 1).map((a) => a.name)).toEqual(["Herbalism"]);
  });

  it("returns [] for a level with no unlocks", () => {
    expect(abilitiesUnlockedAt(ranger, 2)).toEqual([]);
    expect(abilitiesUnlockedAt(ranger, 4)).toEqual([]);
  });

  it("returns [] for plain classes with no class_abilities defined", () => {
    expect(abilitiesUnlockedAt(fighter, 1)).toEqual([]);
    expect(abilitiesUnlockedAt(fighter, 5)).toEqual([]);
  });
});

describe("awardXp — new spell/ability events", () => {
  // Paladin reaching level 5 should pick up Turn Undead via spell
  // class_min_levels AND the class ability if both are present.
  const paladin: ClassTemplate = {
    name: "Paladin", hpPerLevel: 10, mpPerLevel: 5, expPerLevel: 1500, range: 4,
    mpSource: { ability: "wisdom" },
    classAbilities: [
      { name: "Turn Undead", minLevel: 5,
        description: "Channel holy energy to turn undead." },
    ],
  };
  const turnUndead: Spell = {
    id: "turn_undead", name: "Turn Undead", description: "Holy blast.",
    allowable_classes: ["Cleric", "Paladin"],
    casting_type: "priest", min_level: 2,
    class_min_levels: { Paladin: 5 },
    mp_cost: 0, duration: "instant", effect_type: "undead_damage",
    targeting: "auto_monster", usable_in: ["battle"],
  };

  it("attaches newSpells when a level-up clears a spell threshold", () => {
    const m = member({
      class: "Paladin", level: 4, exp: 4 * 1500 - 1,
      hp: 50, maxHp: 50, mp: 5, maxMp: 5,
    });
    // One nudge of XP carries them across the level-5 threshold.
    const events = awardXp(m, 2, paladin, null, [turnUndead]);
    expect(events).toHaveLength(1);
    expect(events[0].newLevel).toBe(5);
    expect(events[0].newSpells.map((s) => s.name)).toEqual(["Turn Undead"]);
  });

  it("attaches newAbilities for a class ability gated to this level", () => {
    const m = member({
      class: "Paladin", level: 4, exp: 4 * 1500 - 1,
      hp: 50, maxHp: 50, mp: 5, maxMp: 5,
    });
    const events = awardXp(m, 2, paladin, null, [turnUndead]);
    expect(events[0].newAbilities.map((a) => a.name)).toEqual(["Turn Undead"]);
  });

  it("each level in a multi-level award sees only that level's unlocks", () => {
    // Ranger going from 1 → 4 in one award. Pick Locks + Detect Traps
    // unlock at L3 only — not at L2 or L4.
    const ranger: ClassTemplate = {
      name: "Ranger", hpPerLevel: 10, mpPerLevel: 3, expPerLevel: 1500, range: 6,
      mpSource: { ability: "wisdom" },
      classAbilities: [
        { name: "Pick Locks",  minLevel: 3, description: "" },
        { name: "Detect Traps", minLevel: 3, description: "" },
      ],
    };
    const m = member({ class: "Ranger", level: 1, exp: 0 });
    const events = awardXp(m, 4500, ranger, null, []);
    expect(events.map((e) => e.newLevel)).toEqual([2, 3, 4]);
    expect(events[0].newAbilities).toEqual([]);
    expect(events[1].newAbilities.map((a) => a.name).sort())
      .toEqual(["Detect Traps", "Pick Locks"]);
    expect(events[2].newAbilities).toEqual([]);
  });
});
