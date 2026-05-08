/**
 * Examine state — port of `src/states/examine.py`.
 *
 * When the party stands on an overworld tile and presses E, the scene
 * zooms into a 12×14 themed grid. The party walks a single avatar
 * around picking up forageable items (rocks, healing herbs, reagents).
 * Rangers and Alchemists give the party two advantages: doubled
 * reagent weight in the random loot table, and a one-time INT
 * saving-throw on first visit to discover a free reagent.
 *
 * This module is pure logic — generation, herbalist discovery, and
 * pickup. The Phaser scene owns rendering and input.
 */

import type { Party, PartyMember } from "./Party";
import { TILE_GRASS, TILE_FOREST, TILE_SAND, TILE_PATH, TILE_MOUNTAIN } from "./Tiles";
import { statMod } from "./PartyActions";

export const EXAMINE_COLS = 12;
export const EXAMINE_ROWS = 14;
/** The avatar's starting cell in the interior grid (centre-ish). */
export const EXAMINE_START_COL = 5;
export const EXAMINE_START_ROW = 6;

export type ObstacleKind = "bush" | "tree" | "rock";

interface ObstacleSpec {
  kind: ObstacleKind;
  min: number;
  max: number;
}

/** Per-terrain obstacle profile — copied from `examine.py:TERRAIN_OBSTACLES`. */
const TERRAIN_OBSTACLES: Record<number, ObstacleSpec> = {
  [TILE_GRASS]:  { kind: "bush", min: 0, max: 2 },
  [TILE_FOREST]: { kind: "tree", min: 6, max: 10 },
  [TILE_SAND]:   { kind: "rock", min: 1, max: 3 },
  [TILE_PATH]:   { kind: "bush", min: 0, max: 1 },
};
const DEFAULT_OBSTACLES: ObstacleSpec = { kind: "bush", min: 0, max: 1 };

/**
 * Per-terrain weighted loot table. `_reagent_` is a placeholder — when
 * rolled, a real reagent name is picked from FORAGE_REAGENTS. Mirrors
 * `examine.py:EXAMINE_LOOT`.
 */
const EXAMINE_LOOT: Record<number, ReadonlyArray<readonly [string, number]>> = {
  [TILE_GRASS]:  [["Rock", 10], ["_reagent_", 4], ["Healing Herb", 2]],
  [TILE_FOREST]: [["Rock", 8],  ["_reagent_", 6], ["Healing Herb", 3]],
  [TILE_SAND]:   [["Rock", 12], ["_reagent_", 3], ["Healing Herb", 1]],
  [TILE_PATH]:   [["Rock", 10], ["_reagent_", 3], ["Healing Herb", 2]],
};
const DEFAULT_LOOT = EXAMINE_LOOT[TILE_GRASS];

export const FORAGE_REAGENTS = [
  "Moonpetal",
  "Glowcap Mushroom",
  "Serpent Root",
  "Brimite Ore",
  "Spring Water",
];

const HERBALIST_CLASSES = new Set(["ranger", "alchemist"]);

/** Themes the scene uses for floor / edge colouring. */
export const EXAMINE_THEMES: Record<number, { floor: number; edge: number; obstacle: number }> = {
  [TILE_GRASS]:  { floor: 0x6dad55, edge: 0x4a7d3b, obstacle: 0x355d28 },
  [TILE_FOREST]: { floor: 0x4a7d3b, edge: 0x335628, obstacle: 0x1f3b18 },
  [TILE_SAND]:   { floor: 0xd9c08e, edge: 0xb89a6b, obstacle: 0x8c7546 },
  [TILE_PATH]:   { floor: 0xb09472, edge: 0x8c7656, obstacle: 0x6b563f },
};
const DEFAULT_THEME = EXAMINE_THEMES[TILE_GRASS];

export function themeForExamine(tileId: number) {
  return EXAMINE_THEMES[tileId] ?? DEFAULT_THEME;
}

/** Map any overworld tile id to one of the four themed types. */
export function themeTileFor(tileId: number): number {
  if (tileId === TILE_FOREST) return TILE_FOREST;
  if (tileId === TILE_SAND)   return TILE_SAND;
  if (tileId === TILE_PATH)   return TILE_PATH;
  return TILE_GRASS;
}

/**
 * In-memory layout shape — the scene reads this and the persistence
 * layer round-trips it via gameState.
 */
