import { describe, it, expect } from "vitest";
import {
  resolveThrow,
  resolveDamageSpell,
  resolveHealSpell,
  spellIsCombatCastable,
  isThrowable,
} from "./CombatActions";
import { spellFromRaw, type Spell } from "../world/Spells";
import { mulberry32 } from "../rng";
import type { Combatant } from "../types";
import type { Item } from "../world/Items";

function makeCombatant(over: Partial<Combatant> = {}): Combatant {
  return {
    id:             over.id   ?? "x",
    name:           over.name ?? "X",
    side:           over.side ?? "party",
    maxHp:          over.maxHp ?? 20,
    hp:             over.hp ?? 20,
    ac:             over.ac ?? 12,
    attackBonus:    over.attackBonus ?? 2,
    damage:         over.damage ?? { dice: 1, sides: 6, bonus: 0 },
    dexMod:         over.dexMod ?? 0,
    color:          over.color ?? [200, 200, 200],
    baseMoveRange:  over.baseMoveRange ?? 4,
    position:       over.position ?? { col: 5, row: 5 },
  };
}

const dagger: Item = {
  name: "Dagger", category: "weapons", description: "",
  slots: ["right_hand", "left_hand"],
  characterCanEquip: true, partyCanEquip: false,
  usable: false, effect: null,
  power: 3, ranged: false, melee: true, throwable: true, durability: 20,
};
const longBow: Item = {
  name: "Long Bow", category: "weapons", description: "",
  slots: ["right_hand"],
  characterCanEquip: true, partyCanEquip: false,
  usable: false, effect: null,
  power: 5, ranged: true, melee: false, throwable: false,
};
const healingHerb: Item = {
  name: "Healing Herb", category: "general", description: "",
  slots: [], characterCanEquip: false, partyCanEquip: false,
  usable: true, effect: "heal_hp",
};

describe("isThrowable", () => {
  it("only flags items with throwable: true", () => {
    expect(isThrowable(dagger)).toBe(true);
  });
  it("does NOT flag ranged-only weapons (bows belong to a ranged-attack action)", () => {
    expect(isThrowable(longBow)).toBe(false);
  });
  it("rejects non-equippable consumables", () => {
    expect(isThrowable(healingHerb)).toBe(false);
  });
});

describe("resolveThrow", () => {
  it("hits when the d20 + bonus clears AC and deals at least 1 damage", () => {
    const attacker = makeCombatant({ id: "a", attackBonus: 99 });
    const target = makeCombatant({ id: "t", side: "enemies", ac: 10, hp: 20, maxHp: 20 });
    const r = resolveThrow(attacker, target, dagger, mulberry32(1));
    expect(r.hit).toBe(true);
    expect(r.damage).toBeGreaterThan(0);
    expect(target.hp).toBe(20 - r.damage);
    expect(r.item).toBe("Dagger");
  });

  it("misses when the roll never beats AC", () => {
    const attacker = makeCombatant({ id: "a", attackBonus: -100 });
    const target = makeCombatant({ id: "t", side: "enemies", ac: 30 });
    const r = resolveThrow(attacker, target, dagger, mulberry32(1));
    expect(r.hit).toBe(false);
    expect(r.damage).toBe(0);
    expect(target.hp).toBe(20);
  });

  it("kills cleanly and reports it", () => {
    const attacker = makeCombatant({ id: "a", attackBonus: 99 });
    const target = makeCombatant({ id: "t", side: "enemies", ac: 1, hp: 1, maxHp: 1 });
    const r = resolveThrow(attacker, target, dagger, mulberry32(1));
    expect(r.killed).toBe(true);
    expect(target.hp).toBe(0);
  });

  it("returns a no-op against an already-downed target", () => {
    const attacker = makeCombatant({ id: "a" });
    const target = makeCombatant({ id: "t", side: "enemies", hp: 0 });
    const r = resolveThrow(attacker, target, dagger, mulberry32(1));
    expect(r.hit).toBe(false);
    expect(r.damage).toBe(0);
  });

  it("uses item.power as a damage bonus on a 1d6 base", () => {
    // Bow has higher power → on a hit with rng=0 we still see at
    // least power+1 damage (1d6 = 1, bonus = power).
    const attacker = makeCombatant({ id: "a", attackBonus: 99 });
    const target = makeCombatant({ id: "t", side: "enemies", ac: 1, hp: 100, maxHp: 100 });
    const r = resolveThrow(attacker, target, longBow, mulberry32(1));
    expect(r.damage).toBeGreaterThanOrEqual(longBow.power!);
  });
});

