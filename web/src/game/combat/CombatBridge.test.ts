import { describe, it, expect } from "vitest";
import { combatantFromMember, combatantsFromParty, syncCombatHpBack } from "./CombatBridge";
import { partyFromRaw, memberFromRaw } from "../world/Party";
import type { Item } from "../world/Items";
import type { ClassTemplate } from "../world/Classes";

function classes(): Map<string, ClassTemplate> {
  const m = new Map<string, ClassTemplate>();
  m.set("fighter", { name: "Fighter", hpPerLevel: 15, mpPerLevel: 0, expPerLevel: 1500, range: 4 });
  m.set("thief",   { name: "Thief",   hpPerLevel: 5,  mpPerLevel: 0, expPerLevel: 1500, range: 6 });
  m.set("wizard",  { name: "Wizard",  hpPerLevel: 4,  mpPerLevel: 15, expPerLevel: 1500, range: 2,
                     mpSource: { ability: "intelligence" } });
  m.set("cleric",  { name: "Cleric",  hpPerLevel: 6,  mpPerLevel: 10, expPerLevel: 1500, range: 2,
                     mpSource: { ability: "wisdom" } });
  return m;
}

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
  it("derives Python-style stats from ability mods + equipped weapon", () => {
    const fighter = memberFromRaw({
      name: "Gimli", class: "Fighter", race: "Dwarf",
      level: 10, hp: 60, strength: 18, dexterity: 14, intelligence: 9, wisdom: 9,
      equipped: { right_hand: "Sword", left_hand: null, body: "Chain", head: null },
    });
    const c = combatantFromMember(fighter, items());
    expect(c.name).toBe("Gimli");
    expect(c.maxHp).toBe(60);
    expect(c.hp).toBe(60);
    // STR 18 → +4 mod (Python: `Member.get_attack_bonus(ranged=False)`).
    expect(c.attackBonus).toBe(4);
    // DEX 14 → +2; Chain evasion 50 → +0 armour bonus (50-50)/5; AC = 10+2+0 = 12.
    expect(c.ac).toBe(12);
    // Sword has power 5 → 1d6 + STR mod (+4).
    expect(c.damage).toEqual({ dice: 1, sides: 6, bonus: 4 });
    expect(c.dexMod).toBe(2);
    expect(c.strength).toBe(18);
    expect(c.intelligence).toBe(9);
    expect(c.wisdom).toBe(9);
    expect(c.sprite).toMatch(/fighter/);
  });

  it("uses DEX for ranged weapons and STR for throwable melee weapons", () => {
    const thief = memberFromRaw({
      name: "Merry", class: "Thief", race: "Halfling",
      level: 10, hp: 45, strength: 12, dexterity: 18,
      equipped: { right_hand: "Dagger", left_hand: null, body: "Cloth", head: null },
    });
    // Dagger is melee + throwable. Default is melee, so STR mod (+1).
    const melee = combatantFromMember(thief, items());
    expect(melee.attackBonus).toBe(1);
    // Crossbow is ranged → DEX mod (+4) for both attack and damage.
    const ranger = memberFromRaw({
      name: "Syl", class: "Ranger", race: "Elf",
      level: 5, hp: 30, strength: 10, dexterity: 18,
      equipped: { right_hand: "Crossbow", left_hand: null, body: "Cloth", head: null },
    });
    const c = combatantFromMember(ranger, items());
    expect(c.attackBonus).toBe(4);
    // Power 7 → 1d8 + DEX mod (+4).
    expect(c.damage).toEqual({ dice: 1, sides: 8, bonus: 4 });
  });

  it("falls back to flat 1 damage when nothing is equipped", () => {
    const m = memberFromRaw({
      name: "X", class: "Fighter", race: "Human", level: 1, hp: 10,
      strength: 10, dexterity: 10, intelligence: 10, wisdom: 10,
    });
    const c = combatantFromMember(m, items());
    expect(c.damage).toEqual({ dice: 0, sides: 0, bonus: 1 });
    // Empty hands: STR 10 → +0 attack, AC 10 + DEX 0 + (50-50)/5 = 10.
    expect(c.attackBonus).toBe(0);
    expect(c.ac).toBe(10);
  });

  it("scales AC with armour evasion the way the Python game does", () => {
    const heavy = memberFromRaw({
      name: "X", class: "Fighter", race: "Human", level: 1, hp: 10,
      strength: 10, dexterity: 14,
      equipped: { right_hand: null, left_hand: null, body: "Chain", head: null },
    });
    // Chain evasion 50 → +0 armour bonus (50-50)/5; AC = 10 + DEX 2 + 0 = 12.
    expect(combatantFromMember(heavy, items()).ac).toBe(12);
  });

  it("rolls power-1 weapons to 1d4-1 and power-9+ to 1d10", () => {
    const items_ = items();
    items_.set("Club", {
      name: "Club", category: "weapons", description: "",
      slots: ["right_hand"], characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null, power: 1, ranged: false,
    });
    items_.set("Greataxe", {
      name: "Greataxe", category: "weapons", description: "",
      slots: ["right_hand"], characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null, power: 9, ranged: false,
    });
    const club = memberFromRaw({
      name: "X", class: "Fighter", race: "Human", level: 1, hp: 10,
      strength: 14, dexterity: 10,
      equipped: { right_hand: "Club", left_hand: null, body: null, head: null },
    });
    // STR 14 → +2; power 1 path is 1d4 + (mod - 1) = 1d4 + 1.
    expect(combatantFromMember(club, items_).damage)
      .toEqual({ dice: 1, sides: 4, bonus: 1 });
    const heavy = memberFromRaw({
      name: "X", class: "Fighter", race: "Human", level: 1, hp: 10,
      strength: 18, dexterity: 10,
      equipped: { right_hand: "Greataxe", left_hand: null, body: null, head: null },
    });
    // STR 18 → +4; power 9+ path is 1d10 + STR mod.
    expect(combatantFromMember(heavy, items_).damage)
      .toEqual({ dice: 1, sides: 10, bonus: 4 });
  });

  it("sums the acBonus from every equipped magic item", () => {
    const items_ = items();
    items_.set("Bracers", {
      name: "Bracers", category: "armors", description: "",
      slots: ["body"], characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null, evasion: 50, acBonus: 2,
    });
    items_.set("Ring", {
      name: "Ring", category: "general", description: "",
      slots: ["head"], characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null, acBonus: 1,
    });
    const m = memberFromRaw({
      name: "X", class: "Fighter", race: "Human", level: 1, hp: 10,
      strength: 10, dexterity: 10,
      equipped: { right_hand: null, left_hand: null, body: "Bracers", head: "Ring" },
    });
    // AC = 10 + DEX 0 + (50-50)/5 + (2 + 1) magic = 13.
    expect(combatantFromMember(m, items_).ac).toBe(13);
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

  it("falls back to the default 4-tile move range when no class map is supplied", () => {
    const p = partyFromRaw(raw);
    const cs = combatantsFromParty(p, items());
    expect(cs.every((c) => c.baseMoveRange === 4)).toBe(true);
  });

  it("uses each class template's range when a map is supplied", () => {
    const p = partyFromRaw(raw);
    const cs = combatantsFromParty(p, items(), classes());
    // Roster: Fighter, Thief, Cleric, Wizard
    expect(cs[0].baseMoveRange).toBe(4); // Fighter
    expect(cs[1].baseMoveRange).toBe(6); // Thief
    expect(cs[2].baseMoveRange).toBe(2); // Cleric
    expect(cs[3].baseMoveRange).toBe(2); // Wizard
  });

  it("falls back to the default for classes missing from the map", () => {
    const p = partyFromRaw(raw);
    const onlyFighter = new Map<string, ClassTemplate>();
    onlyFighter.set("fighter", classes().get("fighter")!);
    const cs = combatantsFromParty(p, items(), onlyFighter);
    expect(cs[0].baseMoveRange).toBe(4); // explicit
    expect(cs[1].baseMoveRange).toBe(4); // default for Thief
    expect(cs[2].baseMoveRange).toBe(4); // default for Cleric
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