export interface ExamineLayout {
  /** Themed terrain id (one of grass/forest/sand/path). */
  tileType: number;
  /** Display name from tile_defs (e.g. "Forest"). */
  tileName: string;
  /** Obstacles by `${col},${row}`. */
  obstacles: Map<string, ObstacleKind>;
  /** Ground items by `${col},${row}`. */
  groundItems: Map<string, { item: string }>;
  /** True once a herbalist (Ranger / Alchemist) has combed this area. */
  reagentsSearched: boolean;
}

/** Inclusive integer in [lo, hi] using the supplied rng. */
function randInt(rng: () => number, lo: number, hi: number): number {
  return Math.floor(rng() * (hi - lo + 1)) + lo;
}

function pickWeighted<T>(rng: () => number, table: ReadonlyArray<readonly [T, number]>): T {
  let total = 0;
  for (const [, w] of table) total += w;
  let pick = rng() * total;
  for (const [v, w] of table) {
    pick -= w;
    if (pick <= 0) return v;
  }
  return table[table.length - 1][0];
}

/** True iff the active party has at least one alive Ranger or Alchemist. */
export function hasHerbalist(members: PartyMember[]): boolean {
  return members.some(
    (m) => m.hp > 0 && HERBALIST_CLASSES.has(m.class.toLowerCase()),
  );
}

/**
 * Build the weighted loot table for this terrain, doubling the
 * `_reagent_` weight when a herbalist is present. Mirrors
 * `_build_loot_table` in the Python state.
 */
function buildLootTable(
  tileId: number,
  herbalist: boolean,
): ReadonlyArray<readonly [string, number]> {
  const base = EXAMINE_LOOT[tileId] ?? DEFAULT_LOOT;
  return base.map(([name, weight]): readonly [string, number] => {
    if (herbalist && name === "_reagent_") return [name, weight * 2];
    return [name, weight];
  });
}

/** Replace a `_reagent_` placeholder with a concrete reagent. */
function resolveItemName(raw: string, rng: () => number): string {
  if (raw !== "_reagent_") return raw;
  return FORAGE_REAGENTS[Math.floor(rng() * FORAGE_REAGENTS.length)];
}

/**
 * Build a fresh layout for a tile. Includes obstacle scattering, a
 * 0–1 random ground item from the weighted table, and the themed
 * floor / display name. Caller decides whether to additionally call
 * `attemptHerbalistDiscovery` for the on-enter INT save.
 */
export function generateExamineLayout(
  rawTileId: number,
  tileName: string,
  members: PartyMember[],
  rng: () => number,
): ExamineLayout {
  const tileType = themeTileFor(rawTileId);
  const obstacles = new Map<string, ObstacleKind>();
  const spec = TERRAIN_OBSTACLES[tileType] ?? DEFAULT_OBSTACLES;
  const count = randInt(rng, spec.min, spec.max);
  for (let placed = 0; placed < count; placed++) {
    for (let attempt = 0; attempt < 40; attempt++) {
      const col = randInt(rng, 1, EXAMINE_COLS - 2);
      const row = randInt(rng, 1, EXAMINE_ROWS - 2);
      if (col === EXAMINE_START_COL && row === EXAMINE_START_ROW) continue;
      const key = `${col},${row}`;
      if (obstacles.has(key)) continue;
      obstacles.set(key, spec.kind);
      break;
    }
  }
  // Random ground items — same distribution as Python (60% nothing).
  const groundItems = new Map<string, { item: string }>();
  const numItems = pickWeighted(rng, [[0, 3], [1, 2]] as const);
  if (numItems > 0) {
    const table = buildLootTable(tileType, hasHerbalist(members));
    for (let attempt = 0; attempt < 30; attempt++) {
      const col = randInt(rng, 1, EXAMINE_COLS - 2);
      const row = randInt(rng, 1, EXAMINE_ROWS - 2);
      if (col === EXAMINE_START_COL && row === EXAMINE_START_ROW) continue;
      const key = `${col},${row}`;
      if (obstacles.has(key)) continue;
      if (groundItems.has(key)) continue;
      const raw = pickWeighted(rng, table);
      groundItems.set(key, { item: resolveItemName(raw, rng) });
      break;
    }
  }
  return {
    tileType,
    tileName,
    obstacles,
    groundItems,
    reagentsSearched: false,
  };
}

export interface HerbalistDiscovery {
  member: string;
  reagent: string;
}

