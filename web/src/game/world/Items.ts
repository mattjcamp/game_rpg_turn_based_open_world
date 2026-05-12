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
  /**
   * Whether a `usable` item can be drunk / applied during a combat
   * encounter (Healing Potion = unset → defaults true; Camping
   * Supplies = explicit `false`). Mirrors items.json `combat_usable`.
   * Left optional in the model so authors don't have to mark every
   * potion or herb; consumers should call `isCombatUsable(item)`
   * which encodes the "default true for usable items" rule.
   */
  combatUsable?: boolean;
  /** Free-form effect tag for usable items (e.g. "heal_hp"). */
  effect: string | null;
  // Combat / display stats — present where relevant.
  power?: number;
  ranged?: boolean;
  melee?: boolean;
  throwable?: boolean;
  evasion?: number;
  /** Magic AC bonus that stacks with armor evasion when this item is
   *  equipped. Mirrors the Python `ac_bonus` field; weapons can carry
   *  it too (e.g. a parrying dagger). */
  acBonus?: number;
  durability?: number;
  itemType?: string;
  /**
   * Render-glyph hint from items.json (e.g. "torch", "potion",
   * "sword", "key", "scroll"). Drives how the item is drawn when
   * dropped on a tile (Decorations.ts) and matches the Python
   * game's `_draw_item_icon` switch. Distinct from `itemType`,
   * which is the gameplay category — e.g. Antidote has
   * `itemType: "antidote"` but `icon: "potion"`.
   */
  icon?: string;
  /** Buy price at shops (gold). 0 / missing = not for sale. */
  buy?: number;
  /** Sell price (gold) at shops. 0 / missing = nobody will buy it. */
  sell?: number;
  /**
   * Whether multiple copies of this item collapse into a single
   * inventory entry whose `charges` count sums across copies. Mirrors
   * the items.json `stackable` flag — true for ammo, herbs, potions,
   * lockpicks, torches, camping supplies, reagents.
   */
  stackable?: boolean;
  /**
   * Per-purchase / per-drop "stack size". Adding one copy of this
   * item to the stash bumps the inventory entry's `charges` by this
   * amount. e.g. arrows are sold in stacks of 20 (charges: 20), each
   * lockpick set has 5 attempts (charges: 5), most potions are 1.
   * Undefined falls back to 1 in code.
   */
  charges?: number;
  /**
   * Name of the matching ammo item this weapon consumes per shot.
   * Bows reference "Arrows", crossbows "Bolts", slings "Stones".
   * Missing for melee weapons and for ranged weapons with built-in
   * ammo (e.g. Rock — the weapon IS the projectile).
   */
  ammo?: string;
  /**
   * Extra damage dice rolled on top of the base weapon roll for magic
   * weapons (e.g. Sun Sword's `1d6` fire damage). Accepts either a
   * flat number (`3`) or a dice string (`"1d6"`, `"2d4"`). Crits
   * double the dice count the same way base damage does. Mirrors the
   * Python game's `bonus_damage` weapon field.
   */
  bonusDamage?: string | number;
  /**
   * Damage school for the weapon — `"fire"`, `"cold"`, `"lightning"`,
   * etc. Used for log flavor today (e.g. "12 dmg (fire)") and for
   * future resist/vulnerable scaling against monsters. Missing /
   * `"physical"` is the default and is never scaled. Mirrors the
   * Python game's `damage_type` field.
   */
  damageType?: string;
  /**
   * Effect id this item confers on the party while equipped — Sun
   * Sword grants `"sun_sword_aura"`, etc. The granted effect is
   * looked up against effects.json and surfaces in the HUD's active-
   * effects readout (and any lighting/buff helpers that read effect
   * ids) for as long as the item stays in a slot. Mirrors the Python
   * game's `grants_effect` field.
   */
  grantsEffect?: string;
}

interface RawItem {
  description?: string;
  slots?: string[];
  party_can_equip?: boolean;
  character_can_equip?: boolean;
  usable?: boolean;
  combat_usable?: boolean;
  effect?: string | null;
  power?: number;
  ranged?: boolean;
  melee?: boolean;
  throwable?: boolean;
  evasion?: number;
  ac_bonus?: number;
  durability?: number;
  item_type?: string;
  buy?: number;
  sell?: number;
  stackable?: boolean;
  charges?: number;
  ammo?: string;
  icon?: string;
  bonus_damage?: string | number;
  damage_type?: string;
  grants_effect?: string;
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
    // Pass the raw flag through unchanged so the default-true rule
    // lives in `isCombatUsable` (one place, easier to reason about).
    combatUsable: r.combat_usable,
    effect: r.effect ?? null,
    power: r.power,
    ranged: r.ranged,
    melee: r.melee,
    throwable: r.throwable,
    evasion: r.evasion,
    acBonus: r.ac_bonus,
    durability: r.durability,
    itemType: r.item_type,
    buy: r.buy,
    sell: r.sell,
    stackable: r.stackable,
    charges: r.charges,
    ammo: r.ammo,
    icon: r.icon,
    bonusDamage: r.bonus_damage,
    damageType: r.damage_type,
    grantsEffect: r.grants_effect,
  };
}

/**
 * "Stack size" for a stackable item — how many uses one purchase /
 * drop / loot pickup adds to the inventory entry's `charges` count.
 * Defaults to 1 so non-ammo consumables (potions, herbs, scrolls)
 * stack one-per-copy without each needing an explicit value.
 *
 * For non-stackable items returns 1 too — callers that care about
 * the distinction should check `item.stackable` directly.
 */
export function stackSizeOf(item: Item): number {
  if (typeof item.charges === "number" && item.charges > 0) return item.charges;
  return 1;
}

/**
 * True for items the inventory should consolidate. Defers to the
 * `stackable` flag in items.json so authors stay in control; nothing
 * stacks implicitly. Non-equippable items that lack the flag remain
 * one-entry-per-copy.
 */
export function isStackable(item: Item): boolean {
  return !!item.stackable;
}

/**
 * Whether a usable item can be drunk / applied during a combat round.
 * Mirrors the Python game's `info.get("combat_usable", True)` rule:
 *   - non-usable items always return false (nothing to apply)
 *   - usable items default to combat-usable unless `combat_usable` is
 *     explicitly false in items.json (Camping Supplies is the only
 *     ship-time entry that opts out — its "rest" effect needs the
 *     party to be safely outside an encounter).
 *
 * Used by the CombatScene Use-item picker to filter the inventory
 * down to potions / herbs / antidotes / throwables-with-effects, and
 * to skip torches and camping supplies.
 */
export function isCombatUsable(item: Item): boolean {
  if (!item.usable) return false;
  return item.combatUsable !== false;
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
