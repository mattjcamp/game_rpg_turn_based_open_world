import { describe, it, expect } from "vitest";
import { canEquip, type Effect } from "./Effects";
import { memberFromRaw } from "./Party";

const party = [
  memberFromRaw({ name: "Gimli",   class: "Fighter", race: "Dwarf",    level: 1, hp: 20 }),
  memberFromRaw({ name: "Merry",   class: "Thief",   race: "Halfling", level: 1, hp: 18 }),
  memberFromRaw({ name: "Gandolf", class: "Wizard",  race: "Elf",      level: 1, hp: 16 }),
  memberFromRaw({ name: "Selina",  class: "Cleric",  race: "Human",    level: 1, hp: 18 }),
];

const detectTraps: Effect = {
  id: "detect_traps", name: "Detect Traps", description: "", duration: "permanent",
  requirements: { any_of: [
    { class: "Thief",  min_level: 1 },
    { class: "Ranger", min_level: 3 },
  ]},
};

describe("canEquip", () => {
  it("matches via any_of when one branch is satisfied (Thief in party)", () => {
    expect(canEquip(detectTraps, party)).toBe(true);
  });

  it("returns false when no branch is satisfied", () => {
    const ranger3: Effect = {
      id: "x", name: "Ranger 3", description: "", duration: "permanent",
      requirements: { class: "Ranger", min_level: 3 },
    };
    expect(canEquip(ranger3, party)).toBe(false);
  });

  it("respects min_level on a single class clause", () => {
    const lvl5fighter: Effect = {
      id: "x", name: "x", description: "", duration: "permanent",
      requirements: { class: "Fighter", min_level: 5 },
    };
    expect(canEquip(lvl5fighter, party)).toBe(false);
    // Level the fighter up to 5 and it now qualifies.
    party[0].level = 5;
    expect(canEquip(lvl5fighter, party)).toBe(true);
    party[0].level = 1;
  });

  it("matches a race requirement on any active member", () => {
    const dwarven: Effect = {
      id: "x", name: "Infravision", description: "", duration: "permanent",
      requirements: { race: "Dwarf" },
    };
    expect(canEquip(dwarven, party)).toBe(true);
    const orcOnly: Effect = { ...dwarven, requirements: { race: "Orc" } };
    expect(canEquip(orcOnly, party)).toBe(false);
  });

  it("treats item_granted effects as not-yet-available", () => {
    const sunSword: Effect = {
      id: "sun", name: "Sun Sword Aura", description: "", duration: "permanent",
      item_granted: true,
    };
    expect(canEquip(sunSword, party)).toBe(false);
  });

  it("an effect with no requirements is always equippable", () => {
    const free: Effect = { id: "free", name: "Free", description: "", duration: "permanent" };
    expect(canEquip(free, party)).toBe(true);
  });
});
