/**
 * Town interior data.
 *
 * The Python module-editor format stores town tiles as a dict keyed by
 * "col,row" with values that are full tile-manifest entries (tile_id +
 * name + sprite path), e.g.:
 *
 *   "0,0": { "tile_id": 50, "name": "Grass Sparse", "path": "..." }
 *
 * That's a strict superset of what we need — we only consume `tile_id`
 * here. Missing positions fall back to a "void" tile id (36) so the
 * border/exterior renders as non-walkable empty space.
 */

import { TileMap, type TileLink } from "./TileMap";

/** Tile id 36 = TILE_VOID per `src/settings.py`. Non-walkable, black. */
const TILE_VOID = 36;

export interface NpcDef {
  name: string;
  /** "villager" | "shopkeep" | "priest" | "elder" | … (free-form). */
  npcType: string;
  /** Path under /assets/ — translated from the Python source path. */
  sprite: string;
  col: number;
  row: number;
  /** Either a single line or a list of lines the NPC speaks. */
  dialogue: string[];
  godName?: string;
  wanderRange?: number;
}

export interface Town {
  name: string;
  width: number;
  height: number;
  /** The tile-id 2D grid, normalised from the dict format. */
  tiles: number[][];
  /** Where the player drops in when entering from the overworld. */
  entry: { col: number; row: number };
  npcs: NpcDef[];
  /** Per-tile properties dict, same shape as overworld TileMap. */
  tileProperties: Record<string, unknown>;
  /**
   * Building interiors that live inside this town. Each interior is
   * structurally identical to a Town (same tile dict, npcs, tile_properties)
   * — we just expose them under their parent so navigation can be
   * resolved by a "Town/Interior" path.
   */
  interiors: Town[];
}

interface RawNpc {
  name?: string;
  npc_type?: string;
  sprite?: string;
  col?: number;
  row?: number;
  dialogue?: string | string[];
  god_name?: string;
  wander_range?: number;
}

interface RawTown {
  name?: string;
  width?: number;
  height?: number;
  tiles?: Record<string, { tile_id?: number } | number> | number[][];
  entry_col?: number;
  entry_row?: number;
  npcs?: RawNpc[];
  tile_properties?: Record<string, unknown>;
  interiors?: RawTown[];
}

/**
 * Translate a Python-style asset path (e.g. `src/assets/game/characters/cleric.png`)
 * into the web path (`/assets/characters/cleric.png`). Returns the
 * input unchanged if it already starts with `/assets/`.
 *
 * The web asset structure flattens `assets/game/<category>/...` to
 * `assets/<category>/...`, so a `/game/` segment is stripped on the way.
 */
export function normalizeSpritePath(path: string): string {
  if (!path) return "";
  if (path.startsWith("/assets/")) return path;
  // Capture the tail after `assets/[game/]`. Both source layouts hit this:
  //   src/assets/game/characters/cleric.png → characters/cleric.png
  //   assets/characters/cleric.png          → characters/cleric.png
  const m = path.match(/assets\/(?:game\/)?(.+)$/);
  if (m) return "/assets/" + m[1];
  // Fallback for un-prefixed paths: assume a relative web path.
  return "/assets/" + path.replace(/^\/+/, "");
}

/** Convert a "col,row"-keyed dict of rich tile entries into a 2D grid. */
export function normalizeTownTiles(
  source: RawTown["tiles"],
  width: number,
  height: number
): number[][] {
  const grid: number[][] = [];
  // Already a 2D array — accept as-is.
  if (Array.isArray(source) && Array.isArray(source[0])) {
    for (let r = 0; r < height; r++) {
      const row = source[r] ?? [];
      const out: number[] = [];
      for (let c = 0; c < width; c++) out.push(typeof row[c] === "number" ? row[c] : TILE_VOID);
      grid.push(out);
    }
    return grid;
  }
  const dict = (source as Record<string, { tile_id?: number } | number> | undefined) ?? {};
  for (let r = 0; r < height; r++) {
    const row: number[] = [];
    for (let c = 0; c < width; c++) {
      const v = dict[`${c},${r}`];
      if (v == null) {
        row.push(TILE_VOID);
      } else if (typeof v === "number") {
        row.push(v);
      } else if (typeof v === "object" && typeof v.tile_id === "number") {
        row.push(v.tile_id);
      } else {
        row.push(TILE_VOID);
      }
    }
    grid.push(row);
  }
  return grid;
}