/**
 * For each alive Ranger/Alchemist, roll d20 + INT modifier vs DC 13.
 * On success the character finds a random reagent, which is appended
 * to the party stash. Returns the per-member discoveries (caller
 * builds a UI message).
 *
 * The Python game raised this DC from 10 to 13 to slow farming; we
 * keep that tuning. Mirrors `_attempt_herbalist_discovery`.
 */
export function attemptHerbalistDiscovery(
  party: Party,
  members: PartyMember[],
  rng: () => number,
): HerbalistDiscovery[] {
  const out: HerbalistDiscovery[] = [];
  for (const m of members) {
    if (m.hp <= 0) continue;
    if (!HERBALIST_CLASSES.has(m.class.toLowerCase())) continue;
    const roll = randInt(rng, 1, 20) + statMod(m.intelligence);
    if (roll < 13) continue;
    const reagent = FORAGE_REAGENTS[Math.floor(rng() * FORAGE_REAGENTS.length)];
    party.inventory.push({ item: reagent });
    out.push({ member: m.name, reagent });
  }
  return out;
}

/**
 * Serialise a layout for `gameState.examineLayouts`. Maps don't
 * survive a JSON.stringify, so we flatten to plain objects keyed by
 * `${col},${row}`.
 */
export interface ExamineSavedLayout {
  tileType: number;
  tileName: string;
  obstacles: Record<string, ObstacleKind>;
  groundItems: Record<string, { item: string }>;
  reagentsSearched: boolean;
}

export function freezeLayout(layout: ExamineLayout): ExamineSavedLayout {
  return {
    tileType: layout.tileType,
    tileName: layout.tileName,
    obstacles: Object.fromEntries(layout.obstacles),
    groundItems: Object.fromEntries(layout.groundItems),
    reagentsSearched: layout.reagentsSearched,
  };
}

export function thawLayout(saved: ExamineSavedLayout): ExamineLayout {
  return {
    tileType: saved.tileType,
    tileName: saved.tileName,
    obstacles: new Map(Object.entries(saved.obstacles)),
    groundItems: new Map(Object.entries(saved.groundItems)),
    reagentsSearched: !!saved.reagentsSearched,
  };
}

/**
 * Pick the floor tile id for a single examine cell. Theme drives the
 * base sprite (grass/forest/sand/path), and a deterministic per-cell
 * hash sprinkles a small percentage of accent tiles so the grid
 * doesn't look like a flat field.
 *
 * Variety profiles roughly mirror the Python game's procedural texture
 * passes (`_draw_examine_floor_tile`): grass mostly grass with rare
 * trees showing through; forest is denser with grass clearings; sand
 * is uniform with the occasional lighter patch; path runs a packed
 * dirt strip with grass bordering it.
 */
export function floorTileFor(themeId: number, col: number, row: number): number {
  const h = ((col * 37 + row * 13) & 0xff);
  if (themeId === TILE_FOREST) {
    // Forest theme — mostly forest, ~25% grass for breathing room.
    return h % 4 === 0 ? TILE_GRASS : TILE_FOREST;
  }
  if (themeId === TILE_SAND) {
    // Sand — uniform; the obstacles + edges carry visual variety.
    return TILE_SAND;
  }
  if (themeId === TILE_PATH) {
    // Path — a 2-tile-wide strip down the middle (cols 5 and 6),
    // grass elsewhere. Reads as a footpath cutting through a clearing.
    if (col === 5 || col === 6) return TILE_PATH;
    return TILE_GRASS;
  }
  // Grass theme (the default fallback). Mostly grass; occasionally a
  // forest tile pokes through (≈12%) — the "and other mixed in" the
  // user asked for.
  return h % 8 === 0 ? TILE_FOREST : TILE_GRASS;
}

/**
 * Pick the edge-ring tile id for a theme. Edge tiles surround the
 * 12×14 interior and are non-walkable in gameplay terms (the move
 * code already clamps movement to the inner cells); the visual just
 * sells the "you've zoomed into the middle of a wider area".
 */
export function edgeTileFor(themeId: number): number {
  if (themeId === TILE_SAND)   return TILE_MOUNTAIN; // rocky cliffs
  if (themeId === TILE_PATH)   return TILE_FOREST;   // hedge border
  // Grass / Forest themes — surrounding forest reads as "you're in
  // a clearing inside a wood".
  return TILE_FOREST;
}
