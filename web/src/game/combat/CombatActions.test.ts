import { describe, it, expect } from "vitest";
import {
  resolveThrow,
  resolveDamageSpell,
  resolveHealSpell,
  resolveTurnUndead,
  makeSummonedSkeleton,
  traceDirectionalRay,
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
    strength:       over.strength,
    dexterity:      over.dexterity,
    intelligence:   over.intelligence,
    wisdom:         over.wisdom,
    color:          over.color ?? [200, 200, 200],
    baseMoveRange:  over.baseMoveRange ?? 4,
    position:       over.position ?? { col: 5, row: 5 },
    undead:         over.undead,
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

  it("adds the caster's stat_bonus modifier to the dice damage", () => {
    // Magic Arrow ships with `stat_bonus: "intelligence"` in the
    // shipped data — mirror that here.
    const arrow: Spell = spellFromRaw({
      id: "magic_arrow", name: "Magic Arrow", description: "",
      allowable_classes: ["Wizard"], casting_type: "sorcerer",
      min_level: 1, mp_cost: 4, duration: "instant",
      effect_type: "damage",
      effect_value: { dice_count: 2, dice_sides: 8, stat_bonus: "intelligence" },
      usable_in: ["battle"],
    });
    const wizard = makeCombatant({ id: "w", intelligence: 18 }); // +4 INT mod
    const dummy  = makeCombatant({ id: "d", intelligence: 10 }); // +0 INT mod
    const target1 = makeCombatant({ id: "t1", side: "enemies", hp: 99, maxHp: 99 });
    const target2 = makeCombatant({ id: "t2", side: "enemies", hp: 99, maxHp: 99 });
    // Same RNG seed → same dice rolls. The wizard's INT bump is the
    // only source of difference.
    const r1 = resolveDamageSpell(wizard, target1, arrow, mulberry32(7));
    const r2 = resolveDamageSpell(dummy,  target2, arrow, mulberry32(7));
    expect(r1.damage - r2.damage).toBe(4);
  });

  it("ignores stat_bonus when the caster has no ability score", () => {
    const arrow: Spell = spellFromRaw({
      id: "magic_arrow", name: "Magic Arrow", description: "",
      allowable_classes: ["Wizard"], casting_type: "sorcerer",
      min_level: 1, mp_cost: 4, duration: "instant",
      effect_type: "damage",
      effect_value: { dice_count: 1, dice_sides: 4, stat_bonus: "intelligence" },
      usable_in: ["battle"],
    });
    // No `intelligence` field → defaults to 0 modifier.
    const monster = makeCombatant({ id: "m" });
    const target = makeCombatant({ id: "t", side: "party", hp: 50, maxHp: 50 });
    const r = resolveDamageSpell(monster, target, arrow, mulberry32(7));
    expect(r.damage).toBeGreaterThan(0); // didn't crash; minimum-1 still applies
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

  it("adds the caster's WIS modifier when stat_bonus = 'wisdom'", () => {
    const cleric: Spell = spellFromRaw({
      id: "heal", name: "Heal", description: "",
      allowable_classes: ["Cleric"], casting_type: "priest",
      min_level: 1, mp_cost: 4, duration: "instant",
      effect_type: "heal",
      effect_value: { dice_count: 1, dice_sides: 6, stat_bonus: "wisdom" },
      usable_in: ["battle", "town"],
    });
    const wise   = makeCombatant({ id: "c", wisdom: 18 }); // +4 WIS
    const novice = makeCombatant({ id: "c", wisdom: 10 }); // +0 WIS
    const t1 = makeCombatant({ id: "t1", side: "party", hp: 1, maxHp: 99 });
    const t2 = makeCombatant({ id: "t2", side: "party", hp: 1, maxHp: 99 });
    const r1 = resolveHealSpell(wise,   t1, cleric, mulberry32(3));
    const r2 = resolveHealSpell(novice, t2, cleric, mulberry32(3));
    expect(r1.heal - r2.heal).toBe(4);
  });

  it("honours an `hp_amount` field as a flat heal override", () => {
    const flat: Spell = spellFromRaw({
      id: "potion_heal", name: "Potion Heal", description: "",
      allowable_classes: ["Cleric"], casting_type: "priest",
      min_level: 1, mp_cost: 4, duration: "instant",
      effect_type: "heal",
      effect_value: { dice_count: 99, dice_sides: 99, hp_amount: 12 },
      usable_in: ["battle"],
    });
    const caster = makeCombatant({ id: "c" });
    const target = makeCombatant({ id: "t", side: "party", hp: 5, maxHp: 50 });
    const r = resolveHealSpell(caster, target, flat, mulberry32(9));
    // Despite massive dice in the payload, hp_amount wins.
    expect(r.heal).toBe(12);
    expect(target.hp).toBe(17);
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

  it("pick-enemy for select_enemy / damage spells", () => {
    expect(classifyCombatCast(spell({ effect_type: "sleep",  targeting: "select_enemy" }))).toBe("pick-enemy");
    expect(classifyCombatCast(spell({ effect_type: "curse",  targeting: "select_enemy" }))).toBe("pick-enemy");
  });

  it("pick-direction for directional_projectile (Magic Dart)", () => {
    expect(classifyCombatCast(spell({ effect_type: "damage", targeting: "directional_projectile" }))).toBe("pick-direction");
  });

  it("Magic Arrow (select_enemy) is pick-enemy, NOT pick-direction", () => {
    // Magic Arrow's data uses select_enemy + range:99 — the
    // classifier must distinguish it from Magic Dart's directional
    // flow even though both share effect_type=damage.
    expect(classifyCombatCast(spell({ effect_type: "damage", targeting: "select_enemy" }))).toBe("pick-enemy");
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

describe("resolveTurnUndead", () => {
  const turnUndead: Spell = spellFromRaw({
    id: "turn_undead", name: "Turn Undead", description: "",
    allowable_classes: ["Cleric", "Paladin"],
    casting_type: "priest", min_level: 2, mp_cost: 0, duration: "instant",
    effect_type: "undead_damage",
    effect_value: { hp_percent: 0.5, save_dc_base: 10, save_dc_stat: "wisdom" },
    targeting: "auto_monster", usable_in: ["battle"],
  });

  it("ignores non-undead enemies entirely", () => {
    const goblin = makeCombatant({
      id: "g", name: "Goblin", side: "enemies", hp: 10, maxHp: 10, attackBonus: 2,
    });
    const skeleton = makeCombatant({
      id: "s", name: "Skeleton", side: "enemies", hp: 10, maxHp: 10, attackBonus: 3,
      undead: true,
    });
    const result = resolveTurnUndead([goblin, skeleton], turnUndead, /*wisMod*/ 2, mulberry32(1));
    // Only one outcome — the skeleton.
    expect(result.outcomes).toHaveLength(1);
    expect(result.outcomes[0].targetId).toBe("s");
    // Goblin is untouched.
    expect(goblin.hp).toBe(10);
  });

  it("returns hadTargets=false when there are no undead at all", () => {
    const goblin = makeCombatant({
      id: "g", name: "Goblin", side: "enemies", hp: 10, maxHp: 10,
    });
    const result = resolveTurnUndead([goblin], turnUndead, 2, mulberry32(1));
    expect(result.hadTargets).toBe(false);
    expect(result.outcomes).toHaveLength(0);
    expect(goblin.hp).toBe(10);
  });

  it("destroys undead that fail their save (HP set to 0)", () => {
    // Save DC = 10 + wisMod(4) = 14. Skeleton attackBonus 3 → save bonus 1.
    // Even a d20 = 12 → total 13 < 14 → fails. Find a seed that yields a
    // low roll. mulberry32(0) starts low — verify the outcome is failure.
    const skeleton = makeCombatant({
      id: "s", name: "Skeleton", side: "enemies", hp: 12, maxHp: 12, attackBonus: 3,
      undead: true,
    });
    // Use a seed that's reproducible. With save DC = 14 we expect at
    // least one of the first few rolls to fail.
    const rng = mulberry32(99);
    const result = resolveTurnUndead([skeleton], turnUndead, /*wisMod*/ 4, rng);
    const o = result.outcomes[0];
    if (!o.saved) {
      expect(o.damage).toBe(12);    // full HP destroyed
      expect(skeleton.hp).toBe(0);
      expect(o.killed).toBe(true);
    } else {
      // Survives — must take exactly hp_percent of maxHp = 6.
      expect(o.damage).toBe(6);
      expect(skeleton.hp).toBe(6);
    }
  });

  it("seared-but-alive case deals max(1, floor(maxHp * hp_percent))", () => {
    // Tiny zombie with maxHp=3 → floor(3 * 0.5) = 1. Force a successful
    // save by setting wisMod negative so the DC drops below the
    // worst-possible roll.
    const zombie = makeCombatant({
      id: "z", name: "Zombie", side: "enemies", hp: 3, maxHp: 3, attackBonus: 5,
      undead: true,
    });
    // DC = 10 + (-5) = 5. attackBonus 5 → save bonus 3. Lowest possible
    // total = 1+3 = 4 < 5 — uh, that fails. Bump wisMod down further.
    const result = resolveTurnUndead([zombie], turnUndead, /*wisMod*/ -10, mulberry32(7));
    const o = result.outcomes[0];
    // DC = 10 + (-10) = 0. Any save passes.
    expect(o.saved).toBe(true);
    expect(o.damage).toBe(1);     // max(1, floor(3*0.5)) = max(1, 1)
    expect(zombie.hp).toBe(2);
  });

  it("includes saveRoll/saveTotal/saveDc in each outcome for the log", () => {
    const skeleton = makeCombatant({
      id: "s", name: "Skeleton", side: "enemies", hp: 10, maxHp: 10, attackBonus: 3,
      undead: true,
    });
    const result = resolveTurnUndead([skeleton], turnUndead, /*wisMod*/ 0, mulberry32(3));
    const o = result.outcomes[0];
    expect(o.saveRoll).toBeGreaterThanOrEqual(1);
    expect(o.saveRoll).toBeLessThanOrEqual(20);
    expect(o.saveDc).toBe(10);    // dc_base 10 + 0 wisMod
    // saveTotal = saveRoll + max(0, attackBonus - 2) = saveRoll + 1
    expect(o.saveTotal).toBe(o.saveRoll + 1);
  });
});

describe("makeSummonedSkeleton", () => {
  const animateDead: Spell = spellFromRaw({
    id: "animate_dead", name: "Animate Dead", description: "",
    allowable_classes: ["Wizard"],
    casting_type: "sorcerer", min_level: 6, mp_cost: 20, duration: 5,
    effect_type: "summon_skeleton",
    effect_value: {
      skeleton_hp: 30, skeleton_ac: 14, skeleton_attack: 6,
      skeleton_dmg_dice: 2, skeleton_dmg_sides: 6, skeleton_dmg_bonus: 3,
    },
    targeting: "select_tile", usable_in: ["battle"],
  });

  it("reads stats from spell.effect_value", () => {
    const c = makeSummonedSkeleton(animateDead, "summon-1", "Gandolf");
    expect(c.maxHp).toBe(30);
    expect(c.hp).toBe(30);
    expect(c.ac).toBe(14);
    expect(c.attackBonus).toBe(6);
    expect(c.damage).toEqual({ dice: 2, sides: 6, bonus: 3 });
  });

  it("flags the summon as undead, party-side, AI-controlled", () => {
    const c = makeSummonedSkeleton(animateDead, "summon-1", "Gandolf");
    expect(c.undead).toBe(true);
    expect(c.side).toBe("party");
    expect(c.aiControlled).toBe(true);
  });

  it("names the skeleton after its summoner", () => {
    const c = makeSummonedSkeleton(animateDead, "summon-1", "Selina");
    expect(c.name).toContain("Selina");
    expect(c.name.toLowerCase()).toContain("skeleton");
  });

  it("falls back to defaults when effect_value is missing fields", () => {
    const stripped = spellFromRaw({
      id: "weak_summon", name: "Weak Summon", description: "",
      allowable_classes: ["Wizard"], casting_type: "sorcerer",
      min_level: 1, mp_cost: 1, duration: 1,
      effect_type: "summon_skeleton",
      effect_value: {},
      targeting: "select_tile", usable_in: ["battle"],
    });
    const c = makeSummonedSkeleton(stripped, "summon-2", "Gandolf");
    // Default skeleton spec — nothing should be NaN.
    expect(Number.isNaN(c.maxHp)).toBe(false);
    expect(Number.isNaN(c.ac)).toBe(false);
    expect(c.maxHp).toBeGreaterThan(0);
  });
});

describe("traceDirectionalRay", () => {
  // No walls in these tests — we explicitly stub isWallAt to false.
  const noWalls = (): boolean => false;
  const noOne = (): Combatant | null => null;

  it("returns the first combatant in the path as hitId", () => {
    const goblin = makeCombatant({
      id: "g", name: "Goblin", side: "enemies", position: { col: 5, row: 2 },
    });
    const at = (c: number, r: number): Combatant | null =>
      (c === goblin.position.col && r === goblin.position.row) ? goblin : null;
    // Caster at (5,5), firing north (dRow = -1). Goblin is at (5,2).
    const trace = traceDirectionalRay(
      { col: 5, row: 5 }, { dCol: 0, dRow: -1 }, /*range*/ 10, noWalls, at,
    );
    expect(trace.hitId).toBe("g");
    expect(trace.endCol).toBe(5);
    expect(trace.endRow).toBe(2);
    expect(trace.fizzled).toBe(false);
  });

  it("stops one tile short of a wall and reports fizzled", () => {
    const wallAt = (c: number, r: number): boolean => (c === 5 && r === 2);
    const trace = traceDirectionalRay(
      { col: 5, row: 5 }, { dCol: 0, dRow: -1 }, 10, wallAt, noOne,
    );
    expect(trace.hitId).toBe(null);
    expect(trace.fizzled).toBe(true);
    // Last open tile reached before the wall.
    expect(trace.endRow).toBe(3);
  });

  it("respects the spell range cap", () => {
    // Range 3 tiles — caster at (5,5) firing south stops at row 8.
    const trace = traceDirectionalRay(
      { col: 5, row: 5 }, { dCol: 0, dRow: 1 }, 3, noWalls, noOne,
    );
    expect(trace.hitId).toBe(null);
    expect(trace.fizzled).toBe(true);
    expect(trace.endCol).toBe(5);
    expect(trace.endRow).toBe(8);
  });

  it("stops at the closer of two enemies", () => {
    const near = makeCombatant({
      id: "near", side: "enemies", position: { col: 5, row: 3 },
    });
    const far  = makeCombatant({
      id: "far",  side: "enemies", position: { col: 5, row: 1 },
    });
    const at = (c: number, r: number): Combatant | null =>
      (c === near.position.col && r === near.position.row) ? near :
      (c === far.position.col  && r === far.position.row)  ? far  : null;
    const trace = traceDirectionalRay(
      { col: 5, row: 5 }, { dCol: 0, dRow: -1 }, 10, noWalls, at,
    );
    expect(trace.hitId).toBe("near");
    expect(trace.endRow).toBe(3);
  });

  it("works for east/west and other cardinals", () => {
    const target = makeCombatant({
      id: "e", side: "enemies", position: { col: 9, row: 5 },
    });
    const at = (c: number, r: number): Combatant | null =>
      (c === target.position.col && r === target.position.row) ? target : null;
    const trace = traceDirectionalRay(
      { col: 5, row: 5 }, { dCol: 1, dRow: 0 }, 10, noWalls, at,
    );
    expect(trace.hitId).toBe("e");
    expect(trace.endCol).toBe(9);
  });
});
