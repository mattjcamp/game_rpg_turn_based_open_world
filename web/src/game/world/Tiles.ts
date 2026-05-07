/**
 * Tile id constants and per-tile properties.
 *
 * Mirrors the relevant subset of `src/settings.py` from the Python
 * project — same numeric ids so loaded maps drop in unchanged.
 *
 * **Sprite resolution is data-driven.** `tile_defs.json` is the single
 * source of truth: for each tile id it carries a `sprite` field like
 * `"overworld/grass"` or `"town/door"`, which resolves to the web URL
 * `/assets/<sprite>.png`. The hardcoded DEFS table below only carries
 * walkability + fallback colour for the small set of overworld tiles
 * that other code (state, OverworldScene) needs to reason about
 * synchronously before `tile_defs.json` has loaded; sprites for those
 * tiles also come from `tile_defs.json` once it's in cache.
 *
 * To add a new tile: drop the PNG into `web/public/assets/<key>.png`
 * and add an entry to `tile_defs.json` with the matching `sprite` key.
 * No edits required here.
 */

import { BASE_PATH, dataPath } from "./Module";

// ── Overworld tiles ─────────────────────────────────────────────
export const TILE_GRASS = 0;
export const TILE_WATER = 1;
export const TILE_FOREST = 2;
export const TILE_MOUNTAIN = 3;
export const TILE_TOWN = 4;
export const TILE_DUNGEON = 5;
export const TILE_PATH = 6;
export const TILE_SAND = 7;
export const TILE_BRIDGE = 8;
export const TILE_DUNGEON_CLEARED = 9;
export const TILE_BOAT = 64;

// ── Combat-encounter triggers (overworld) ──────────────────────
export const TILE_SPAWN = 66;
export const TILE_SPAWN_CAMPFIRE = 67;
export const TILE_SPAWN_GRAVEYARD = 68;
export const TILE_ENCOUNTER = 69;

// ── Misc / decorative ──────────────────────────────────────────
export const TILE_FOREST_ARCHWAY_UP = 77;
export const TILE_FOREST_ARCHWAY_DOWN = 78;

// ── Town interior tiles ────────────────────────────────────────
// (subset of `src/settings.py` TILE_DEFS keyed by their id)
export const TILE_TOWN_FLOOR = 10;
export const TILE_TOWN_WALL = 11;
export const TILE_TOWN_COUNTER = 12;
export const TILE_DOOR = 13;
export const TILE_DFLOOR = 20;
export const TILE_STAIRS_DOWN = 25;
export const TILE_DDOOR = 26;
export const TILE_WALL_TORCH = 34;
export const TILE_BRICK = 37;
export const TILE_SHRINE = 45;
export const TILE_PATH_FLOOR = 46;
export const TILE_SAND_FLOOR = 47;
export const TILE_FLOOR_GRAY = 48;
export const TILE_BRICK_BROWN = 49;
export const TILE_GRASS_PLAINS = 50;
export const TILE_BRICK_LIGHTER = 51;
export const TILE_SHOP_SIGN = 52;
export const TILE_TOWN_WATER = 53;
export const TILE_SCRUB = 54;
export const TILE_TOWN_GATE = 56;
export const TILE_WEAPON_COUNTER = 57;
export const TILE_ARMOR_COUNTER = 58;
export const TILE_MAGIC_COUNTER = 59;
export const TILE_SHOP_ARMOR = 60;
export const TILE_HEALING_COUNTER = 61;
export const TILE_FLOOR_LIGHT = 63;
export const TILE_LIGHT_SAND = 70;
export const TILE_WINDOW = 72;

/**
 * Per-tile flag block carried over from `tile_defs.json`. Authors set
 * these once per tile id (in contrast to `tile_properties` which set
 * them per-cell on a specific map).
 *
 * Most flags are radiance/light-related. `transparent` is used by the
 * lighting model to let light pass through water and similar.
 */
export interface TileFlags {
  /** This tile id always emits its own light (e.g., wall torch). */
  light_source?: boolean;
  light_radius?: number;
  light_intensity?: number;
  /**
   * The tile is a "feature" that emits light at a smaller radius —
   * doors, exits, and altars get this so a lit doorway shows up in
   * an otherwise-dark interior.
   */
  feature_light?: boolean;
  feature_radius?: number;
  feature_intensity?: number;
  /** Light passes through this tile (water, windows, etc.). */
  transparent?: boolean;
}

export interface TileDef {
  /** Fallback color when no sprite is loaded for this tile id. */
  color: [number, number, number];
  walkable: boolean;
  name: string;
  /**
   * Sprite path under /assets/. When present the renderer draws the
   * image instead of a coloured rectangle. Tiles without a sprite
   * (spawn markers, encounter glyphs) keep the rectangle fallback.
   */
  sprite?: string;
  /** Optional per-tile-id flag block from tile_defs.json. */
  flags?: TileFlags;
  /**
   * Interaction kind from tile_defs.json. Today's values: `"shop"`
   * (counter — opens a buy/sell or service screen), `"sign"` (shows a
   * message), `"spawn"` (overworld monster spawner). Anything else is
   * passed through unchanged for future expansion.
   */
  interactionType?: string;
  /**
   * Companion data field for the interaction. For `"shop"` this is a
   * counter key from counters.json (`general` / `weapon` / `healing` …);
   * for `"sign"` it's the message text; for `"spawn"` it identifies the
   * spawn template.
   */
  interactionData?: string;
}

