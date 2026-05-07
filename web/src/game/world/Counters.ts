/**
 * Counter definitions — `data/counters.json`.
 *
 * A "counter" is a place the party interacts with from a map tile (or
 * an NPC) to buy/sell items or pay for a service. The Python project's
 * `data/counters.json` keys each counter by a short id (e.g. `general`,
 * `weapon`, `armor`, `magic`, `healing`) and carries either:
 *
 *   - a list of item names the counter sells (default `kind: "shop"`),
 *     used by buy/sell counter UIs to filter SHOP_INVENTORY; or
 *   - `kind: "service"` plus a list of priced services
 *     ({ id, name, description, cost }) which a service counter such
 *     as a temple healer offers instead of items.
 *
 * Tile cells get a counter via either of two paths, which mirror the
 * Python game's tile + map-properties layering:
 *
 *   1. Tile-id default: `tile_defs.json` carries
 *      `interaction_type: "shop"` and `interaction_data: <key>` on
 *      Counter / Weapon Counter / Armor Counter / Magic Shop /
 *      Healing Counter tile ids (12, 57, 58, 59, 61). Stepping into
 *      one of those tiles uses its counter key by default.
 *   2. Per-cell override: `tile_properties["col,row"].shop_type =
 *      <key>` lets a map author point any tile at any counter without
 *      changing its tile id (used by interior maps that decorate plain
 *      brick walls into a working stall).
 *
 * Both paths converge on a counter key that this loader resolves
 * against `counters.json`.
 */

import { dataPath } from "./Module";

export type CounterKind = "shop" | "service";

export interface ShopService {
  id: string;
  name: string;
  description: string;
  cost: number;
}

export interface Counter {
  /** Stable key used in tile_defs.interaction_data and tile_properties.shop_type. */
  key: string;
  name: string;
  description: string;
  kind: CounterKind;
  /** Item names sold here (shop counters). Empty for service counters. */
  items: string[];
  /** Priced services (service counters). Empty for shop counters. */
  services: ShopService[];
}

interface RawCounterEntry {
  name?: string;
  description?: string;
  kind?: string;
  items?: string[];
  services?: Array<{
    id?: string;
    name?: string;
    description?: string;
    cost?: number | string;
  }>;
}

type RawCountersFile = Record<string, RawCounterEntry>;

let _cache: Map<string, Counter> | null = null;

function counterFromRaw(key: string, raw: RawCounterEntry): Counter {
  const kind: CounterKind = raw.kind === "service" ? "service" : "shop";
  const services: ShopService[] = (raw.services ?? []).map((s) => ({
    id: s.id ?? "",
    name: s.name ?? s.id ?? "",
    description: s.description ?? "",
    cost: Number(s.cost ?? 0) || 0,
  }));
  return {
    key,
    name: raw.name ?? key,
    description: raw.description ?? "",
    kind,
    items: Array.isArray(raw.items) ? raw.items.slice() : [],
    services,
  };
}

/**
 * Fetch and parse the shared `data/counters.json`. Cached.
 *
 * The file lives under `/data/` (not the active module) — counters are
 * shared definitions just like items.json and spells.json. Modules that
 * need a custom counter list can override per-key entries by shipping
 * their own counters.json; that's a follow-up if/when the data demands
 * it. For now the shared file is the single source of truth.
 */
export async function loadCounters(
  url = dataPath("counters.json"),
): Promise<Map<string, Counter>> {
  if (_cache) return _cache;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as RawCountersFile;
  const out = new Map<string, Counter>();
  for (const [k, v] of Object.entries(raw)) {
    if (!v || typeof v !== "object") continue;
    out.set(k, counterFromRaw(k, v));
  }
  _cache = out;
  return out;
}

export function getCounter(
  counters: Map<string, Counter>,
  key: string,
): Counter | null {
  return counters.get(key) ?? null;
}

export function isServiceCounter(c: Counter | null): boolean {
  return !!c && c.kind === "service";
}

export function isShopCounter(c: Counter | null): boolean {
  return !!c && c.kind === "shop";
}

/** Test-only cache reset so each test starts fresh. */
export function _clearCountersCache(): void {
  _cache = null;
}
