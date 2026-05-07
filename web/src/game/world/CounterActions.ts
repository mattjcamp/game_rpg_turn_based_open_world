/**
 * Pure logic for the buy/sell + service-counter interactions.
 *
 * Mirrors the Python game's `_handle_shop_input` and
 * `_process_healing_counter_service` paths but split out from the
 * scene class so the same helpers can be unit-tested without Phaser.
 *
 * The contract follows the rest of `PartyActions.ts`: each action
 * mutates the live `Party` in place and returns `{ ok, message }` so
 * the caller can show a feedback line.
 */

import type { Party, PartyMember } from "./Party";
import { activeMembers } from "./Party";
import type { Counter, ShopService } from "./Counters";
import type { Item } from "./Items";
import { getBuyPrice, getSellPrice } from "./Items";

export interface CounterActionResult {
  ok: boolean;
  message: string;
}

/**
 * One row in the buy list — an item name plus the price the counter
 * charges. Items the counter declares but that have no resolvable
 * price (no `buy` field and no derived stat-based price) are skipped
 * here so the player isn't shown a "0 gold" line they can never act on.
 */
export interface ShopRow {
  itemName: string;
  price: number;
  item: Item | null;
}

/**
 * Build the list of buyable rows for a shop counter. Counter declares
 * the available item names; we look each one up in `items.json` to
 * resolve the catalog Item and price. Unknown / unpriced items are
 * filtered out so the UI only shows rows the player can actually buy.
 */
export function buildShopRows(
  counter: Counter,
  items: Map<string, Item>,
): ShopRow[] {
  const rows: ShopRow[] = [];
  for (const name of counter.items) {
    const item = items.get(name) ?? null;
    const price = getBuyPrice(item);
    if (price == null) continue;
    rows.push({ itemName: name, price, item });
  }
  return rows;
}

/**
 * One row in the sell list — points at an entry in `party.inventory`
 * by its index, plus the resolved sell price. Indices stay valid for
 * the current render; they're recomputed from scratch after a sell.
 */
export interface SellRow {
  /** Index into `party.inventory`. */
  inventoryIndex: number;
  itemName: string;
  price: number;
  item: Item | null;
}

/**
 * Build the list of sellable rows for the current party stash. Items
 * with no sell price are kept in the list but priced 0; the action
 * helper refuses zero-priced sells so the player can see why the
 * shopkeep won't take a quest token.
 */
export function buildSellRows(
  party: Party,
  items: Map<string, Item>,
): SellRow[] {
  return party.inventory.map((entry, idx) => {
    const item = items.get(entry.item) ?? null;
    return {
      inventoryIndex: idx,
      itemName: entry.item,
      price: getSellPrice(item),
      item,
    };
  });
}

/** Apply a buy from a shop row. Mutates `party` in place. */
export function buyFromShop(
  party: Party,
  row: ShopRow,
): CounterActionResult {
  if (party.gold < row.price) {
    return { ok: false, message: "Not enough gold." };
  }
  party.gold -= row.price;
  party.inventory.push({ item: row.itemName });
  return { ok: true, message: `Bought ${row.itemName} for ${row.price} gold.` };
}

/** Apply a sell from a sell row. Mutates `party` in place. */
export function sellToShop(
  party: Party,
  row: SellRow,
): CounterActionResult {
  if (row.price <= 0) {
    return { ok: false, message: "The shopkeep won't take that." };
  }
  if (
    row.inventoryIndex < 0 ||
    row.inventoryIndex >= party.inventory.length
  ) {
    return { ok: false, message: "That item is no longer in the stash." };
  }
  party.inventory.splice(row.inventoryIndex, 1);
  party.gold += row.price;
  return { ok: true, message: `Sold ${row.itemName} for ${row.price} gold.` };
}

// ── Service-counter actions ──────────────────────────────────────────
//
// Service counters (counters.json `kind: "service"`) carry an array of
// priced services keyed by `id`. The healer's four canonical services
// are handled here — unknown ids fall through to a polite refusal so a
// data-driven counter can declare extra services without crashing.

/**
 * Pay the service's cost and apply its effect. Mutates the active
 * party members and `party.gold`. Returns `{ ok: false }` for cases
 * where the service would do nothing useful (no one wounded, no one
 * dead) so the UI can show a context message instead of charging gold.
 */
export function applyService(
  party: Party,
  service: ShopService,
): CounterActionResult {
  const members = activeMembers(party);

  switch (service.id) {
    case "heal_all_hp": {
      const wounded = members.filter((m) => m.hp > 0 && m.hp < m.maxHp);
      if (wounded.length === 0) {
        return { ok: false, message: "No one needs healing." };
      }
      if (party.gold < service.cost) {
        return { ok: false, message: "Not enough gold." };
      }
      party.gold -= service.cost;
      for (const m of wounded) m.hp = m.maxHp;
      return {
        ok: true,
        message: `Wounds close — party fully healed.`,
      };
    }
    case "restore_all_mp": {
      const drained = members.filter(
        (m) => m.hp > 0 && m.maxMp != null && (m.mp ?? 0) < m.maxMp,
      );
      if (drained.length === 0) {
        return { ok: false, message: "Magic reserves are already full." };
      }
      if (party.gold < service.cost) {
        return { ok: false, message: "Not enough gold." };
      }
      party.gold -= service.cost;
      for (const m of drained) m.mp = m.maxMp;
      return {
        ok: true,
        message: "Arcane power flows back to the party.",
      };
    }
    case "cure_all_poisons": {
      // We don't yet model poison status on PartyMember in the web
      // port — once that lands the predicate goes here. For now the
      // service still charges gold (matching the Python flow's
      // behaviour when it can't find anyone poisoned: the message
      // refuses without charging).
      return { ok: false, message: "No one is poisoned." };
    }
    case "raise_dead": {
      const target = findFallenMember(members);
      if (target == null) {
        return { ok: false, message: "No fallen allies to raise." };
      }
      if (party.gold < service.cost) {
        return { ok: false, message: "Not enough gold." };
      }
      party.gold -= service.cost;
      target.hp = target.maxHp;
      if (target.maxMp != null) target.mp = target.maxMp;
      return {
        ok: true,
        message: `${target.name} is returned to life!`,
      };
    }
    default:
      return { ok: false, message: `Unknown service: ${service.id}` };
  }
}

function findFallenMember(members: PartyMember[]): PartyMember | null {
  for (const m of members) {
    if (m.hp <= 0) return m;
  }
  return null;
}
