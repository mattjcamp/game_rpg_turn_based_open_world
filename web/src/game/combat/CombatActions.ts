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
import { isCombatUsable } from "../world/Items";
import type { Spell } from "../world/Spells";
import type { PartyMember } from "../world/Party";
import { rollAttack, rollDamage } from "./engine";
import type { RNG } from "../rng";
import { assetUrl } from "../world/Module";
import type { Buff } from "./Buffs";

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
 * Mirrors the Python combat resolution at `src/states/combat.py:2653`:
 *   damage = roll(dice_count d dice_sides) + caster's stat-mod bonus
 *
 * `effect_value.stat_bonus` names the ability ("intelligence",
 * "wisdom", …) — Magic Arrow scales with INT, future spells can pick
 * any stat. Without the bonus the web port shipped a flat dice roll
 * that ignored the caster's primary attribute entirely.
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
  const damage = rollSpellDamage(spell, caster, rng);
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
 * Roll dice + stat_bonus for a damage spell. Pure helper so AOE /
 * directional / single-target paths all share one source of truth.
 */
export function rollSpellDamage(spell: Spell, caster: Combatant, rng: RNG): number {
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
  const bonus = casterStatBonus(caster, ev.stat_bonus);
  return Math.max(1, dice + bonus);
}

/** Read the caster's modifier for the named ability, defaulting to 0
 *  when the spell omits a stat_bonus or the Combatant lacks the
 *  ability score (monsters before we port their stat blocks). */
function casterStatBonus(caster: Combatant, statName: unknown): number {
  if (typeof statName !== "string") return 0;
  const stat = readAbility(caster, statName);
  if (stat === undefined) return 0;
  return Math.floor((stat - 10) / 2);
}

function readAbility(c: Combatant, name: string): number | undefined {
  switch (name.toLowerCase()) {
    case "strength":     return c.strength;
    case "dexterity":    return c.dexterity;
    case "intelligence": return c.intelligence;
    case "wisdom":       return c.wisdom;
    default:             return undefined;
  }
}

/**
 * Single-target heal — used for `heal` / `major_heal` spells cast
 * during combat. Mutates the target's HP up to maxHp. Returns a
 * shared shape with `heal: amount`.
 *
 * Mirrors `Member.cast_heal_in_combat` at `src/states/combat.py:2977`:
 *   hp_amount > 0  → flat amount (overrides dice)
 *   else           → dice + stat_bonus mod (WIS for cleric heals)
 */
export function resolveHealSpell(
  caster: Combatant,
  target: Combatant,
  spell: Spell,
  rng: RNG,
): { attackerId: string; targetId: string; heal: number; spell: string } {
  const amount = rollSpellHeal(spell, caster, rng);
  const before = target.hp;
  target.hp = Math.min(target.maxHp, target.hp + amount);
  return {
    attackerId: caster.id,
    targetId: target.id,
    heal: target.hp - before,
    spell: spell.name,
  };
}

/** Roll dice + stat_bonus for a heal spell. Honours `hp_amount` as a
 *  flat-amount override (mirrors the out-of-combat `rollHeal` at
 *  `web/src/game/world/PartyActions.ts:718` plus the Python combat
 *  branch). Shared between single-target and mass-heal paths. */