const FALLBACK: TileDef = { color: [60, 60, 60], walkable: false, name: "Unknown" };

/**
 * Hardcoded defs for overworld tiles + encounter trigger glyphs.
 *
 * These are the tiles that need a synchronous TileDef before
 * `loadTileDefs()` resolves — `OverworldScene` calls `tileDef()` while
 * iterating its grid and `isEncounterTrigger()` looks up trigger ids.
 * Town/dungeon tiles only need their sprite & walkability *after*
 * `loadTileDefs()` has populated `_runtimeDefs`, so they don't need
 * to be listed here.
 *
 * Sprite paths follow the canonical `/assets/<sprite_key>.png`
 * convention so the same sprite resolves whether it comes from the
 * hardcoded table or from `tile_defs.json`.
 */
const DEFS: Record<number, TileDef> = {
  [TILE_GRASS]:    { color: [34, 139, 34],  walkable: true,  name: "Grass",
                     sprite: `${BASE_PATH}/assets/overworld/grass.png` },
  [TILE_WATER]:    { color: [30, 90, 180],  walkable: false, name: "Water",
                     sprite: `${BASE_PATH}/assets/overworld/water.png` },
  [TILE_FOREST]:   { color: [0, 80, 0],     walkable: true,  name: "Forest",
                     sprite: `${BASE_PATH}/assets/overworld/forest.png` },
  [TILE_MOUNTAIN]: { color: [130, 130, 130],walkable: false, name: "Mountain",
                     sprite: `${BASE_PATH}/assets/overworld/mountain.png` },
  [TILE_TOWN]:     { color: [180, 140, 80], walkable: true,  name: "Town",
                     sprite: `${BASE_PATH}/assets/overworld/town.png` },
  [TILE_DUNGEON]:  { color: [120, 40, 80],  walkable: true,  name: "Dungeon",
                     sprite: `${BASE_PATH}/assets/overworld/dungeon.png` },
  [TILE_PATH]:     { color: [160, 140, 100],walkable: true,  name: "Path",
                     sprite: `${BASE_PATH}/assets/overworld/path.png` },
  [TILE_SAND]:     { color: [210, 190, 130],walkable: true,  name: "Sand",
                     sprite: `${BASE_PATH}/assets/overworld/sand.png` },
  [TILE_BRIDGE]:   { color: [140, 100, 50], walkable: true,  name: "Bridge",
                     sprite: `${BASE_PATH}/assets/overworld/bridge.png` },
  [TILE_DUNGEON_CLEARED]: { color: [80, 70, 60], walkable: true, name: "Cleared Dungeon",
                     sprite: `${BASE_PATH}/assets/overworld/dungeon_cleared.png` },
  // Encounter triggers: rendered with a ✦ glyph overlaid on the
  // fallback colour. Sprites in /assets/items/campfire.png etc. are
  // available via tile_defs.json runtime entries if a scene wants
  // them, but the overworld leaves these as glyphs by design so the
  // player can spot encounters at a glance.
  [TILE_BOAT]:     { color: [110, 70, 40],  walkable: true,  name: "Boat" },
  [TILE_SPAWN]:    { color: [180, 40, 40],  walkable: true,  name: "Monster Spawn" },
  [TILE_SPAWN_CAMPFIRE]: { color: [200, 120, 30], walkable: true, name: "Campfire" },
  [TILE_SPAWN_GRAVEYARD]: { color: [120, 115, 105], walkable: true, name: "Graveyard" },
  [TILE_ENCOUNTER]: { color: [180, 60, 140], walkable: true,  name: "Encounter" },
  [TILE_FOREST_ARCHWAY_UP]:   { color: [80, 120, 60], walkable: true, name: "Forest Archway" },
  [TILE_FOREST_ARCHWAY_DOWN]: { color: [40, 55, 35],  walkable: true, name: "Forest Archway" },
};

/** Path to the player avatar sprite. */
export const PLAYER_SPRITE = `${BASE_PATH}/assets/overworld/party_marker.png`;

/**
 * Runtime-loaded tile defs sourced from `data/tile_defs.json`.
 *
 * Populated by `loadTileDefs()` in the scene's create() phase. Carries
 * walkability, fallback colour, **and** the canonical sprite path
 * derived from the def's `sprite` field (e.g. `"town/floor"` →
 * `/assets/town/floor.png`).
 */
const _runtimeDefs: Record<number, TileDef> = {};

interface RawTileDef {
  name?: string;
  walkable?: boolean;
  color?: [number, number, number];
  /** Logical sprite key, e.g. "overworld/grass". Resolved to /assets/<key>.png. */
  sprite?: string;
  /** Optional flag block (lighting + transparency). */
  flags?: TileFlags;
  interaction_type?: string;
  interaction_data?: string;
}

