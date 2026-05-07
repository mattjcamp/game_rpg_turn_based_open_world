/**
 * Party state — roster, active members, gold, shared inventory.
 *
 * Mirrors the Python project's `data/party.json` format directly so a
 * round-trip through the module editor stays loss-less. Loaded via
 * `loadParty()` once on first access and then held in `gameState`
 * (state.ts) so HP/gold/inventory edits survive scene transitions.
 */

import { dataPath } from "./Module";
import { normalizeSpritePath } from "./Towns";

export interface EquipmentSlots {
  rightHand: string | null;
  leftHand: string | null;
  body: string | null;
  head: string | null;
}

export interface InventoryItem {
  item: string;
  /** Charges remaining for stacked / consumable items. Absent for gear. */
  charges?: number;
  /**
   * Current remaining durability for worn gear. Absent means the item
   * has never been used (start at the catalog max when equipped) or is
   * indestructible. The field travels with the entry so two copies of
   * the same item in the stash can wear independently — exactly like
   * the Python game's per-entry durability dict.
   */
  durability?: number;
}

export interface PartyMember {
  name: string;
  /** Class name, capitalised as the source data writes it (Fighter, Wizard…). */
  class: string;
  race: string;
  gender: string;
  hp: number;
  /** Starting/maximum HP — derived from `hp` at load time. */
  maxHp: number;
  /** Mana points (casters only). */
  mp?: number;
  maxMp?: number;
  strength: number;
  dexterity: number;
  intelligence: number;
  wisdom: number;
  level: number;
  equipped: EquipmentSlots;
  /**
   * Per-slot remaining durability for the items currently equipped.
   * `null` means the slot's item is indestructible (or there's nothing
   * equipped). When an item is unequipped, its current value moves
   * onto the receiving InventoryItem.durability so wear isn't lost.
   */
  equippedDurability: {
    right_hand: number | null;
    left_hand: number | null;
    body: number | null;
    head: number | null;
  };
  inventory: InventoryItem[];
  /** Resolved /assets/... path. Source path is normalised on load. */
  sprite: string;
}

export interface Party {
  startPosition: { col: number; row: number };
  gold: number;
  /** Full roster — characters available to swap in/out of the active party. */
  roster: PartyMember[];
  /** Indices into `roster` of the four members currently adventuring. */
  activeParty: number[];
  /** Up to 4 named effects active on the party (Detect Traps, Infravision…). */
  partyEffects: Record<string, string | null>;
  /** Stash — items shared across the party. */
  inventory: InventoryItem[];
}

interface RawEquipped {
  right_hand?: string | null;
  left_hand?: string | null;
  body?: string | null;
  head?: string | null;
}

interface RawMember {
  name?: string;
  class?: string;
  race?: string;
  gender?: string;
  hp?: number;
  mp?: number;
  strength?: number;
  dexterity?: number;
  intelligence?: number;
  wisdom?: number;
  level?: number;
  equipped?: RawEquipped;
  inventory?: InventoryItem[];
  sprite?: string;
}

interface RawParty {
  start_position?: { col?: number; row?: number };
  gold?: number;
  roster?: RawMember[];
  active_party?: number[];
  party_effects?: Record<string, string | null>;
  inventory?: InventoryItem[];
}

/**
 * If the source sprite path doesn't resolve to one of the character
 * PNGs we ship, fall back to a class-based default. e.g. a Fighter
 * with sprite `src/assets/game/npcs/shopkeep.png` (placeholder data
 * in the source) lands on `/assets/characters/fighter.png` instead.
 */
const SHIPPED_CHARACTER_SPRITES = new Set([
  "alchemist", "barbarian", "cleric", "fighter",
  "illusionist", "paladin", "ranger", "thief", "wizard",
]);

export function spriteForMember(rawSprite: string | undefined, klass: string): string {
  const norm = normalizeSpritePath(rawSprite ?? "");
  // If the normalised path points at a /assets/characters/<known>.png
  // we have shipped, accept it as-is.
  const m = /\/assets\/characters\/([^/]+)\.png$/.exec(norm);
  if (m && SHIPPED_CHARACTER_SPRITES.has(m[1])) return norm;
  // Otherwise fall back to /assets/characters/<class>.png.
  const fallback = `/assets/characters/${klass.toLowerCase()}.png`;
  return fallback;
}

export function memberFromRaw(raw: RawMember): PartyMember {
  const klass = raw.class ?? "Fighter";
  const hp = raw.hp ?? 0;
  return {
    name: raw.name ?? "?",
    class: klass,
    race: raw.race ?? "?",
    gender: raw.gender ?? "?",
    hp,
    maxHp: hp,
    mp: raw.mp,
    maxMp: raw.mp,
    strength: raw.strength ?? 10,
    dexterity: raw.dexterity ?? 10,
    intelligence: raw.intelligence ?? 10,
    wisdom: raw.wisdom ?? 10,
    level: raw.level ?? 1,
    equipped: {
      rightHand: raw.equipped?.right_hand ?? null,
      leftHand: raw.equipped?.left_hand ?? null,
      body: raw.equipped?.body ?? null,
      head: raw.equipped?.head ?? null,
    },
    // Durability trackers default to "uninitialised" — the first time
    // an item is equipped (or use_durability runs against it) the
    // helper seeds it from the catalog max. Mirrors the Python game's
    // lazy initialisation in equipped_durability.
    equippedDurability: {
      right_hand: null,
      left_hand: null,
      body: null,
      head: null,
    },
    inventory: raw.inventory ?? [],
    sprite: spriteForMember(raw.sprite, klass),
  };
}

export function partyFromRaw(raw: RawParty): Party {
  return {
    startPosition: {
      col: raw.start_position?.col ?? 0,
      row: raw.start_position?.row ?? 0,
    },
    gold: raw.gold ?? 0,
    roster: (raw.roster ?? []).map(memberFromRaw),
    activeParty: raw.active_party ?? [0, 1, 2, 3],
    partyEffects: raw.party_effects ?? {
      effect_1: null, effect_2: null, effect_3: null, effect_4: null,
    },
    inventory: raw.inventory ?? [],
  };
}

let _partyCache: Party | null = null;

/** Fetch and parse /data/party.json. Result is cached. */
export async function loadParty(url = dataPath("party.json")): Promise<Party> {
  if (_partyCache) return _partyCache;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as RawParty;
  _partyCache = partyFromRaw(raw);
  return _partyCache;
}

/** Return the four active PartyMember objects (in active_party order). */
export function activeMembers(p: Party): PartyMember[] {
  return p.activeParty
    .map((i) => p.roster[i])
    .filter((m): m is PartyMember => Boolean(m));
}

/** Test-only cache reset. */
export function _clearPartyCache(): void {
  _partyCache = null;
}
