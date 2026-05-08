/**
 * Bridge from `PartyMember` (the data model used by the Party screen
 * + save/load) to `Combatant` (the data model the combat engine
 * runs on). The combat layer was originally fed a hand-built sample
 * party; this lets it instead read the real roster from
 * `data/party.json` so encounters use whoever the player actually
 * has — with their actual level, equipped weapon, HP/MP, sprite.
 *
 * Stat derivation is deliberately simple — it covers what combat
 * needs today (hit / damage / AC / initiative) without trying to
 * replicate every tweak the Python game's class tables apply. Once
 * we port the class JSON files we can layer richer maths on top.
 */

import type { Combatant, DamageRoll } from "../types";
import type { PartyMember, Party, EquipmentSlots } from "../world/Party";
import type { Item } from "../world/Items";
import type { ClassTemplate } from "../world/Classes";
import { activeMembers } from "../world/Party";

/** Fall-back tile movement budget when no class template is available
 *  (tests that don't pass a classes map, or a class file failed to
 *  load). Picked to match the prior hardcoded value so callers that
 *  don't opt in see no behaviour change. */
const DEFAULT_MOVE_RANGE = 4;

/** D&D-style modifier (10 = 0, 18 = +4, 8 = -1, …). */
export function abilityMod(stat: number): number {
  return Math.floor((stat - 10) / 2);
}

/** Internal alias kept short for the bridge's existing callers. */
function mod(stat: number): number { return abilityMod(stat); }

/**
 * Sum the `acBonus` field across every equipped item the member is
 * currently wearing. Mundane gear has no `acBonus`, so this is a
 * no-op for the starter party — the field is honoured for magic
 * gear (Mystic Sword, Sun Sword, Bracers of Defence, etc.) the way
 * the Python game's `Member.get_total_ac_bonus()` does.
 */
function totalAcBonus(equipped: EquipmentSlots, items: Map<string, Item>): number {
  let total = 0;
  const slots: Array<keyof EquipmentSlots> = ["rightHand", "leftHand", "body", "head"];
  for (const slot of slots) {
    const name = equipped[slot];
    if (!name) continue;
    const it = items.get(name);
    if (it?.acBonus) total += it.acBonus;
  }
  return total;
}

/**
 * Power-tier damage dice — direct port of `Member.get_damage_dice()`
 * in `src/party.py:956`. Power tier sets the die size; the wielder's
 * STR mod (or DEX mod for ranged weapons) is added as a bonus, and
 * power-1 weapons get an extra `-1` to round to roughly d3.
 */
function damageForWeapon(member: PartyMember, weapon: Item | null): DamageRoll {
  if (!weapon || typeof weapon.power !== "number") {
    // Bare fists / no weapon — flat 1 damage, matches Python's `power 0` path.
    return { dice: 0, sides: 0, bonus: 1 };
  }
  // Python keys off only `ranged` (a bow / sling / crossbow) — a
  // throwable melee weapon (Dagger) defaults to STR until the player
  // explicitly throws it. Matches `Member.get_damage_dice` at
  // `src/party.py:973`.
  const isRanged = !!weapon.ranged;
  const statMod = isRanged ? mod(member.dexterity) : mod(member.strength);
  const wp = weapon.power;
  if (wp <= 0) return { dice: 0, sides: 0, bonus: 1 };
  if (wp === 1) return { dice: 1, sides: 4, bonus: statMod - 1 };
  if (wp <= 3)  return { dice: 1, sides: 4, bonus: statMod };
  if (wp <= 5)  return { dice: 1, sides: 6, bonus: statMod };
  if (wp <= 8)  return { dice: 1, sides: 8, bonus: statMod };
  return         { dice: 1, sides: 10, bonus: statMod };
}

/**
 * Derive combat stats from a PartyMember + the catalog of items.
 * Mirrors `Member.get_ac()`, `Member.get_attack_bonus()`, and
 * `Member.get_damage_dice()` from `src/party.py`:
 *
 *   AC          = 10 + DEX_mod + (armor_evasion - 50)/5 + Σ acBonus
 *   atk bonus   = STR_mod (melee) or DEX_mod (ranged/thrown)
 *   damage      = power-tier dice + STR_mod (or DEX_mod for ranged)
 *
 * The full ability block also rides along on the Combatant so spell
 * damage helpers can read INT (Magic Arrow) and WIS (Heal) without
 * having to re-look-up the underlying PartyMember.
 *
 * - HP / maxHP: from the member directly so HP carries between
 *   encounters when combat finishes.
 * - move range: from the member's class template (Wizards 2,
 *   Fighters 4, Thieves 6 in the shipped data). Falls back to 4 when
 *   `classes` isn't supplied or the class file failed to load.
 */
export function combatantFromMember(
  member: PartyMember,
  items: Map<string, Item>,
  classes?: Map<string, ClassTemplate>,
): Combatant {
  const weapon = member.equipped.rightHand
    ? items.get(member.equipped.rightHand) ?? null
    : null;
  const armor = member.equipped.body
    ? items.get(member.equipped.body) ?? null
    : null;
  const dexMod = mod(member.dexterity);
  const evasion = armor && typeof armor.evasion === "number" ? armor.evasion : 50;
  const armorBonus = Math.floor((evasion - 50) / 5);
  const ac = 10 + dexMod + armorBonus + totalAcBonus(member.equipped, items);
  const isRanged = !!(weapon && weapon.ranged);
  const attackBonus = isRanged ? dexMod : mod(member.strength);
  const damage = damageForWeapon(member, weapon);
  const tpl = classes?.get(member.class.toLowerCase());
  const baseMoveRange = tpl ? tpl.range : DEFAULT_MOVE_RANGE;
  return {
    id: `pm:${member.name}`,
    name: member.name,
    side: "party",
    maxHp: member.maxHp,
    hp: member.hp,
    ac,
    attackBonus,
    damage,
    dexMod,
    strength: member.strength,
    dexterity: member.dexterity,
    constitution: member.constitution,
    intelligence: member.intelligence,
    wisdom: member.wisdom,
    color: [200, 200, 200],
    sprite: member.sprite,
    baseMoveRange,
    position: { col: 0, row: 0 },
  };
}

/** Convert the active four PartyMembers into Combatants for the
 *  combat engine. Pass `classes` (lowercased class name → template)
 *  to honour per-class movement ranges; without it everyone defaults
 *  to the legacy 4-tile budget. */
export function combatantsFromParty(
  party: Party,
  items: Map<string, Item>,
  classes?: Map<string, ClassTemplate>,
): Combatant[] {
  return activeMembers(party).map((m) => combatantFromMember(m, items, classes));
}

/**
 * Write combat HP back into the party data after the encounter
 * resolves. The combat layer mutates Combatant.hp during the fight;
 * this propagates the result so HP carries across the overworld.
 */
export function syncCombatHpBack(
  party: Party,
  combatants: Combatant[],
): void {
  const byName = new Map(combatants.filter((c) => c.side === "party")
                                   .map((c) => [c.name, c]));
  for (const m of party.roster) {
    const c = byName.get(m.name);
    if (c) m.hp = c.hp;
  }
}
