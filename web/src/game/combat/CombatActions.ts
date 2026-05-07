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
 * Combat-side cast classification — drives the targeting flow.
 *
 *   - self        — applies to the caster; no picker
 *   - pick-ally   — choose a single party member
 *   - pick-enemy  — choose a single enemy
 *   - pick-tile   — place an effect at a chosen arena tile
 *                   (Fireball / Misty Step / Animate Dead)
 *   - mass-ally   — every alive ally (no picker)
 *   - mass-enemy  — every alive enemy (no picker)
 *   - unsupported — known effect but no resolution wired yet
 *
 * Combines `effect_type` with `targeting`; the data uses both, and
 * we honour the more specific one when available.
 */
export type CombatCastKind =
  | "self" | "pick-ally" | "pick-enemy" | "pick-tile"
  | "pick-direction"
  | "mass-ally" | "mass-enemy" | "unsupported";

export function classifyCombatCast(spell: Spell): CombatCastKind {
  const t = (spell.targeting ?? "").toLowerCase();
  const e = spell.effect_type;

  // Tile-targeted spells get a dedicated arena picker.
  if (t === "select_tile") return "pick-tile";
  if (e === "aoe_fireball" || e === "teleport" || e === "summon_skeleton") {
    return "pick-tile";
  }

  // Mass-effect spells with self targeting: Mass Heal, Restore.
  if (e === "mass_heal") return "mass-ally";
  // Bless is "self" in the data but the Python game applies it
  // party-wide — treat it as mass-ally so every alive ally gets the
  // attack-bonus buff.
  if (e === "bless") return "mass-ally";

  // Auto-against-all-enemies: Turn Undead's auto_monster targeting.
  if (e === "undead_damage" || t === "auto_monster") return "mass-enemy";

  // Self-only buffs and recoveries.
  if (t === "self") return "self";

  // Picker-driven targeting.
  if (t === "select_ally" || t === "select_ally_or_self") return "pick-ally";
  if (t === "select_enemy") return "pick-enemy";
  // Directional projectiles (Magic Dart-style): the player picks a
  // cardinal direction and the spell flies in a straight line until
  // it hits the first creature, a wall, or its `range` cap. Distinct
  // from pick-enemy (Magic Arrow) which lets the player click any foe.
  if (t === "directional_projectile") return "pick-direction";

  // Fallback by effect_type when targeting is missing or odd.
  if (e === "heal" || e === "major_heal" || e === "ac_buff" || e === "bless"
      || e === "range_buff" || e === "cure_poison" || e === "invisibility") {
    return "pick-ally";
  }
  if (e === "damage" || e === "lightning_bolt" || e === "sleep" || e === "charm"
      || e === "curse") {
    return "pick-enemy";
  }
  return "unsupported";
}

