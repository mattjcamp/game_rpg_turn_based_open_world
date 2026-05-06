import { describe, it, expect } from "vitest";
import {
  spellFromRaw,
  minLevelFor,
  castersFor,
  spellsCastableFromMenu,
  type Spell,
} from "./Spells";
import { memberFromRaw } from "./Party";

const heal: Spell = spellFromRaw({
  id: "heal", name: "Heal",
  description: "Heals a wound.",
  allowable_classes: ["Cleric", "Paladin"],
  casting_type: "priest",
  min_level: 1,
  mp_cost: 4,
  duration: "instant",
  effect_type: "heal",
  effect_value: { dice: "1d8", stat_bonus: "wisdom" },
  range: 5,
  targeting: "select_ally",
  usable_in: ["battle", "town", "overworld", "dungeon"],
});

const fireball: Spell = spellFromRaw({
  id: "fireball", name: "Magic Dart",
  description: "",
  allowable_classes: ["Wizard", "Alchemist"],
  casting_type: "sorcerer",
  min_level: 1,
  mp_cost: 6,
  duration: "instant",
  effect_type: "damage",
  range: 10,
  usable_in: ["battle"],
});

const knock: Spell = spellFromRaw({
  id: "knock", name: "Knock",
  description: "Pop a lock.",
  allowable_classes: ["Wizard"],
  casting_type: "sorcerer",
  min_level: 2,
  mp_cost: 6,
  duration: "instant",
  effect_type: "knock",
  usable_in: ["dungeon"],
});

function makeParty() {
  return [
    memberFromRaw({ name: "Gimli",  class: "Fighter", race: "Dwarf",  level: 1, hp: 20 }),
    memberFromRaw({ name: "Merry",  class: "Thief",   race: "Halfling", level: 1, hp: 18 }),
    memberFromRaw({ name: "Gandolf",class: "Wizard",  race: "Elf",    level: 1, hp: 16, mp: 10 }),
    memberFromRaw({ name: "Selina", class: "Cleric",  race: "Human",  level: 1, hp: 18, mp: 12 }),
  ];
}

describe("minLevelFor", () => {
  it("uses class_min_levels when present", () => {
    const s = spellFromRaw({
      id: "x", name: "x", min_level: 1,
      class_min_levels: { Wizard: 1, Druid: 3 },
      allowable_classes: ["Wizard", "Druid"],
      mp_cost: 0, usable_in: ["battle"], casting_type: "", duration: "instant",
      effect_type: "",
    });
    expect(minLevelFor(s, "Wizard")).toBe(1);
    expect(minLevelFor(s, "Druid")).toBe(3);
  });

  it("falls back to min_level for classes not in the table", () => {
    const s = spellFromRaw({
      id: "x", name: "x", min_level: 4,
      class_min_levels: { Druid: 3 },
      allowable_classes: ["Wizard", "Druid"],
      mp_cost: 0, usable_in: ["battle"], casting_type: "", duration: "instant",
      effect_type: "",
    });
    expect(minLevelFor(s, "Wizard")).toBe(4);
  });
});

describe("castersFor", () => {
  it("filters by class, level, alive, and MP", () => {
    const p = makeParty();
    expect(castersFor(heal, p).map((m) => m.name)).toEqual(["Selina"]);
  });

  it("excludes a caster with insufficient MP", () => {
    const p = makeParty();
    p[3].mp = 2; // Selina now has 2 MP < 4 cost
    expect(castersFor(heal, p)).toEqual([]);
  });

  it("excludes a dead caster", () => {
    const p = makeParty();
    p[3].hp = 0;
    expect(castersFor(heal, p)).toEqual([]);
  });
});

describe("spellsCastableFromMenu", () => {
  it("returns spells castable outside combat by at least one party member", () => {
    const p = makeParty();
    // Knock requires min_level 2 — Gandolf at level 1 can't cast it.
    const list = spellsCastableFromMenu([heal, fireball, knock], p);
    const names = list.map((s) => s.name).sort();
    expect(names).toEqual(["Heal"]);
  });

  it("admits a spell once a member meets its min_level", () => {
    const p = makeParty();
    p[2].level = 2; // Gandolf hits Knock's threshold
    const list = spellsCastableFromMenu([knock], p);
    expect(list).toHaveLength(1);
  });

  it("drops a battle-only spell even when a caster meets requirements", () => {
    const p = makeParty();
    expect(spellsCastableFromMenu([fireball], p)).toEqual([]);
  });

  it("drops a spell when no caster meets MP / class / level", () => {
    const p = makeParty();
    p[2].mp = 0; // Gandolf no MP
    expect(spellsCastableFromMenu([knock], p)).toEqual([]);
  });
});
