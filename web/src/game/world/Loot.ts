/**
 * Combat loot — post-victory item drops.
 *
 * After the party wins an encounter, in addition to gold + XP they get
 * a chance to find a piece of mundane gear on the field. The drop pool
 * is the union of every item that appears in the General Store,
 * Weapons Shop, or Armor Shop counters — i.e. anything a shopkeep
 * would normally stock. This keeps drops thematically tied to "stuff
 * a wandering merchant might've been carrying" rather than handing out
 * unique magic gear at random.
 *
 * `rollLootDrop` is the lone public entry point. It's pure (no DOM,
 * no Phaser) and accepts an injectable RNG so the combat scene can
 * use Math.random in production while tests pin a seed.
 */

import type { Item } from "./Items";
import type { Counter } from "./Counters";
import { defaultRng, type RNG } from "../rng";

/** Counter shop types whose inventories feed the post-combat loot pool. */
export const LOOT_SHOP_TYPES = ["general", "weapon", "armor"] as const;

/** Probability (0-1) that a winning encounter drops an item. */
export const LOOT_DROP_CHANCE = 0.25;

/**
 * Build the de-duplicated list of item names that can drop after a
 * combat victory. Any name that appears in the general, weapon, or
 * armor counter feeds in; an item is only included if `items` actually
 * has an entry for it (so a typo in counters.json won't crash the
 * drop roll).
 *
 * The pool is sorted alphabetically for deterministic ordering — that
 * keeps the index-based RNG selection reproducible in tests without
 * depending on Map iteration order.
 */
export function buildLootPool(
  items: Map<string, Item>,
  counters: Map<string, Counter>,
): string[] {
  const seen = new Set<string>();
  for (const shopType of LOOT_SHOP_TYPES) {
    const counter = counters.get(shopType);
    if (!counter) continue;
    for (const name of counter.items) {
      if (!items.has(name)) continue;
      seen.add(name);
    }
  }
  return [...seen].sort();
}

/**
 * Roll for a post-combat item drop.
 *
 *   - With probability `LOOT_DROP_CHANCE` (25%), returns the name of
 *     a random item from the general/weapon/armor shop pool.
 *   - Otherwise returns null (no drop).
 *
 * Returns null when the pool is empty (e.g. the counters file failed
 * to load). The RNG argument lets tests pin specific outcomes; the
 * caller is responsible for advancing it consistently across rolls.
 */
export function rollLootDrop(
  items: Map<string, Item>,
  counters: Map<string, Counter>,
  rng: RNG = defaultRng,
): string | null {
  const pool = buildLootPool(items, counters);
  if (pool.length === 0) return null;
  if (rng() >= LOOT_DROP_CHANCE) return null;
  const idx = Math.floor(rng() * pool.length);
  return pool[Math.min(idx, pool.length - 1)] ?? null;
}
