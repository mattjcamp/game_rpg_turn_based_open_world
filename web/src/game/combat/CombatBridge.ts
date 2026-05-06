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

import type { Combatant } from "../types";
import type { PartyMember, Party } from "../world/Party";
import type { Item } from "../world/Items";
import { activeMembers } from "../world/Party";

const DEFAULT_DAMAGE = { dice: 1, sides: 6, bonus: 0 } as const;

/** D&D-style modifier (10 = 0, 18 = +4, 8 = -1, …). */
function mod(stat: number): number {
  return Math.floor((stat - 10) / 2);
}

/** Pick the best ability modifier for hit rolls — STR for melee
 *  and unarmed, DEX for ranged / thrown. */
function bestAttackMod(member: PartyMember, weapon: Item | null): number {
  if (weapon && (weapon.ranged || weapon.throwable)) return mod(member.dexterity);
  return mod(member.strength);
}

/**
 * Derive combat stats from a PartyMember + the catalog of items.
 *
 * - HP / maxHP: from the member directly so HP carries between
 *   encounters when combat finishes.
 * - AC: 10 + DEX modifier + a small armour bonus from the equipped
 *   body slot (`evasion / 25`, capped at +4 — keeps Plate worth
 *   wearing without trivialising fights).
 * - attack bonus: floor(level/2) + best-stat mod + 1 proficiency.
 * - damage: 1d6 + weapon.power. Unarmed → bare 1d6.
 */
export function combatantFromMember(
  member: PartyMember,
  items: Map<string, Item>,
): Combatant {
  const weapon = member.equipped.rightHand
    ? items.get(member.equipped.rightHand) ?? null
    : null;
  const armor = member.equipped.body
    ? items.get(member.equipped.body) ?? null
    : null;
  const dexMod = mod(member.dexterity);
  const armorBonus = armor && typeof armor.evasion === "number"
    ? Math.min(4, Math.floor(armor.evasion / 25))
    : 0;
  const ac = 10 + dexMod + armorBonus;
  const attackBonus =
    Math.floor(member.level / 2) + bestAttackMod(member, weapon) + 1;
  const damage = weapon && typeof weapon.power === "number"
    ? { dice: 1, sides: 6, bonus: weapon.power }
    : { ...DEFAULT_DAMAGE };
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
    color: [200, 200, 200],
    sprite: member.sprite,
    baseMoveRange: 4,
    position: { col: 0, row: 0 },
  };
}

/** Convert the active four PartyMembers into Combatants for the
 *  combat engine. */
export function combatantsFromParty(
  party: Party,
  items: Map<string, Item>,
): Combatant[] {
  return activeMembers(party).map((m) => combatantFromMember(m, items));
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
