import { describe, it, expect } from "vitest";
import { combatantFromMember, combatantsFromParty, syncCombatHpBack } from "./CombatBridge";
import { partyFromRaw, memberFromRaw } from "../world/Party";
import type { Item } from "../world/Items";

function items(): Map<string, Item> {
  const m = new Map<string, Item>();
  m.set("Sword", {
    name: "Sword", category: "weapons", description: "",
    slots: ["right_hand"], characterCanEquip: true, partyCanEquip: false,
    usable: false, effect: null, power: 5, ranged: false, melee: true, throwable: false,
  });
  m.set("Crossbow", {
    name: "Crossbow", category: "weapons", description: "",
    slots: ["right_hand"], characterCanEquip: true, partyCanEquip: false,
    usable: false, effect: null, power: 7, ranged: true, melee: false, throwable: false,
  });
  m.set("Dagger", {
    name: "Dagger", category: "weapons", description: "",
    slots: ["right_hand", "left_hand"], characterCanEquip: true, partyCanEquip: false,
    usable: false, effect: null, power: 3, ranged: false, melee: true, throwable: true,
  });
  m.set("Chain", {
    name: "Chain", category: "armors", description: "",
    slots: ["body"], characterCanEquip: true, partyCanEquip: false,
    usable: false, effect: null, evasion: 50,
  });
  m.set("Cloth", {
    name: "Cloth", category: "armors", description: "",
    slots: ["body"], characterCanEquip: true, partyCanEquip: false,
    usable: false, effect: null, evasion: 0,
  });
  return m;
}

describe("combatantFromMember", () => {
  it("derives stats from level + ability mods + equipped weapon", () => {
    const fighter = memberFromRaw({
      name: "Gimli", class: "Fighter", race: "Dwarf",
      level: 10, hp: 60, strength: 18, dexterity: 14, intelligence: 9, wisdom: 9,
      equipped: { right_hand: "Sword", left_hand: null, body: "Chain", head: null },
    });
    const c = combatantFromMember(fighter, items());
    expect(c.name).toBe("Gimli");
    expect(c.maxHp).toBe(60);
    expect(c.hp).toBe(60);
    // STR 18 → +4 mod, level 10 → +5 prof, +1 baseline → +10 attack bonus
    expect(c.attackBonus).toBe(10);
    // DEX 14 → +2; Chain evasion 50 → +2 armor; AC = 10+2+2 = 14
    expect(c.ac).toBe(14);
    // weapon.power 5 → 1d6+5
    expect(c.damage).toEqual({ dice: 1, sides: 6, bonus: 5 });
    expect(c.dexMod).toBe(2);
    expect(c.sprite).toMatch(/fighter/);
  });

  it("uses DEX for ranged and throwable weapons", () => {
    const thief = memberFromRaw({
      name: "Merry", class: "Thief", race: "Halfling",
      level: 10, hp: 45, strength: 12, dexterity: 18,
      equipped: { right_hand: "Dagger", left_hand: null, body: "Cloth", head: null },
    });
    const c = combatantFromMember(thief, items());
    // DEX 18 → +4, level 10 → +5, +1 → 10
    expect(c.attackBonus).toBe(10);
  });

  it("falls back to bare 1d6 when nothing is equipped", () => {
    const m = memberFromRaw({
      name: "X", class: "Fighter", race: "Human", level: 1, hp: 10,
      strength: 10, dexterity: 10, intelligence: 10, wisdom: 10,
    });
    const c = combatantFromMember(m, items());
    expect(c.damage).toEqual({ dice: 1, sides: 6, bonus: 0 });
  });

  it("caps the armour bonus at +4 even with high evasion gear", () => {
    const m = memberFromRaw({
      name: "X", class: "Fighter", race: "Human", level: 1, hp: 10,
      strength: 10, dexterity: 10,
      equipped: { right_hand: null, left_hand: null, body: "Chain", head: null },
    });
    const c = combatantFromMember(m, items());
    // DEX 10 → 0 mod; Chain evasion 50 → +2 armour; AC = 10+0+2 = 12
    expect(c.ac).toBe(12);
  });
});

describe("combatantsFromParty", () => {
  const raw = {
    start_position: { col: 0, row: 0 }, gold: 0,
    roster: [
      { name: "Gimli",  class: "Fighter", race: "Dwarf", level: 10, hp: 60, strength: 18, dexterity: 14 },
      { name: "Merry",  class: "Thief",   race: "Halfling", level: 10, hp: 45, strength: 12, dexterity: 18 },
      { name: "Spare",  class: "Cleric",  race: "Human",  level: 1, hp: 20 },
      { name: "Spare2", class: "Wizard",  race: "Elf",    level: 1, hp: 20 },
    ],
    active_party: [0, 1, 2, 3],
  };

  it("maps each active member to a Combatant in order", () => {
    const p = partyFromRaw(raw);
    const cs = combatantsFromParty(p, items());
    expect(cs).toHaveLength(4);
    expect(cs[0].name).toBe("Gimli");
    expect(cs[1].name).toBe("Merry");
    expect(cs.every((c) => c.side === "party")).toBe(true);
  });

  it("respects active_party ordering", () => {
    const p = partyFromRaw({ ...raw, active_party: [1, 0, 3, 2] });
    const cs = combatantsFromParty(p, items());
    expect(cs.map((c) => c.name)).toEqual(["Merry", "Gimli", "Spare2", "Spare"]);
  });
});

describe("syncCombatHpBack", () => {
  it("writes combat HP back into the party roster by name", () => {
    const p = partyFromRaw({
      start_position: { col: 0, row: 0 }, gold: 0,
      roster: [
        { name: "Gimli", class: "Fighter", race: "Dwarf", level: 10, hp: 60 },
      ],
      active_party: [0],
    });
    const cs = combatantsFromParty(p, items());
    cs[0].hp = 30;
    syncCombatHpBack(p, cs);
    expect(p.roster[0].hp).toBe(30);
  });
});
