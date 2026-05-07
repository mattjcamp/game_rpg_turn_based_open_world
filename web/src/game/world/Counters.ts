/**
 * Counters loader — port of `data/counters.json`.
 *
 * Counters are the catalog of "things you can do at a service NPC":
 * shopkeeps' wares (general / weapon / armor / magic / reagent / inn /
 * guild) and the temple Healing Counter's miracles (heal-all, restore-
 * mp, cure-poisons, raise-dead). Mirrors `src/party.py::SHOP_INVENTORY`
 * and the Python game's `_handle_shop_input` /
 * `_handle_healing_counter_input` dispatch.
 *
 * Two flavours land in the same `Counter` shape:
 *
 *   - kind === undefined (default) → `items[]` is a list of item names
 *     the shopkeep sells. Buy prices come from items.json's `buy`
 *     field via the items catalog; sell prices from `sell`.
 *   - kind === "service" → `services[]` is the menu of fixed-price
 *     temple services. Each entry has id/name/description/cost.
 */

import { dataPath } from "./Module";

export interface CounterService {
  id: string;
  name: string;
  description: string;
  cost: number;
}

export interface Counter {
  /** "general", "weapon", "armor", "magic", "reagent", "inn", "guild",
   *  "healing" — keyed by the npc's shop_type. */
  shopType: string;
  name: string;
  description: string;
  /** Item names the shop sells. Empty for service counters. */
  items: string[];
  /** Distinguishes regular shops (undefined) from service counters
   *  ("service"). */
  kind?: string;
  /** Service menu entries — present only when kind === "service". */
  services?: CounterService[];
}

interface RawCounter {
  name?: string;
  description?: string;
  items?: string[];
  kind?: string;
  services?: Array<{ id?: string; name?: string; description?: string; cost?: number }>;
}

let _cache: Map<string, Counter> | null = null;

export async function loadCounters(
  url = dataPath("counters.json"),
): Promise<Map<string, Counter>> {
  if (_cache) return _cache;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as Record<string, RawCounter>;
  _cache = parseCounters(raw);
  return _cache;
}

/** Parse a raw counters.json blob into the typed map. */
export function parseCounters(raw: Record<string, RawCounter>): Map<string, Counter> {
  const out = new Map<string, Counter>();
  for (const [shopType, body] of Object.entries(raw)) {
    out.set(shopType, {
      shopType,
      name: body.name ?? shopType,
      description: body.description ?? "",
      items: body.items ?? [],
      kind: body.kind,
      services: (body.services ?? []).map((s) => ({
        id:          s.id          ?? "",
        name:        s.name        ?? "?",
        description: s.description ?? "",
        cost:        s.cost        ?? 0,
      })),
    });
  }
  return out;
}

/** Test-only escape hatch for the module-scope cache. */
export function _clearCountersCache(): void {
  _cache = null;
}
