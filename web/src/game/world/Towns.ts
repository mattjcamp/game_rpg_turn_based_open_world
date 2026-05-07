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
import { modulePath, withBase } from "./Module";

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
  /**
   * For shopkeep NPCs only — keys into counters.json
   * (general/weapon/armor/magic/reagent/inn/guild). Tells the shop UI
   * which catalog to display. Priests use the "healing" counter
   * implicitly so this field is unused for them.
   */
  shopType?: string;
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
  shop_type?: string;
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
  if (path.startsWith("/assets/")) return withBase(path);
  // Capture the tail after `assets/[game/]`. Both source layouts hit this:
  //   src/assets/game/characters/cleric.png → characters/cleric.png
  //   assets/characters/cleric.png          → characters/cleric.png
  const m = path.match(/assets\/(?:game\/)?(.+)$/);
  if (m) return withBase("/assets/" + m[1]);
  // Fallback for un-prefixed paths: assume a relative web path.
  return withBase("/assets/" + path.replace(/^\/+/, ""));
}

// ── NPC sprite resolution ─────────────────────────────────────────
//
// Slightly stricter than the Python renderer's chain: we let the
// `npc_type` field outrank the data file's explicit `sprite` path
// when the type is a known role (shopkeep, innkeeper, elder, priest,
// mage, etc.). The `sprite` field in the shipped towns.json is
// often a copy-paste placeholder (every Shanty Town NPC literally
// points at fighter.png), so honouring `npc_type` first is what
// makes a town read as a town.
//
//   1. If npc_type is in NPC_ROLE_SPRITES, use that sprite.
//   2. Otherwise honour the explicit `sprite` path when its texture
//      is loaded (Lonny the alchemist-villager keeps his portrait).
//   3. Otherwise hash the NPC name into one of six villager variants
//      so crowds of plain villagers visually differ.

/**
 * Sprite map for known NPC roles. Keys are npc_type values that
 * carry strong visual intent — those win over whatever the data file
 * has in the `sprite` field. Plain `villager` is intentionally NOT
 * in this map so that a villager with a custom sprite (Lonny → Alchemist)
 * keeps it.
 */
const NPC_ROLE_SPRITES: Record<string, string> = {
  shopkeep:  withBase("/assets/npcs/shopkeep.png"),
  innkeeper: withBase("/assets/npcs/innkeeper.png"),
  elder:     withBase("/assets/npcs/elder.png"),
  // Type aliases the source data uses but the manifest doesn't ship a
  // unique sprite for — fall back to the closest character class so
  // priests look like clerics, mages like wizards, etc.
  priest:    withBase("/assets/characters/cleric.png"),
  cleric:    withBase("/assets/characters/cleric.png"),
  mage:      withBase("/assets/characters/wizard.png"),
  wizard:    withBase("/assets/characters/wizard.png"),
  guard:     withBase("/assets/npcs/villager_guard.png"),
  bard:      withBase("/assets/npcs/villager_bard.png"),
};

/** The six villager fallbacks, indexed by hash(name) % 6. */
const VILLAGER_SPRITES = [
  withBase("/assets/npcs/villager_citizen.png"),
  withBase("/assets/npcs/villager_shepherd.png"),
  withBase("/assets/npcs/villager_bard.png"),
  withBase("/assets/npcs/villager_guard.png"),
  withBase("/assets/npcs/villager_beggar.png"),
  withBase("/assets/npcs/villager_child.png"),
];

/** Tiny stable hash so the same NPC name always picks the same villager. */
function hashName(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) {
    h = (h * 31 + name.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

/**
 * Resolve a sprite path for an NPC. `textureExists` is a predicate
 * the scene supplies (Phaser's `this.textures.exists`); when omitted
 * (tests / preload paths) we assume any path resolves so the chain
 * still picks the most specific entry.
 *
 * Priority:
 *   1. Known role npc_type (shopkeep / innkeeper / elder / priest / …)
 *      → role sprite. Wins over the data file's explicit `sprite`,
 *      which is often a generic placeholder.
 *   2. Explicit `sprite` field, when its texture is loaded.
 *   3. Hash-by-name into one of six villager variants.
 */
export function resolveNpcSprite(
  npc: { name: string; npcType?: string; sprite?: string },
  textureExists?: (path: string) => boolean,
): string {
  // 1. Role-based mapping — the strongest signal the data carries.
  const t = (npc.npcType ?? "").toLowerCase();
  const role = NPC_ROLE_SPRITES[t];
  if (role && (!textureExists || textureExists(role))) return role;
  // 2. Explicit custom sprite, when its texture exists.
  if (npc.sprite && (!textureExists || textureExists(npc.sprite))) {
    return npc.sprite;
  }
  // 3. Hash-by-name → one of six villager variants.
  return VILLAGER_SPRITES[hashName(npc.name) % VILLAGER_SPRITES.length];
}

/** Every sprite path the resolver may hand back — used by preloaders. */
export const NPC_SPRITE_MANIFEST: string[] = [
  ...new Set<string>([
    ...Object.values(NPC_ROLE_SPRITES),
    ...VILLAGER_SPRITES,
  ]),
];

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
    shopType: n.shop_type,
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

/**
 * Fetch and parse the active module's towns.json. Result is cached.
 *
 * Path matches the Python project: `modules/<name>/towns.json`.
 */
export async function loadTowns(url = modulePath("towns.json")): Promise<Town[]> {
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
