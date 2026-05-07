import { describe, it, expect } from "vitest";
import {
  resolveThrow,
  resolveDamageSpell,
  resolveHealSpell,
  spellIsCombatCastable,
  isThrowable,
  isRanged,
  maxRangeFor,
  classifyCombatCast,
  describeStatusCast,
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

describe("isRanged + maxRangeFor", () => {
  it("isRanged is true for bows / crossbows", () => {
    expect(isRanged(longBow)).toBe(true);
  });
  it("isRanged is false for melee-only weapons", () => {
    expect(isRanged(dagger)).toBe(false);
  });

  it("maxRangeFor returns sensible defaults per item_type", () => {
    const make = (item_type: string): Item => ({
      name: item_type, category: "weapons", description: "",
      slots: ["right_hand"], characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null, ranged: true, itemType: item_type,
    });
    expect(maxRangeFor(make("long_bow"))).toBe(10);
    expect(maxRangeFor(make("crossbow"))).toBe(8);
    expect(maxRangeFor(make("short_bow"))).toBe(6);
    expect(maxRangeFor(make("sling"))).toBe(6);
    expect(maxRangeFor(make("rock"))).toBe(4);
  });

  it("maxRangeFor falls back to 8 for unknown ranged item_types", () => {
    const oddBow: Item = {
      name: "Glaive Launcher", category: "weapons", description: "",
      slots: ["right_hand"], characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null, ranged: true, itemType: "glaive_launcher",
    };
    expect(maxRangeFor(oddBow)).toBe(8);
  });

  it("maxRangeFor returns 1 for non-ranged items", () => {
    expect(maxRangeFor(dagger)).toBe(1);
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

function spell(over: Partial<Spell>): Spell {
  return spellFromRaw({
    id: over.id ?? "x",
    name: over.name ?? "X",
    description: "",
    allowable_classes: over.allowable_classes ?? ["Wizard"],
    casting_type: "sorcerer",
    min_level: 1,
    mp_cost: over.mp_cost ?? 4,
    duration: "instant",
    effect_type: over.effect_type ?? "damage",
    effect_value: over.effect_value,
    targeting: over.targeting,
    usable_in: over.usable_in ?? ["battle"],
  });
}

describe("classifyCombatCast", () => {
  it("self-targeted recovery / utility spells", () => {
    expect(classifyCombatCast(spell({ effect_type: "invisibility", targeting: "self" }))).toBe("self");
    expect(classifyCombatCast(spell({ effect_type: "restore",      targeting: "self" }))).toBe("self");
  });

  it("Bless is mass-ally even though the data tags it self (party-wide buff)", () => {
    expect(classifyCombatCast(spell({ effect_type: "bless", targeting: "self" }))).toBe("mass-ally");
  });

  it("mass-ally for mass_heal", () => {
    expect(classifyCombatCast(spell({ effect_type: "mass_heal", targeting: "self" }))).toBe("mass-ally");
  });

  it("mass-enemy for undead_damage / auto_monster", () => {
    expect(classifyCombatCast(spell({ effect_type: "undead_damage", targeting: "auto_monster" }))).toBe("mass-enemy");
  });

  it("pick-ally for select_ally / select_ally_or_self / heals", () => {
    expect(classifyCombatCast(spell({ effect_type: "ac_buff",  targeting: "select_ally" }))).toBe("pick-ally");
    expect(classifyCombatCast(spell({ effect_type: "heal",     targeting: "select_ally_or_self" }))).toBe("pick-ally");
    expect(classifyCombatCast(spell({ effect_type: "cure_poison", targeting: "select_ally" }))).toBe("pick-ally");
  });

  it("pick-enemy for select_enemy / directional_projectile / damage spells", () => {
    expect(classifyCombatCast(spell({ effect_type: "damage", targeting: "directional_projectile" }))).toBe("pick-enemy");
    expect(classifyCombatCast(spell({ effect_type: "sleep",  targeting: "select_enemy" }))).toBe("pick-enemy");
    expect(classifyCombatCast(spell({ effect_type: "curse",  targeting: "select_enemy" }))).toBe("pick-enemy");
  });

  it("tile-targeted spells classify as pick-tile", () => {
    expect(classifyCombatCast(spell({ effect_type: "aoe_fireball",   targeting: "select_tile" }))).toBe("pick-tile");
    expect(classifyCombatCast(spell({ effect_type: "teleport",       targeting: "select_tile" }))).toBe("pick-tile");
    expect(classifyCombatCast(spell({ effect_type: "summon_skeleton",targeting: "select_tile" }))).toBe("pick-tile");
  });

  it("aoe / teleport / summon classify as pick-tile even when targeting is missing", () => {
    expect(classifyCombatCast(spell({ effect_type: "aoe_fireball" }))).toBe("pick-tile");
    expect(classifyCombatCast(spell({ effect_type: "teleport" }))).toBe("pick-tile");
    expect(classifyCombatCast(spell({ effect_type: "summon_skeleton" }))).toBe("pick-tile");
  });
});

describe("describeStatusCast", () => {
  const caster = { id: "c", name: "Gandolf" } as Combatant;
  const target = { id: "t", name: "Wolf" } as Combatant;
  it("renders a flavour line per status effect", () => {
    expect(describeStatusCast(caster, target, spell({ effect_type: "sleep" })))
      .toMatch(/sleep/i);
    expect(describeStatusCast(caster, target, spell({ effect_type: "charm" })))
      .toMatch(/charmed/i);
    expect(describeStatusCast(caster, target, spell({ effect_type: "ac_buff" })))
      .toMatch(/shield/i);
    expect(describeStatusCast(caster, caster, spell({ effect_type: "bless" })))
      .toMatch(/blessed/i);
    expect(describeStatusCast(caster, caster, spell({ effect_type: "invisibility" })))
      .toMatch(/fades/i);
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