export function townFromRaw(raw: RawTown): Town {
  const w = raw.width ?? 0;
  const h = raw.height ?? 0;
  if (!w || !h) throw new Error(`Town '${raw.name ?? "?"}' missing width/height`);
  const tiles = normalizeTownTiles(raw.tiles, w, h);
  const npcs: NpcDef[] = (raw.npcs ?? []).map((n) => ({
    name: n.name ?? "?",
    npcType: n.npc_type ?? "villager",
    sprite: normalizeSpritePath(n.sprite ?? ""),
    col: n.col ?? 0,
    row: n.row ?? 0,
    dialogue: Array.isArray(n.dialogue)
      ? n.dialogue.map(String)
      : n.dialogue
        ? [String(n.dialogue)]
        : [],
    godName: n.god_name,
    wanderRange: n.wander_range,
  }));
  // Interiors are structurally identical to towns — recurse with the
  // same parser and treat them as nested Town objects. We don't allow
  // interiors-of-interiors today (none in the data); a too-deep nest
  // would just be parsed but unreachable via the path resolver.
  const interiors: Town[] = (raw.interiors ?? []).map(townFromRaw);
  return {
    name: raw.name ?? "Unknown",
    width: w,
    height: h,
    tiles,
    entry: { col: raw.entry_col ?? 0, row: raw.entry_row ?? 0 },
    npcs,
    tileProperties: (raw.tile_properties ?? {}) as Record<string, unknown>,
    interiors,
  };
}

/** Build a TileMap from a Town so existing walkability/link helpers apply. */
export function tileMapForTown(town: Town): TileMap {
  return new TileMap(town.width, town.height, town.tiles, {
    tileProperties: town.tileProperties as Record<string, never>,
    label: town.name,
  });
}

let _townCache: Town[] | null = null;

/** Fetch and parse the bundled towns.json. Result is cached. */
export async function loadTowns(url = "/data/towns.json"): Promise<Town[]> {
  if (_townCache) return _townCache;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as RawTown[];
  if (!Array.isArray(raw)) throw new Error("towns.json is not an array");
  _townCache = raw.map(townFromRaw);
  return _townCache;
}

export function getTownByName(towns: Town[], name: string): Town | null {
  return towns.find((t) => t.name === name) ?? null;
}

/**
 * Find a building interior inside a named parent town.
 *
 * Path syntax: `"<TownName>/<InteriorName>"`. Both the town and the
 * interior are looked up by exact name match.
 */
export function getInteriorByPath(towns: Town[], path: string): Town | null {
  const idx = path.indexOf("/");
  if (idx <= 0) return null;
  const townName = path.slice(0, idx);
  const interiorName = path.slice(idx + 1);
  const town = getTownByName(towns, townName);
  if (!town) return null;
  return town.interiors.find((i) => i.name === interiorName) ?? null;
}

/**
 * Resolve either a bare town name or a "Town/Interior" path to the
 * matching map. This is the single entry point scenes should use when
 * they receive a `mapPath` from a tile link — the caller doesn't need
 * to know whether it's a town or an interior.
 */
export function resolveTownOrInterior(towns: Town[], path: string): Town | null {
  if (path.includes("/")) return getInteriorByPath(towns, path);
  return getTownByName(towns, path);
}

/**
 * Returns the parent town's name for a "Town/Interior" path, or null
 * for a bare town name (which has no parent).
 *
 * Useful for scenes that need to know which town to return to from an
 * interior — interior exits link back via `town:<TownName>` already,
 * so this is mostly a fallback for cases where the interior data is
 * missing that link.
 */
export function parentTownName(path: string): string | null {
  const idx = path.indexOf("/");
  return idx > 0 ? path.slice(0, idx) : null;
}

/** Re-export the link type so scenes don't need to import from TileMap. */
export type { TileLink };

/** Test-only: clear the loader cache so each test starts fresh. */
export function _clearTownCache(): void {
  _townCache = null;
}
