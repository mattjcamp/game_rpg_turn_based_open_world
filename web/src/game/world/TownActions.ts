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
 * Buy *itemName* from a counter. Debits gold and pushes a fresh entry
 * onto the shared stash. Refuses when the counter doesn't price the
 * item or the party can't afford it.
 */
export function buyItem(
  party: Party,
  itemName: string,
  items: Map<string, Item>,
): ActionResult {
  const price = buyPriceOf(itemName, items);
  if (price <= 0) {
    return { ok: false, message: `${itemName} isn't for sale here.` };
  }
  if (party.gold < price) {
    return { ok: false, message: "Not enough gold." };
  }
  party.gold -= price;
  party.inventory.push({ item: itemName });
  return { ok: true, message: `Bought ${itemName} for ${price}g.` };
}

/**
 * Sell the stash entry at *index* to a counter. Removes it from the
 * stash and credits the sell price. Refuses when the index is out of
 * range or the item has no resolvable sell price.
 */
export function sellItem(
  party: Party,
  inventoryIndex: number,
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
  return { ok: true, message: `Sold ${entry.item} for ${price}g.` };
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
