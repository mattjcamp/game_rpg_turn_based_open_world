/**
 * Data-driven combat actions — Throw, Cast, ranged attack.
 *
 * Each function is pure: takes the actor / target / item-or-spell
 * data, returns an `AttackResult`-shaped record so the combat log,
 * floating damage text, and HP refresh paths can stay shared with
 * the existing bump-attack flow.
 *
 * Item definitions come from `data/items.json` (via `Items.ts`),
 * spell definitions from `data/spells.json` (via `Spells.ts`). The
 * scene picks the relevant entry, calls the helper, then animates
 * + logs the result.
 */

import type { Combatant, AttackResult } from "../types";
import type { Item } from "../world/Items";
import type { Spell } from "../world/Spells";
import { rollAttack, rollDamage } from "./engine";
import type { RNG } from "../rng";

/**
 * Throwable / ranged attack — used by the Throw action and by ranged
 * weapons like bows. Damage scales off `item.power` (from the item
 * catalog). Treats the attacker's `attackBonus` as a +to-hit bonus
 * and the target's `ac` for the saving throw, exactly like the
 * melee bump-attack — that keeps the dice math identical.
 */
export function resolveThrow(
  attacker: Combatant,
  target: Combatant,
  item: Item,
  rng: RNG,
): AttackResult & { item: string } {
  if (target.hp <= 0) {
    return {
      attackerId: attacker.id, targetId: target.id,
      hit: false, roll: 0, total: 0, critical: false,
      damage: 0, killed: false, item: item.name,
    };
  }
  const roll = rollAttack(attacker.attackBonus, target.ac, rng);
  let damage = 0;
  // Use item.power as the dice bonus on a single d6 — mirrors the
  // Python combat_engine's throw resolution where a thrown item
  // does ~ 1d6 + power damage. Bows / crossbows have higher power.
  const power = item.power ?? 1;
  if (roll.hit) {
    damage = rollDamage(1, 6, power, roll.critical, rng);
    target.hp = Math.max(0, target.hp - damage);
  }
  return {
    attackerId: attacker.id,
    targetId: target.id,
    hit: roll.hit,
    roll: roll.roll,
    total: roll.total,
    critical: roll.critical,
    damage,
    killed: target.hp === 0 && roll.hit,
    item: item.name,
  };
}

/**
 * Single-target damage spell — used for Magic Dart, Lightning Bolt,
 * and other `effect_type: damage`/`undead_damage` spells in combat.
 *
 * Reads `effect_value.dice_count`/`dice_sides` (or parses `dice` like
 * "2d6") from the spell, plus an optional caster stat bonus.
 */
export function resolveDamageSpell(
  caster: Combatant,
  target: Combatant,
  spell: Spell,
  rng: RNG,
): AttackResult & { spell: string } {
  if (target.hp <= 0) {
    return {
      attackerId: caster.id, targetId: target.id,
      hit: false, roll: 0, total: 0, critical: false,
      damage: 0, killed: false, spell: spell.name,
    };
  }
  // Damage spells generally hit unless the spell explicitly calls
  // for a saving throw — the data we ship doesn't include that
  // detail yet, so we treat them as auto-hit at full power. The
  // d20 + attackBonus check stays in the result for log parity.
  const roll = rollAttack(caster.attackBonus, target.ac, rng);
  const ev = spell.effect_value ?? {};
  let dice = 0;
  if (typeof ev.dice_count === "number" && typeof ev.dice_sides === "number") {
    dice = rollDamage(ev.dice_count, ev.dice_sides, 0, false, rng);
  } else if (typeof ev.dice === "string") {
    const m = /^(\d+)d(\d+)$/.exec(ev.dice);
    if (m) dice = rollDamage(parseInt(m[1], 10), parseInt(m[2], 10), 0, false, rng);
  } else {
    // Fallback for spells without explicit dice — small chip damage.
    dice = rollDamage(1, 4, 0, false, rng);
  }
  const damage = Math.max(1, dice);
  target.hp = Math.max(0, target.hp - damage);
  return {
    attackerId: caster.id,
    targetId: target.id,
    hit: true,
    roll: roll.roll,
    total: roll.total,
    critical: false,
    damage,
    killed: target.hp === 0,
    spell: spell.name,
  };
}

/**
 * Single-target heal — used for `heal` / `major_heal` spells cast
 * during combat. Mutates the target's HP up to maxHp. Returns a
 * shared shape with `heal: amount`.
 */
export function resolveHealSpell(
  caster: Combatant,
  target: Combatant,
  spell: Spell,
  rng: RNG,
): { attackerId: string; targetId: string; heal: number; spell: string } {
  const ev = spell.effect_value ?? {};
  let amount = 0;
  if (typeof ev.dice_count === "number" && typeof ev.dice_sides === "number") {
    amount = rollDamage(ev.dice_count, ev.dice_sides, 0, false, rng);
  } else if (typeof ev.dice === "string") {
    const m = /^(\d+)d(\d+)$/.exec(ev.dice);
    if (m) amount = rollDamage(parseInt(m[1], 10), parseInt(m[2], 10), 0, false, rng);
  } else {
    const defaults: Record<string, [number, number]> = {
      heal:        [1, 8],
      major_heal:  [2, 8],
      mass_heal:   [1, 6],
    };
    const def = defaults[spell.effect_type];
    if (def) amount = rollDamage(def[0], def[1], 0, false, rng);
  }
  amount = Math.max(1, amount);
  const before = target.hp;
  target.hp = Math.min(target.maxHp, target.hp + amount);
  return {
    attackerId: caster.id,
    targetId: target.id,
    heal: target.hp - before,
    spell: spell.name,
  };
}

/**
 * Whether a spell is castable in combat by this combatant's class
 * (we look up class via the bridge in the scene). Convenience
 * filter over spell.usable_in + spell.allowable_classes.
 */
export function spellIsCombatCastable(
  spell: Spell, callerClass: string,
): boolean {
  if (!spell.usable_in.includes("battle")) return false;
  return spell.allowable_classes
    .some((c) => c.toLowerCase() === callerClass.toLowerCase());
}

/**
 * Strictly filter a flat catalog of items for "throwable in combat".
 * Mirrors the items.json `throwable` flag — daggers, rocks, fire
 * oils, poison vials. Ranged weapons (bows, crossbows, slings) have
 * `ranged: true` but `throwable: false`; they belong to a separate
 * ranged-attack flow, not the Throw menu.
 */
export function isThrowable(item: Item): boolean {
  return !!item.throwable;
}
