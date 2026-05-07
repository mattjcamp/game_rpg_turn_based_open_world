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
  /** Shop price the player pays. 0 / undefined = unique / not for sale. */
  buy?: number;
  /** Shop price the player receives when selling. */
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
    buy: typeof r.buy === "number" ? r.buy : undefined,
    sell: typeof r.sell === "number" ? r.sell : undefined,
  };
}

/**
 * Shop price the party pays at a counter, or `null` for items the
 * counter can't actually sell (no `buy` price in items.json).
 *
 * Mirrors `_derive_buy_price` in the Python game: weapons & armor that
 * lack an explicit price get one derived from their stats so a counter
 * always has a price to display, while general items with no price
 * (quest items, unique drops) stay `null` so the counter can hide them.
 */
export function getBuyPrice(item: Item | null | undefined): number | null {
  if (!item) return null;
  if (typeof item.buy === "number" && item.buy > 0) return item.buy;
  if (item.category === "armors" && typeof item.evasion === "number") {
    return Math.max(10, item.evasion * 15);
  }
  if (item.category === "weapons" && typeof item.power === "number") {
    return Math.max(10, item.power * 8);
  }
  return null;
}

/**
 * Sell-back price. Falls back to half the buy price (rounded down) when
 * items.json doesn't carry an explicit `sell` value, matching the
 * Python game's `get_sell_price`.
 */
export function getSellPrice(item: Item | null | undefined): number {
  if (!item) return 0;
  if (typeof item.sell === "number" && item.sell > 0) return item.sell;
  const buy = getBuyPrice(item);
  return buy != null ? Math.floor(buy / 2) : 0;
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