export function rollSpellHeal(spell: Spell, caster: Combatant, rng: RNG): number {
  const ev = spell.effect_value ?? {};
  if (typeof ev.hp_amount === "number") return Math.max(1, ev.hp_amount);
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
  const bonus = casterStatBonus(caster, ev.stat_bonus);
  return Math.max(1, amount + bonus);
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
    sprite: assetUrl("/assets/monsters/skeleton.png"),
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

// ── Combat-usable consumables (Healing Potion, Antidote, Fire Oil…) ──
//
// Mirrors src/states/combat.py::_apply_use_item — same effect tags,
// same dice rolls, same "drink ends the turn" cadence. Pure helper:
// mutates the caster's hp / member's mp / enemy hp in place, returns a
// result the scene logs and animates. Item consumption (splice from
// personal or shared stash) stays in the scene, mirroring how the
// Throw action works — that way the rest of this file stays free of
// inventory bookkeeping.

/** Per-enemy damage outcome for a `combat_only` mass-damage item. */
export interface UseItemEnemyHit {
  id: string;
  damage: number;
  killed: boolean;
}

export interface UseItemOutcome {
  /** `false` when the item is unusable (no effect, not combat-usable),
   *  the relevant resource is already topped up, or the supporting
   *  member data is missing for an MP heal. The scene re-uses the
   *  message either way; on `false` it should NOT consume the item. */
  ok: boolean;
  /** The item's `effect` tag, echoed back so the scene can pick a VFX. */
  effect: string;
  message: string;
  /** HP or MP restored on the caster (`heal_hp` / `heal_mp`). */
  amount?: number;
  /** Per-enemy damage outcomes for `combat_only` (Fire Oil etc.). */
  enemyHits?: UseItemEnemyHit[];
  /** Whether the item use should advance the turn. True for every
   *  successful use; false on refusal so the player can pick something
   *  else without forfeiting their turn. */
  endsTurn: boolean;
}

/**
 * Optional hooks the scene wires up so this pure helper can stage
 * combat buffs without depending on the `Combat` controller. Tests
 * can pass stubs that record the calls; the real call site forwards
 * to `combat.addBuff` / `combat.hasBuffFromSource`.
 *
 * Both are optional: when omitted, the buff branches refuse politely
 * just like they did before the buff system landed (so anyone calling
 * `useCombatItem` from a non-combat path still gets sane behaviour).
 */
export interface UseItemBuffHooks {
  addBuff(combatantId: string, buff: Buff): void;
  /** True when a buff with this `source` (item name) is already active
   *  on the combatant — used to refuse a second Elixir of Strength
   *  rather than letting them stack indefinitely. */
  hasBuffFromSource(combatantId: string, source: string): boolean;
}

/**
 * Apply a usable item's effect during combat. The CombatScene calls
 * this after the player has picked an item from the Use picker.
 *
 *   - `caster`: the active Combatant (mutated for HP heals).
 *   - `member`: the matching PartyMember row (needed for `heal_mp` —
 *     Combatants don't carry an MP pool). Nullable so monster summons
 *     and AI-controlled allies can still call this for HP heals; an
 *     `heal_mp` on a null member refuses politely.
 *   - `enemies`: alive + dead enemy combatants for `combat_only`
 *     throws; dead targets are filtered out before damage rolls.
 *   - `item`: the catalog entry (must satisfy `isCombatUsable`).
 *   - `rng`: injected RNG so tests can pin outcomes.
 *   - `buffs`: optional buff hooks for Elixir-style consumables.
 *     Without them the strength/ac branches still refuse politely.
 */
export function useCombatItem(
  caster: Combatant,
  member: PartyMember | null,
  enemies: Combatant[],
  item: Item,
  rng: RNG,
  buffs?: UseItemBuffHooks,
): UseItemOutcome {
  // Defense in depth: the picker filters by `isCombatUsable` already,
  // but a stale picker entry or a future caller might still pass an
  // item that shouldn't apply. Refuse cleanly instead of trusting the
  // call site.
  if (!isCombatUsable(item)) {
    return {
      ok: false,
      effect: item.effect ?? "",
      message: `${item.name} can't be used in combat.`,
      endsTurn: false,
    };
  }
  const effect = item.effect ?? "";
  const power = item.power ?? 0;

  switch (effect) {
    case "heal_hp": {
      if (caster.hp >= caster.maxHp) {
        return {
          ok: false,
          effect,
          message: `${caster.name} is already at full HP.`,
          endsTurn: false,
        };
      }
      // Mirrors Python: heal = power + 1d6, clamp to maxHp.
      const dice = rollDamage(1, 6, 0, false, rng);
      const heal = Math.max(1, power + dice);
      const before = caster.hp;
      caster.hp = Math.min(caster.maxHp, caster.hp + heal);
      const actual = caster.hp - before;
      return {
        ok: true,
        effect,
        amount: actual,
        message: `${caster.name} uses ${item.name}! (+${actual} HP)`,
        endsTurn: true,
      };
    }
    case "heal_mp": {
      if (!member || member.maxMp == null) {
        return {
          ok: false,
          effect,
          message: `${caster.name} has no magic to restore.`,
          endsTurn: false,
        };
      }
      const cur = member.mp ?? 0;
      if (cur >= member.maxMp) {
        return {
          ok: false,
          effect,
          message: `${caster.name}'s magic reserves are already full.`,
          endsTurn: false,
        };
      }
      // Python: restore = power + 1d4.
      const dice = rollDamage(1, 4, 0, false, rng);
      const restore = Math.max(1, power + dice);
      const next = Math.min(member.maxMp, cur + restore);
      const actual = next - cur;
      member.mp = next;
      return {
        ok: true,
        effect,
        amount: actual,
        message: `${caster.name} uses ${item.name}! (+${actual} MP)`,
        endsTurn: true,
      };
    }
    case "cure_poison": {
      // Poison status isn't modelled on Combatant in the web port yet
      // (mirroring the gap on PartyMember). Refuse without consuming
      // the item so the player isn't billed for a no-op. When the
      // status engine lands this branch can scan + clear flags.
      return {
        ok: false,
        effect,
        message: `${caster.name} isn't poisoned.`,
        endsTurn: false,
      };
    }
    case "buff_strength": {
      // Elixir of Strength: bumps STR for the rest of combat, which
      // in the Python game feeds both attack-bonus and damage. We
      // model that as two parallel buff entries — `attack_bonus` so
      // the d20 hit roll picks it up, and `damage_bonus` so the
      // post-dice total also gets the swing. `power` is the per-
      // potion magnitude from items.json (default 2).
      if (!buffs) {
        return {
          ok: false,
          effect,
          message: `${item.name} can't be applied right now.`,
          endsTurn: false,
        };
      }
      if (buffs.hasBuffFromSource(caster.id, item.name)) {
        return {
          ok: false,
          effect,
          message: `${caster.name} is already feeling the surge from ${item.name}.`,
          endsTurn: false,
        };
      }
      const value = power > 0 ? power : 2;
      // Long turnsLeft so the buff stays for the rest of the
      // encounter — the Python `potion_buffs` dict has no expiry,
      // and we wipe combatant buffs at encounter end anyway.
      const turnsLeft = 99;
      buffs.addBuff(caster.id, {
        kind: "attack_bonus", value, turnsLeft, source: item.name,
      });
      buffs.addBuff(caster.id, {
        kind: "damage_bonus", value, turnsLeft, source: item.name,
      });
      return {
        ok: true,
        effect,
        amount: value,
        message: `${caster.name} drinks ${item.name}! (+${value} STR)`,
        endsTurn: true,
      };
    }
    case "buff_ac": {
      // Elixir of Warding: AC bonus for the rest of the encounter.
      if (!buffs) {
        return {
          ok: false,
          effect,
          message: `${item.name} can't be applied right now.`,
          endsTurn: false,
        };
      }
      if (buffs.hasBuffFromSource(caster.id, item.name)) {
        return {
          ok: false,
          effect,
          message: `${caster.name} is already shielded by ${item.name}.`,
          endsTurn: false,
        };
      }
      const value = power > 0 ? power : 2;
      buffs.addBuff(caster.id, {
        kind: "ac_bonus", value, turnsLeft: 99, source: item.name,
      });
      return {
        ok: true,
        effect,
        amount: value,
        message: `${caster.name} drinks ${item.name}! (+${value} AC)`,
        endsTurn: true,
      };
    }
    case "combat_only": {
      // Throwables like Fire Oil — splash damage to every alive enemy.
      // Mirrors Python: each target takes `power + 1d6`, capped at 0.
      const alive = enemies.filter((e) => e.hp > 0);
      if (alive.length === 0) {
        return {
          ok: false,
          effect,
          message: `No enemies left to target with ${item.name}.`,
          endsTurn: false,
        };
      }
      const hits: UseItemEnemyHit[] = [];
      let total = 0;
      for (const e of alive) {
        const dice = rollDamage(1, 6, 0, false, rng);
        const dmg = Math.max(1, power + dice);
        const before = e.hp;
        e.hp = Math.max(0, e.hp - dmg);
        const dealt = before - e.hp;
        total += dealt;
        hits.push({ id: e.id, damage: dealt, killed: e.hp === 0 });
      }
      return {
        ok: true,
        effect,
        message: `${caster.name} hurls ${item.name}! Splash damage hits everyone! (${total} total)`,
        enemyHits: hits,
        endsTurn: true,
      };
    }
    default: {
      // Unknown effect tag — consume the item but log generically so a
      // future items.json entry doesn't crash combat.
      return {
        ok: true,
        effect,
        message: `${caster.name} uses ${item.name}.`,
        endsTurn: true,
      };
    }
  }
}
