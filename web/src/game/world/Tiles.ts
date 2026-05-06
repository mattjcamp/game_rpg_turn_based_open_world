/**
 * Tile id constants and per-tile properties.
 *
 * Mirrors the relevant subset of `src/settings.py` from the Python
 * project — same numeric ids so loaded maps drop in unchanged.
 *
 * For the first overworld slice we render every tile as a solid
 * coloured rectangle, with the colour matching the Python TILE_DEFS.
 * A future slice can swap the colour for a sprite without touching
 * the data layer.
 */

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
export const TILE_DOOR = 13;             // walkable
export const TILE_DFLOOR = 20;           // dungeon stone floor — also used by Seat of the Realm
export const TILE_BRICK = 37;            // red brick wall — blocked
export const TILE_SHRINE = 45;           // walkable shrine
export const TILE_PATH_FLOOR = 46;       // alias of overworld path
export const TILE_SAND_FLOOR = 47;       // alias of overworld sand
export const TILE_FLOOR_GRAY = 48;       // walkable interior floor
export const TILE_BRICK_BROWN = 49;      // brown brick wall — blocked
export const TILE_GRASS_PLAINS = 50;     // walkable grass variant
export const TILE_BRICK_LIGHTER = 51;    // lighter brick wall — blocked
export const TILE_SHOP_SIGN = 52;        // store sign — blocked
export const TILE_TOWN_WATER = 53;       // water variant — blocked
export const TILE_SCRUB = 54;            // scrubland — walkable
export const TILE_TOWN_GATE = 56;        // gate — walkable
export const TILE_SHOP_ARMOR = 60;       // armoury sign — blocked
export const TILE_FLOOR_LIGHT = 63;      // walkable interior floor (lighter)
export const TILE_LIGHT_SAND = 70;       // walkable sand variant

export interface TileDef {
  /** Fallback color when no sprite is loaded for this tile id. */
  color: [number, number, number];
  walkable: boolean;
  name: string;
  /**
   * Optional sprite path under /assets/. When present the renderer
   * draws the image instead of a coloured rectangle. Tiles without
   * a sprite (spawn markers, encounter glyphs) keep the rectangle
   * fallback.
   */
  sprite?: string;
}

const FALLBACK: TileDef = { color: [60, 60, 60], walkable: false, name: "Unknown" };

