/**
 * Pick-lock + Knock-spell logic.
 *
 * Mirrors `src/states/lock_mixin.py` from the Python game. When the
 * party bumps a tile that's flagged `locked` (either tile_id 29 or a
 * `tile_properties[col,row].locked === true` flag), the host scene
 * opens a small dialog with three rows:
 *
 *   - Pick Lock — alive Thief or L3+ Ranger, requires a Lockpick charge.
 *     Roll d20 + DEX mod vs DC 12. Consumes one charge regardless of
 *     outcome.
 *   - Cast Knock — alive caster from the spell's allowable_classes
 *     list at or above its min_level, with enough MP. Roll d20 + INT
 *     mod (or whatever `effect_value.save_stat` says) vs the spell's
 *     `effect_value.save_dc_base` (default 12). MP is deducted on
 *     attempt regardless of outcome.
 *   - Leave — close the dialog with no effect.
 *
 * Pure functions — the host scene owns the UI and the timing of the
 * unlock animation.
 */

import type { Party, PartyMember } from "./Party";
import type { Spell } from "./Spells";
import type { TileMap } from "./TileMap";
import { TILE_LOCKED_DOOR, TILE_DDOOR } from "./Tiles";
import { statMod } from "./PartyActions";

export const PICK_LOCK_DC = 12;
export const KNOCK_DEFAULT_DC = 12;

/**
 * True when the tile at (col, row) is flagged "locked" — either via
 * the legacy TILE_LOCKED_DOOR id or the editor-painted
 * `tile_properties[col,row].locked` flag.
 */
export function isLockedAt(
  tileMap: TileMap, col: number, row: number,
): boolean {
  if (!tileMap.inBounds(col, row)) return false;
  if (tileMap.getTile(col, row) === TILE_LOCKED_DOOR) return true;
  const entry = tileMap.tileProperties[`${col},${row}`];
  if (!entry || typeof entry !== "object") return false;
  return !!(entry as { locked?: unknown }).locked;
}

/**
 * Apply the unlock — convert TILE_LOCKED_DOOR → TILE_DDOOR (open
 * dungeon door) and clear the `locked` tile_property if present.
 *
 * Returns the new tile id when the visual sprite needs to be
 * swapped (the locked → open transition), or null when only a
 * property was removed and the underlying sprite is unchanged.
 */
export function unlockAt(
  tileMap: TileMap, col: number, row: number,
): number | null {
  let newId: number | null = null;
  if (tileMap.getTile(col, row) === TILE_LOCKED_DOOR) {
    tileMap.setTile(col, row, TILE_DDOOR);
    newId = TILE_DDOOR;
  }
  const key = `${col},${row}`;
  const props = tileMap.tileProperties as Record<string, Record<string, unknown> | undefined>;
  const entry = props[key];
  if (entry && "locked" in entry) {
    delete entry.locked;
    // If `locked` was the only field, drop the property entry too —
    // matches the Python cleanup so a future query (e.g. for
    // light_source) doesn't surface an empty dict.
    if (Object.keys(entry).length === 0) {
      delete props[key];
    }
  }
  return newId;
}

/**
 * Pick the party member who'll attempt to pick the lock. A Thief is
 * always preferred (specialist class); otherwise a Ranger of level 3
 * or higher qualifies. Returns null if neither exists.
 */
export function findLockpicker(members: PartyMember[]): PartyMember | null {
  let ranger: PartyMember | null = null;
  for (const m of members) {
    if (m.hp <= 0) continue;
    if (m.class === "Thief") return m;
    if (m.class === "Ranger" && m.level >= 3 && !ranger) ranger = m;
  }
  return ranger;
}

/**
 * Pick the party member who'll cast Knock. Must be alive, in the
 * spell's allowable_classes list, at or above its min_level. MP
 * sufficiency is checked separately so the dialog can show a
 * "no MP" message instead of hiding the option entirely.
 */
export function findKnockCaster(
  members: PartyMember[], spell: Spell,
): PartyMember | null {
  const allowed = new Set(
    (spell.allowable_classes ?? []).map((c) => c.toLowerCase()),
  );
  const minLevel = spell.min_level ?? 1;
  for (const m of members) {
    if (m.hp <= 0) continue;
    if (!allowed.has(m.class.toLowerCase())) continue;
    if (m.level < minLevel) continue;
    return m;
  }
  return null;
}