/**
 * Convert a logical sprite key from tile_defs.json into the runtime
 * web URL. Empty strings (intentionally unmapped tiles like Void)
 * resolve to undefined so the renderer falls back to a colour rect.
 */
export function spriteUrlForKey(key: string | undefined): string | undefined {
  if (!key) return undefined;
  if (key.startsWith("http://") || key.startsWith("https://")) return key;
  if (key.startsWith("/assets/")) return `${BASE_PATH}${key}`;
  return `${BASE_PATH}/assets/${key}.png`;
}

/**
 * Populate `_runtimeDefs` from already-parsed tile_defs.json data.
 *
 * Used by scene preload chains that fetch tile_defs.json via Phaser's
 * own loader (so it's part of the deterministic preload waterfall)
 * and then need a synchronous hand-off into the runtime cache before
 * sprite loads are queued. `loadTileDefs(url)` is the alternative
 * fetch-from-URL path, used by tests and by code paths that don't
 * have a Phaser loader handy.
 */
export function populateRuntimeDefs(raw: Record<string, RawTileDef>): void {
  for (const [k, v] of Object.entries(raw)) {
    const id = Number(k);
    if (!Number.isFinite(id)) continue;
    _runtimeDefs[id] = {
      name: v.name ?? "Unknown",
      walkable: !!v.walkable,
      color: (v.color ?? [60, 60, 60]) as [number, number, number],
      sprite: spriteUrlForKey(v.sprite),
      flags: v.flags,
      interactionType: v.interaction_type,
      interactionData: v.interaction_data,
    };
  }
}

export async function loadTileDefs(url = dataPath("tile_defs.json")): Promise<void> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as Record<string, RawTileDef>;
  populateRuntimeDefs(raw);
}

/**
 * Look up the def for a tile id.
 *
 * Order: hardcoded DEFS (overworld + triggers) wins so the synchronous
 * pre-loadTileDefs callers see consistent walkability/colour. Where
 * the hardcoded entry has no sprite (e.g. encounter glyphs) the
 * runtime sprite is filled in if available.
 *
 * For everything else (town & dungeon tiles), the runtime def from
 * tile_defs.json is the only source.
 */
export function tileDef(id: number): TileDef {
  const hard = DEFS[id];
  const runtime = _runtimeDefs[id];
  if (hard && runtime) {
    // Merge: keep the hardcoded color/walkable/name (they're the
    // synchronous truth) but borrow sprite + flags from runtime when
    // the hardcoded entry doesn't supply them. tile_defs.json's flag
    // block is the source-of-truth for lighting/transparency.
    return {
      ...hard,
      sprite: hard.sprite ?? runtime.sprite,
      flags: hard.flags ?? runtime.flags,
      interactionType: hard.interactionType ?? runtime.interactionType,
      interactionData: hard.interactionData ?? runtime.interactionData,
    };
  }
  return hard ?? runtime ?? FALLBACK;
}

/**
 * Return every {key, path} pair the renderer needs to preload.
 *
 * Sources:
 *   - hardcoded DEFS sprites (overworld tiles, available before
 *     loadTileDefs has resolved)
 *   - runtime tile_defs.json sprites — included only after
 *     loadTileDefs() has populated `_runtimeDefs`. Until then, the
 *     scene preload chain only sees the hardcoded set; scenes that
 *     need full coverage call `loadTileDefs()` first and then
 *     `spriteManifest()` again to enqueue the rest.
 *
 * Keys are stable: `tile_<id>` for tile sprites, plus the player
 * marker. Calling this twice with the same id is a no-op for Phaser's
 * loader (it dedupes by key).
 */
export function spriteManifest(): Array<{ key: string; path: string }> {
  const out: Array<{ key: string; path: string }> = [];
  const seen = new Set<number>();
  for (const [idStr, def] of Object.entries(DEFS)) {
    if (def.sprite) {
      out.push({ key: `tile_${idStr}`, path: def.sprite });
      seen.add(Number(idStr));
    }
  }
  for (const [idStr, def] of Object.entries(_runtimeDefs)) {
    const id = Number(idStr);
    if (seen.has(id)) continue;
    if (def.sprite) out.push({ key: `tile_${id}`, path: def.sprite });
  }
  out.push({ key: "player", path: PLAYER_SPRITE });
  return out;
}

export function tileSpriteKey(id: number): string | null {
  const def = tileDef(id);
  return def.sprite ? `tile_${id}` : null;
}

/** Test-only: clear the runtime cache so tests stay isolated. */
export function _clearRuntimeTileDefs(): void {
  for (const k of Object.keys(_runtimeDefs)) delete _runtimeDefs[Number(k)];
}

/** Tiles that should kick off a combat encounter when stepped on. */
const TRIGGER_IDS = new Set<number>([
  TILE_SPAWN,
  TILE_SPAWN_CAMPFIRE,
  TILE_SPAWN_GRAVEYARD,
  TILE_ENCOUNTER,
]);

export function isEncounterTrigger(id: number): boolean {
  return TRIGGER_IDS.has(id);
}