const DEFS: Record<number, TileDef> = {
  [TILE_GRASS]:    { color: [34, 139, 34],  walkable: true,  name: "Grass",
                     sprite: "/assets/terrain/grass.png" },
  [TILE_WATER]:    { color: [30, 90, 180],  walkable: false, name: "Water",
                     sprite: "/assets/terrain/water.png" },
  [TILE_FOREST]:   { color: [0, 80, 0],     walkable: true,  name: "Forest",
                     sprite: "/assets/terrain/forest.png" },
  [TILE_MOUNTAIN]: { color: [130, 130, 130],walkable: false, name: "Mountain",
                     sprite: "/assets/terrain/mountain.png" },
  [TILE_TOWN]:     { color: [180, 140, 80], walkable: true,  name: "Town",
                     sprite: "/assets/terrain/town.png" },
  [TILE_DUNGEON]:  { color: [120, 40, 80],  walkable: true,  name: "Dungeon",
                     sprite: "/assets/terrain/dungeon.png" },
  [TILE_PATH]:     { color: [160, 140, 100],walkable: true,  name: "Path",
                     sprite: "/assets/terrain/path.png" },
  [TILE_SAND]:     { color: [210, 190, 130],walkable: true,  name: "Sand",
                     sprite: "/assets/terrain/sand.png" },
  [TILE_BRIDGE]:   { color: [140, 100, 50], walkable: true,  name: "Bridge",
                     sprite: "/assets/terrain/bridge.png" },
  [TILE_DUNGEON_CLEARED]: { color: [80, 70, 60], walkable: true, name: "Cleared Dungeon",
                     sprite: "/assets/terrain/dungeon_cleared.png" },
  // No sprite yet — render via fallback color + ✦ glyph overlay.
  [TILE_BOAT]:     { color: [110, 70, 40],  walkable: true,  name: "Boat" },
  [TILE_SPAWN]:    { color: [180, 40, 40],  walkable: true,  name: "Monster Spawn" },
  [TILE_SPAWN_CAMPFIRE]: { color: [200, 120, 30], walkable: true, name: "Campfire" },
  [TILE_SPAWN_GRAVEYARD]: { color: [120, 115, 105], walkable: true, name: "Graveyard" },
  [TILE_ENCOUNTER]: { color: [180, 60, 140], walkable: true,  name: "Encounter" },
  [TILE_FOREST_ARCHWAY_UP]:   { color: [80, 120, 60], walkable: true, name: "Forest Archway" },
  [TILE_FOREST_ARCHWAY_DOWN]: { color: [40, 55, 35],  walkable: true, name: "Forest Archway" },

  // ── Town interior (covers all tiles used by the bundled towns) ─
  [TILE_DOOR]:          { color: [120, 80, 40],   walkable: true,  name: "Door",
                          sprite: "/assets/town/door.png" },
  [TILE_DFLOOR]:        { color: [50, 45, 40],    walkable: true,  name: "Stone Floor",
                          sprite: "/assets/dungeon/stone_floor.png" },
  [TILE_BRICK]:         { color: [120, 60, 50],   walkable: false, name: "Brick",
                          sprite: "/assets/town/brick_wall_red.png" },
  [TILE_SHRINE]:        { color: [200, 180, 110], walkable: true,  name: "Shrine",
                          sprite: "/assets/town/shrine_church.png" },
  [TILE_PATH_FLOOR]:    { color: [160, 140, 100], walkable: true,  name: "Path",
                          sprite: "/assets/terrain/path.png" },
  [TILE_SAND_FLOOR]:    { color: [210, 190, 130], walkable: true,  name: "Sand",
                          sprite: "/assets/terrain/sand.png" },
  [TILE_FLOOR_GRAY]:    { color: [120, 110, 100], walkable: true,  name: "Floor",
                          sprite: "/assets/town/floor_gray.png" },
  [TILE_BRICK_BROWN]:   { color: [110, 80, 60],   walkable: false, name: "Brick Wall",
                          sprite: "/assets/town/brick_wall_brown.png" },
  [TILE_GRASS_PLAINS]:  { color: [70, 130, 60],   walkable: true,  name: "Grass",
                          sprite: "/assets/town/grass_plains.png" },
  [TILE_BRICK_LIGHTER]: { color: [150, 140, 130], walkable: false, name: "Wall",
                          sprite: "/assets/town/wall_lighter.png" },
  [TILE_SHOP_SIGN]:     { color: [180, 140, 80],  walkable: false, name: "Shop Sign",
                          sprite: "/assets/town/shop_sign.png" },
  [TILE_TOWN_WATER]:    { color: [30, 90, 180],   walkable: false, name: "Water",
                          sprite: "/assets/terrain/water.png" },
  [TILE_SCRUB]:         { color: [80, 110, 50],   walkable: true,  name: "Scrub",
                          sprite: "/assets/town/brush_scrubland.png" },
  [TILE_TOWN_GATE]:     { color: [140, 100, 60],  walkable: true,  name: "Gate",
                          sprite: "/assets/items/town_gate.png" },
  [TILE_SHOP_ARMOR]:    { color: [180, 140, 80],  walkable: false, name: "Armoury",
                          sprite: "/assets/town/shop_sign.png" },
  [TILE_FLOOR_LIGHT]:   { color: [180, 160, 130], walkable: true,  name: "Floor",
                          sprite: "/assets/town/floor_light.png" },
  [TILE_LIGHT_SAND]:    { color: [220, 200, 150], walkable: true,  name: "Sand",
                          sprite: "/assets/town/light_sand.png" },
};

/** Path to the player avatar sprite. */
export const PLAYER_SPRITE = "/assets/terrain/party_marker.png";

/**
 * Return every {key, path} pair the renderer needs to preload.
 * Keys are stable strings — `tile_<id>` for tile sprites, plus the
 * player marker.
 */
export function spriteManifest(): Array<{ key: string; path: string }> {
  const out: Array<{ key: string; path: string }> = [];
  for (const [idStr, def] of Object.entries(DEFS)) {
    if (def.sprite) out.push({ key: `tile_${idStr}`, path: def.sprite });
  }
  out.push({ key: "player", path: PLAYER_SPRITE });
  return out;
}

export function tileSpriteKey(id: number): string | null {
  return DEFS[id]?.sprite ? `tile_${id}` : null;
}

/**
 * Runtime-loaded tile defs sourced from `data/tile_defs.json`.
 *
 * The hand-coded DEFS above only cover the overworld tiles we render
 * with sprites. Towns and dungeons reference 60+ additional tile ids
 * (floors, walls, decorations) whose walkability and colour rules we
 * want to honour without duplicating the JSON inline. `loadTileDefs()`
 * populates this cache once; `tileDef()` consults it as a fallback.
 */
const _runtimeDefs: Record<number, TileDef> = {};

export async function loadTileDefs(url = "/data/tile_defs.json"): Promise<void> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as Record<string, {
    name?: string;
    walkable?: boolean;
    color?: [number, number, number];
  }>;
  for (const [k, v] of Object.entries(raw)) {
    const id = Number(k);
    if (!Number.isFinite(id)) continue;
    _runtimeDefs[id] = {
      name: v.name ?? "Unknown",
      walkable: !!v.walkable,
      color: (v.color ?? [60, 60, 60]) as [number, number, number],
    };
  }
}

/**
 * Look up the def for a tile id. Order: hardcoded DEFS (with sprites
 * for overworld tiles) → runtime tile_defs.json → conservative fallback.
 */
export function tileDef(id: number): TileDef {
  return DEFS[id] ?? _runtimeDefs[id] ?? FALLBACK;
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
