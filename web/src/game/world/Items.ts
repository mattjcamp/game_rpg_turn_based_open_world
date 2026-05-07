/**
 * Items loader.
 *
 * Mirrors `data/items.json` from the Python project. The source has
 * three sections — weapons, armors, general — and the engine cares
 * about a few fields per entry: which slot(s) accept it, whether a
 * character can wear it, plus power / evasion / durability for stat
 * display.
 *
 * `slotsForItem(name)` is the central helper the equip flow asks
 * about. Returns an empty array for items that aren't equippable
 * (consumables, tools, keys).
 */

import { dataPath } from "./Module";

export type EquipSlot = "right_hand" | "left_hand" | "body" | "head";

export interface Item {
  name: string;
  /** Which catalog the item came from. Useful for shop screens. */
  category: "weapons" | "armors" | "general";
  description: string;
  /** Equipment slot(s) that accept this item, in priority order. */
  slots: EquipSlot[];
  /** Whether a single character can equip / hold it. */
  characterCanEquip: boolean;
  /** Whether the whole party can equip it (banners, etc.). */
  partyCanEquip: boolean;
  /** Whether using consumes a charge / acts at runtime. */
  usable: boolean;
  /** Free-form effect tag for usable items (e.g. "heal_hp"). */
  effect: string | null;
  // Combat / display stats — present where relevant.
  power?: number;
  ranged?: boolean;
  melee?: boolean;
  throwable?: boolean;
  evasion?: number;
  durability?: number;
  itemType?: string;
  /** Buy price at shops (gold). 0 / missing = not for sale. */
  buy?: number;
  /** Sell price (gold) at shops. 0 / missing = nobody will buy it. */
  sell?: number;
}

interface RawItem {
  description?: string;
  slots?: string[];
  party_can_equip?: boolean;
  character_can_equip?: boolean;
  usable?: boolean;
  effect?: string | null;
  power?: number;
  ranged?: boolean;
  melee?: boolean;
  throwable?: boolean;
  evasion?: number;
  durability?: number;
  item_type?: string;
  buy?: number;
  sell?: number;
}

interface RawItems {
  weapons?: Record<string, RawItem>;
  armors?:  Record<string, RawItem>;
  general?: Record<string, RawItem>;
}

let _cache: Map<string, Item> | null = null;

function isEquipSlot(s: string): s is EquipSlot {
  return s === "right_hand" || s === "left_hand" || s === "body" || s === "head";
}

function itemFromRaw(name: string, category: Item["category"], r: RawItem): Item {
  const slots = (r.slots ?? []).filter(isEquipSlot);
  return {
    name,
    category,
    description: r.description ?? "",
    slots,
    characterCanEquip: !!r.character_can_equip,
    partyCanEquip: !!r.party_can_equip,
    usable: !!r.usable,
    effect: r.effect ?? null,
    power: r.power,
    ranged: r.ranged,
    melee: r.melee,
    throwable: r.throwable,
    evasion: r.evasion,
    durability: r.durability,
    itemType: r.item_type,
    buy: r.buy,
    sell: r.sell,
  };
}

export async function loadItems(url = dataPath("items.json")): Promise<Map<string, Item>> {
  if (_cache) return _cache;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as RawItems;
  _cache = new Map();
  for (const [name, r] of Object.entries(raw.weapons ?? {})) {
    _cache.set(name, itemFromRaw(name, "weapons", r));
  }
  for (const [name, r] of Object.entries(raw.armors ?? {})) {
    _cache.set(name, itemFromRaw(name, "armors", r));
  }
  for (const [name, r] of Object.entries(raw.general ?? {})) {
    _cache.set(name, itemFromRaw(name, "general", r));
  }
  return _cache;
}

export function getItem(items: Map<string, Item>, name: string): Item | null {
  return items.get(name) ?? null;
}

/**
 * Slot list for an item, in the priority order the editor stores.
 * Empty for non-equippable items so callers can refuse cleanly.
 */
export function slotsForItem(items: Map<string, Item>, name: string): EquipSlot[] {
  const it = items.get(name);
  if (!it) return [];
  if (!it.characterCanEquip) return [];
  return it.slots;
}

/** Test-only cache reset. */
export function _clearItemsCache(): void {
  _cache = null;
}
