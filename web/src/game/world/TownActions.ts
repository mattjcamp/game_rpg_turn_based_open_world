/**
 * Pure logic for town counter interactions — buy, sell, and temple
 * services. Mirrors the Python game's `_handle_shop_input` and
 * `_process_healing_counter_service` paths but split out from the
 * scene class so the same helpers can be unit-tested without Phaser.
 *
 * Each helper mutates the live `Party` in place and returns
 * `{ ok, message }` so the caller can show a feedback line.
 */

import type { Party } from "./Party";
import { activeMembers } from "./Party";
import type { CounterService } from "./Counters";
import type { Item } from "./Items";
import { isStackable, stackSizeOf } from "./Items";

export interface ActionResult {
  ok: boolean;
  message: string;
}

/**
 * Shop price the party pays at a counter. Returns 0 when items.json
 * has no buyable price for this item — the caller treats that as
 * "shop won't sell it" and shows a "—" label instead of a row the
 * player can never act on.
 *
 * Mirrors the Python game's `_derive_buy_price`: weapons & armor
 * with no explicit `buy` field get a stat-derived fallback so a
 * counter always has a price to display.
 */
export function buyPriceOf(
  itemName: string,
  items: Map<string, Item>,
): number {
  const item = items.get(itemName);
  if (!item) return 0;
  if (typeof item.buy === "number" && item.buy > 0) return item.buy;
  if (item.category === "armors" && typeof item.evasion === "number") {
    return Math.max(10, item.evasion * 15);
  }
  if (item.category === "weapons" && typeof item.power === "number") {
    return Math.max(10, item.power * 8);
  }
  return 0;
}

/**
 * Sell-back price. Falls back to half the buy price (rounded down) when
 * items.json doesn't carry an explicit `sell`, matching the Python
 * game's `get_sell_price`. Returns 0 for items the shop won't take.
 */
export function sellPriceOf(
  itemName: string,
  items: Map<string, Item>,
): number {
  const item = items.get(itemName);
  if (!item) return 0;
  if (typeof item.sell === "number" && item.sell > 0) return item.sell;
  const buy = buyPriceOf(itemName, items);
  return buy > 0 ? Math.floor(buy / 2) : 0;
}

/**
 * Add `count` charges of `itemName` to the party's shared stash,
 * stacking onto an existing entry when the item is flagged stackable
 * in items.json. Pushes a fresh entry otherwise. Returns the entry
 * that was mutated/created so callers can show "(N total)".
 *
 * `count` is the per-purchase / per-drop stack size from the catalog
 * (arrows = 20, lockpick = 5, most potions = 1).
 */
export function addToStash(
  party: Party,
  itemName: string,
  items: Map<string, Item>,
): { entry: { item: string; charges?: number }; merged: boolean } {
  const def = items.get(itemName);
  const size = def ? stackSizeOf(def) : 1;
  if (def && isStackable(def)) {
    const existing = party.inventory.find((it) => it.item === itemName);
    if (existing) {
      existing.charges = (existing.charges ?? 0) + size;
      return { entry: existing, merged: true };
    }
    const fresh = { item: itemName, charges: size };
    party.inventory.push(fresh);
    return { entry: fresh, merged: false };
  }
  // Non-stackable items: keep the legacy "one entry per copy"
  // behaviour. We still attach `charges` if the catalog provides one
  // (e.g. a torch carries its own per-copy 150-step counter even
  // when the inventory doesn't pool them).
  const fresh: { item: string; charges?: number } =
    def && typeof def.charges === "number" ? { item: itemName, charges: def.charges } : { item: itemName };
  party.inventory.push(fresh);
  return { entry: fresh, merged: false };
}

/**
 * Buy the item at `stockIndex` from the shop's stock list. Debits gold,
 * adds the item to the party stash (stacking onto an existing entry
 * for stackable items so e.g. a third bundle of arrows turns 40 →
 * 60 rather than creating a new row), and removes the item from
 * the shop's stock so it can't be bought again until somebody sells one
 * back. Refuses when the index is out of range, the counter doesn't
 * price the item, or the party can't afford it.
 */
export function buyItem(
  party: Party,
  stock: string[],
  stockIndex: number,
  items: Map<string, Item>,
): ActionResult {
  if (stockIndex < 0 || stockIndex >= stock.length) {
    return { ok: false, message: "That item is no longer on the shelf." };
  }
  const itemName = stock[stockIndex];
  const price = buyPriceOf(itemName, items);
  if (price <= 0) {
    return { ok: false, message: `${itemName} isn't for sale here.` };
  }
  if (party.gold < price) {
    return { ok: false, message: "Not enough gold." };
  }
  party.gold -= price;
  addToStash(party, itemName, items);
  stock.splice(stockIndex, 1);
  return { ok: true, message: `Bought ${itemName} for ${price}g.` };
}

/**
 * Sell the stash entry at *index* to a counter. Removes it from the
 * stash, credits the sell price, and appends the item name to the
 * shop's `stock` list so it shows up on the BUY tab next time. Refuses
 * when the index is out of range or the item has no resolvable sell
 * price.
 */