describe("resolveDamageSpell", () => {
  const fireball: Spell = spellFromRaw({
    id: "fireball", name: "Magic Dart", description: "",
    allowable_classes: ["Wizard"], casting_type: "sorcerer",
    min_level: 1, mp_cost: 6, duration: "instant",
    effect_type: "damage",
    effect_value: { dice_count: 2, dice_sides: 6 },
    usable_in: ["battle"],
  });

  it("does the dice roll and reduces target HP", () => {
    const caster = makeCombatant({ id: "c", attackBonus: 0 });
    const target = makeCombatant({ id: "t", side: "enemies", hp: 50, maxHp: 50 });
    const r = resolveDamageSpell(caster, target, fireball, mulberry32(1));
    expect(r.hit).toBe(true);
    expect(r.damage).toBeGreaterThan(0);
    expect(target.hp).toBe(50 - r.damage);
  });

  it("no-ops on a downed target", () => {
    const caster = makeCombatant({ id: "c" });
    const target = makeCombatant({ id: "t", side: "enemies", hp: 0 });
    const r = resolveDamageSpell(caster, target, fireball, mulberry32(1));
    expect(r.damage).toBe(0);
  });
});

describe("resolveHealSpell", () => {
  const heal: Spell = spellFromRaw({
    id: "heal", name: "Heal", description: "",
    allowable_classes: ["Cleric"], casting_type: "priest",
    min_level: 1, mp_cost: 4, duration: "instant",
    effect_type: "heal",
    effect_value: { dice_count: 1, dice_sides: 8 },
    usable_in: ["battle", "town"],
  });

  it("heals the target up to maxHp", () => {
    const caster = makeCombatant({ id: "c" });
    const target = makeCombatant({ id: "t", side: "party", hp: 4, maxHp: 20 });
    const r = resolveHealSpell(caster, target, heal, mulberry32(1));
    expect(r.heal).toBeGreaterThan(0);
    expect(target.hp).toBeGreaterThan(4);
    expect(target.hp).toBeLessThanOrEqual(20);
  });

  it("clamps healed HP at maxHp", () => {
    const caster = makeCombatant({ id: "c" });
    const target = makeCombatant({ id: "t", side: "party", hp: 19, maxHp: 20 });
    resolveHealSpell(caster, target, heal, mulberry32(1));
    expect(target.hp).toBe(20);
  });
});

describe("spellIsCombatCastable", () => {
  const battleSpell: Spell = spellFromRaw({
    id: "x", name: "X", description: "", allowable_classes: ["Wizard"],
    casting_type: "sorcerer", min_level: 1, mp_cost: 4, duration: "instant",
    effect_type: "damage", usable_in: ["battle"],
  });
  const utilitySpell: Spell = spellFromRaw({
    id: "y", name: "Y", description: "", allowable_classes: ["Wizard"],
    casting_type: "sorcerer", min_level: 1, mp_cost: 4, duration: "instant",
    effect_type: "knock", usable_in: ["dungeon"],
  });

  it("is true for battle-tagged spells the class can cast", () => {
    expect(spellIsCombatCastable(battleSpell, "Wizard")).toBe(true);
  });

  it("is false for spells without the battle context", () => {
    expect(spellIsCombatCastable(utilitySpell, "Wizard")).toBe(false);
  });

  it("is false for the wrong class", () => {
    expect(spellIsCombatCastable(battleSpell, "Cleric")).toBe(false);
  });
});