// ── Spell side-effects we don't (yet) model with a status engine ──
//
// Sleep / charm / curse / bless / ac_buff / range_buff /
// invisibility / cure_poison / restore all want a per-combatant
// "for N turns" effect tracker, which we haven't built. For now the
// cast resolves with a clean log line so the spell flow is visibly
// wired end-to-end — when the status-effect system lands these will
// pick up actual mechanics without touching the scene.
//
// Returns the human-readable verb that ends up in the log.
export function describeStatusCast(
  caster: Combatant, target: Combatant, spell: Spell,
): string {
  const e = spell.effect_type;
  if (e === "sleep")        return `${target.name} drifts into a magical sleep.`;
  if (e === "charm")        return `${target.name} is charmed by ${caster.name}.`;
  if (e === "curse")        return `${target.name} is cursed.`;
  if (e === "bless")        return `${caster.name} is blessed (+attack).`;
  if (e === "ac_buff")      return `${target.name} gains a magical shield.`;
  if (e === "range_buff")   return `${target.name}'s movement is hastened.`;
  if (e === "invisibility") return `${caster.name} fades from view.`;
  if (e === "cure_poison")  return `${target.name} is purged of poison.`;
  if (e === "restore")      return `${caster.name} is fully restored.`;
  return `${spell.name} has no visible effect.`;
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

/**
 * True when the item is a fire-and-forget ranged weapon — bows,
 * crossbows, slings. `Rock` is both throwable AND ranged; we treat
 * it as ranged here (the Throw menu still picks it up via
 * isThrowable, so authors can use either action).
 */
export function isRanged(item: Item): boolean {
  return !!item.ranged;
}

/**
 * Max attack range (in tiles) for a ranged weapon. Mirrors what the
 * Python game's combat tables use — long bows reach further than
 * short bows, crossbows are mid-range, slings + rocks are short.
 *
 * Falls back to 8 for ranged items the catalog doesn't recognise so
 * the action stays usable when new weapon types are added.
 */
export function maxRangeFor(item: Item): number {
  switch (item.itemType) {
    case "long_bow":  return 10;
    case "crossbow":  return 8;
    case "short_bow": return 6;
    case "sling":     return 6;
    case "rock":      return 4;
    default:
      return item.ranged ? 8 : 1;
  }
}

/**
 * Per-target outcome for Turn Undead — the scene needs both the dice
 * detail (for the log) and the resulting damage so it can flash/animate
 * the right combatant.
 */
export interface TurnUndeadOutcome {
  targetId: string;
  /** Raw d20. */
  saveRoll: number;
  /** d20 + saveBonus. */
  saveTotal: number;
  /** Computed difficulty class for this cast. */
  saveDc: number;
  /** False → destroyed completely; true → seared for hp_percent. */
  saved: boolean;
  damage: number;
  killed: boolean;
}

export interface TurnUndeadResult {
  /** Empty when there were no undead enemies on the field. */
  outcomes: TurnUndeadOutcome[];
  /** True iff the spell found at least one undead target. */
  hadTargets: boolean;
}

/**
 * Result of tracing a directional projectile (Magic Dart, Fireball-
 * direction) along a cardinal ray. Mirrors the Python game's
 * `_fire_fireball` ray walk:
 *
 *   - Step from origin in (dCol, dRow) up to `range` tiles.
 *   - Stop on the first wall (spell fizzles a tile short of the wall).
 *   - Stop on the first combatant (`hitId` is set; the caller decides
 *     friend or foe).
 *   - If nothing is in range, `fizzled` is true and `endCol/endRow`
 *     points to the last cell traversed.
 */
export interface DirectionalTrace {
  endCol: number;
  endRow: number;
  /** Combatant id of the first creature on the ray, or null. */
  hitId: string | null;
  /** True when the ray ran the full range without hitting anything. */
  fizzled: boolean;
}

/**
 * Walk one tile at a time from `origin` in `(dCol, dRow)` for up to
 * `range` steps. `isWallAt(c, r)` and `combatantAt(c, r)` are passed
 * in so this stays a pure function — the scene can wire it to the
 * arena helpers it already uses.
 */
export function traceDirectionalRay(
  origin: { col: number; row: number },
  delta: { dCol: number; dRow: number },
  range: number,
  isWallAt: (col: number, row: number) => boolean,
  combatantAt: (col: number, row: number) => Combatant | null,
): DirectionalTrace {
  let tc = origin.col + delta.dCol;
  let tr = origin.row + delta.dRow;
  let endCol = origin.col;
  let endRow = origin.row;
  for (let steps = 0; steps < range; steps++) {
    if (isWallAt(tc, tr)) {
      // Spell stops one tile short of the wall (stays on the last
      // open tile in the ray). If we hit a wall on the very first
      // step the ray didn't really travel — return the wall tile so
      // the projectile visual still has somewhere to land.
      return { endCol, endRow, hitId: null, fizzled: true };
    }
    const occ = combatantAt(tc, tr);
    if (occ) {
      return { endCol: tc, endRow: tr, hitId: occ.id, fizzled: false };
    }
    endCol = tc;
    endRow = tr;
    tc += delta.dCol;
    tr += delta.dRow;
  }
  // Ran out of range with nothing hit.
  return { endCol, endRow, hitId: null, fizzled: true };
}

/**
 * Build a Combatant for a summoned skeleton from an Animate Dead-style
 * spell. Reads the `skeleton_*` keys out of `spell.effect_value` and
 * falls back to sensible Skeleton-monster defaults when fields are
 * missing — mirrors src/states/combat.py::_cast_animate_dead.
 *
 * `id` is the unique combat id (the scene generates it); `casterName`
 * is just used to flavour the combatant's display name. The position
 * comes from the tile picker and is stamped on by Combat.addCombatant
 * later, so we leave a placeholder here.
 */
export function makeSummonedSkeleton(
  spell: Spell,
  id: string,
  casterName: string,
): Combatant {
  const ev = (spell.effect_value ?? {}) as Record<string, unknown>;
  const num = (k: string, dflt: number): number =>
    typeof ev[k] === "number" ? (ev[k] as number) : dflt;
  return {
    id,
    name: `${casterName}'s Skeleton`,
    side: "party",
    maxHp:        num("skeleton_hp", 30),
    hp:           num("skeleton_hp", 30),
    ac:           num("skeleton_ac", 14),
    attackBonus:  num("skeleton_attack", 6),
    damage: {
      dice:  num("skeleton_dmg_dice", 2),
      sides: num("skeleton_dmg_sides", 6),
      bonus: num("skeleton_dmg_bonus", 3),
    },
    dexMod: 1,
    color: [200, 200, 180],
    sprite: "/assets/monsters/skeleton.png",
    baseMoveRange: 3,
    position: { col: 0, row: 0 }, // overwritten by Combat.addCombatant
    undead: true,
    aiControlled: true,
  };
}

/**
 * Turn Undead resolution — Cleric/Paladin holy blast.
 *
 * Mirrors src/states/combat.py::_cast_turn_undead:
 *   - Filters monsters to those flagged `undead: true` in the data.
 *   - Each undead rolls d20 + max(0, attackBonus-2) vs save_dc
 *     (`save_dc_base + caster wisdom modifier`, default Wisdom).
 *   - Failure → HP set to 0 (destroyed completely).
 *   - Success → max(1, floor(maxHp * hp_percent)) damage.
 *
 * Returns per-target dice + damage so the scene can log and animate.
 * The `casterWisMod` argument lets the caller pre-compute the modifier
 * from PartyMember's wisdom score (or pass 0 for monster casters).
 */
export function resolveTurnUndead(
  enemies: Combatant[],
  spell: Spell,
  casterWisMod: number,
  rng: RNG,
): TurnUndeadResult {
  const ev = (spell.effect_value ?? {}) as Record<string, unknown>;
  const hpPct = typeof ev.hp_percent === "number" ? (ev.hp_percent as number) : 0.5;
  const dcBase = typeof ev.save_dc_base === "number" ? (ev.save_dc_base as number) : 10;
  const dcStat = typeof ev.save_dc_stat === "string" ? (ev.save_dc_stat as string) : "wisdom";

  const undeadTargets = enemies.filter((m) => m.hp > 0 && m.undead);
  if (undeadTargets.length === 0) {
    return { outcomes: [], hadTargets: false };
  }

  // Default to Wisdom — the data only ships wisdom/intelligence today.
  const saveDc = dcBase + (dcStat === "intelligence" ? 0 : casterWisMod);

  const outcomes: TurnUndeadOutcome[] = [];
  for (const t of undeadTargets) {
    const saveRoll = Math.floor(rng() * 20) + 1;
    const saveBonus = Math.max(0, t.attackBonus - 2);
    const saveTotal = saveRoll + saveBonus;
    if (saveTotal < saveDc) {
      const damage = t.hp;
      t.hp = 0;
      outcomes.push({
        targetId: t.id, saveRoll, saveTotal, saveDc,
        saved: false, damage, killed: true,
      });
    } else {
      const damage = Math.max(1, Math.floor(t.maxHp * hpPct));
      t.hp = Math.max(0, t.hp - damage);
      outcomes.push({
        targetId: t.id, saveRoll, saveTotal, saveDc,
        saved: true, damage, killed: t.hp === 0,
      });
    }
  }
  return { outcomes, hadTargets: true };
}