export function sellItem(
  party: Party,
  inventoryIndex: number,
  stock: string[],
  items: Map<string, Item>,
): ActionResult {
  if (inventoryIndex < 0 || inventoryIndex >= party.inventory.length) {
    return { ok: false, message: "That item is no longer in the stash." };
  }
  const entry = party.inventory[inventoryIndex];
  const price = sellPriceOf(entry.item, items);
  if (price <= 0) {
    return { ok: false, message: "The shopkeep won't take that." };
  }
  party.inventory.splice(inventoryIndex, 1);
  party.gold += price;
  stock.push(entry.item);
  return { ok: true, message: `Sold ${entry.item} for ${price}g.` };
}

/**
 * Compose the unique key for a shop instance. A general store in
 * Plainstown is a different shop than the general store in another
 * town, AND two general stores in the *same* town are different from
 * each other — so we key by `(townName, shopType, instance)`. The
 * `instance` is whatever uniquely identifies this physical counter:
 *   - tile-bump shops: the tile coordinates (`"<col>,<row>"`)
 *   - NPC-mediated shops: the NPC's home tile
 *
 * Building interiors keep their `building:Foo` prefix in `townName`,
 * which already disambiguates each interior. The `instance` adds the
 * second axis so two counters inside one interior also stay separate.
 *
 * The `instance` arg is optional — when omitted (the legacy callers
 * before per-instance support landed) the key falls back to the old
 * two-segment shape so existing tests that only thread (town, type)
 * still pass.
 */
export function shopStockKey(
  townName: string,
  shopType: string,
  instance?: string,
): string {
  if (instance == null || instance.length === 0) {
    return `${townName}|${shopType}`;
  }
  return `${townName}|${shopType}|${instance}`;
}

/**
 * Resolve the live stock array for a shop, seeding it from `defaults`
 * (the bundled `counters.json` items list) the first time the party
 * walks into this counter. The returned array is the same reference
 * stored in `inventories`, so mutations from buy/sell propagate
 * naturally and survive serialisation.
 *
 * Pass `instance` (e.g. the tile coords or NPC home position) to
 * key the stock per physical counter — without it, every counter of
 * the same shopType in the same town shares one inventory, which
 * defeats the "discover new caches as items become scarce" design.
 */
export function getOrSeedShopStock(
  inventories: Map<string, string[]>,
  townName: string,
  shopType: string,
  defaults: string[],
  instance?: string,
): string[] {
  const key = shopStockKey(townName, shopType, instance);
  let stock = inventories.get(key);
  if (!stock) {
    stock = [...defaults];
    inventories.set(key, stock);
  }
  return stock;
}

/**
 * Pay for a temple service and apply its effect to the active party.
 * Mirrors `_process_healing_counter_service` in the Python game —
 * same service ids, same costs, same "no-op when nobody needs it"
 * behaviour (no gold spent if the service would do nothing useful).
 *
 * Unknown service ids fall through to a polite refusal so future
 * counters.json entries can declare extra services without crashing.
 */
export function performTempleService(
  party: Party,
  svc: CounterService,
): ActionResult {
  const members = activeMembers(party);
  switch (svc.id) {
    case "heal_all_hp": {
      const wounded = members.filter((m) => m.hp > 0 && m.hp < m.maxHp);
      if (wounded.length === 0) {
        return { ok: false, message: "No one needs healing." };
      }
      if (party.gold < svc.cost) {
        return { ok: false, message: "Not enough gold." };
      }
      party.gold -= svc.cost;
      for (const m of wounded) m.hp = m.maxHp;
      return { ok: true, message: "Wounds close — party fully healed." };
    }
    case "restore_all_mp": {
      const drained = members.filter(
        (m) => m.hp > 0 && m.maxMp != null && (m.mp ?? 0) < m.maxMp,
      );
      if (drained.length === 0) {
        return { ok: false, message: "Magic reserves are already full." };
      }
      if (party.gold < svc.cost) {
        return { ok: false, message: "Not enough gold." };
      }
      party.gold -= svc.cost;
      for (const m of drained) m.mp = m.maxMp;
      return { ok: true, message: "Arcane power flows back to the party." };
    }
    case "cure_all_poisons": {
      // Poison status isn't modelled on PartyMember in the web port
      // yet — once it lands we can scan + cure here. For now refuse
      // without charging so the player isn't billed for nothing.
      return { ok: false, message: "No one is poisoned." };
    }
    case "raise_dead": {
      const target = members.find((m) => m.hp <= 0) ?? null;
      if (target == null) {
        return { ok: false, message: "No fallen allies to raise." };
      }
      if (party.gold < svc.cost) {
        return { ok: false, message: "Not enough gold." };
      }
      party.gold -= svc.cost;
      target.hp = target.maxHp;
      if (target.maxMp != null) target.mp = target.maxMp;
      return { ok: true, message: `${target.name} is returned to life!` };
    }
    default:
      return { ok: false, message: `Unknown service: ${svc.id}` };
  }
}