/** Sum of all charges across every Lockpick stash entry. */
export function getLockpickCharges(party: Party): number {
  let total = 0;
  for (const it of party.inventory) {
    if (it.item === "Lockpick") total += it.charges ?? 1;
  }
  return total;
}

/**
 * Consume one Lockpick charge. Decrements the first Lockpick entry
 * with charges available; removes the entry when its charges hit
 * zero. Returns true on success, false if the stash had no
 * Lockpicks.
 */
export function consumeLockpick(party: Party): boolean {
  for (let i = 0; i < party.inventory.length; i++) {
    const it = party.inventory[i];
    if (it.item !== "Lockpick") continue;
    const charges = (it.charges ?? 1) - 1;
    if (charges <= 0) {
      party.inventory.splice(i, 1);
    } else {
      party.inventory[i] = { ...it, charges };
    }
    return true;
  }
  return false;
}

export interface LockpickResult {
  success: boolean;
  roll: number;
  mod: number;
  total: number;
  dc: number;
}

export function attemptLockpick(
  thief: PartyMember,
  rng: () => number = Math.random,
): LockpickResult {
  const roll = 1 + Math.floor(rng() * 20);
  const mod = statMod(thief.dexterity);
  const total = roll + mod;
  return { success: total >= PICK_LOCK_DC, roll, mod, total, dc: PICK_LOCK_DC };
}

export interface KnockResult {
  success: boolean;
  roll: number;
  mod: number;
  total: number;
  dc: number;
  mpCost: number;
}

function readStat(member: PartyMember, name: string): number {
  switch (name) {
    case "intelligence": return member.intelligence;
    case "wisdom":       return member.wisdom;
    case "dexterity":    return member.dexterity;
    case "strength":     return member.strength;
    default:             return 10;
  }
}

export function attemptKnock(
  caster: PartyMember,
  spell: Spell,
  rng: () => number = Math.random,
): KnockResult {
  const ev = spell.effect_value ?? {};
  const dc = (typeof ev.save_dc_base === "number" ? ev.save_dc_base : KNOCK_DEFAULT_DC);
  const stat = (typeof ev.save_stat === "string" ? ev.save_stat : "intelligence");
  const roll = 1 + Math.floor(rng() * 20);
  const mod = statMod(readStat(caster, stat));
  const total = roll + mod;
  const mpCost = spell.mp_cost ?? 0;
  return { success: total >= dc, roll, mod, total, dc, mpCost };
}

// ── Dialog option assembly ────────────────────────────────────────

export type LockOptionId =
  | "pick"
  | "knock"
  | "leave"
  | "no_thief"
  | "no_picks"
  | "no_knock_mp";

export interface LockOption {
  id: LockOptionId;
  label: string;
}

/**
 * Build the option list the dialog renders. Mirrors the branching in
 * Python's `_show_lock_interact`: every state of the party + spell
 * book maps to one row apiece, plus a final Leave row.
 */
export function buildLockOptions(args: {
  party: Party;
  members: PartyMember[];
  knockSpell: Spell | null;
}): LockOption[] {
  const out: LockOption[] = [];
  const thief = findLockpicker(args.members);
  const picks = getLockpickCharges(args.party);
  if (thief && picks > 0) {
    out.push({ id: "pick", label: `Pick Lock (${thief.name}, ${picks} picks)` });
  } else if (thief) {
    out.push({ id: "no_picks", label: "Pick Lock (no lockpicks!)" });
  } else {
    out.push({ id: "no_thief", label: "Pick Lock (need a Thief or L3+ Ranger!)" });
  }
  if (args.knockSpell) {
    const caster = findKnockCaster(args.members, args.knockSpell);
    if (caster) {
      const cost = args.knockSpell.mp_cost ?? 0;
      if ((caster.mp ?? 0) >= cost) {
        out.push({ id: "knock", label: `Cast Knock (${caster.name}, ${cost} MP)` });
      } else {
        out.push({ id: "no_knock_mp", label: "Cast Knock (insufficient MP)" });
      }
    }
  }
  out.push({ id: "leave", label: "Leave" });
  return out;
}
