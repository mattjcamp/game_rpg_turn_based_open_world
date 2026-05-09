/**
 * Procedural dungeon generator (web port).
 *
 * Mirrors `src/dungeon_generator.py` from the Python project — same
 * rooms-and-corridors algorithm, same difficulty / torch-density /
 * level-size dials so a dungeon defined in `dungeons.json` produces
 * a comparable map in the web build.
 *
 * **Algorithm.** Start with a wall-filled grid; carve rectangular
 * rooms at random positions with a 1-tile padding; connect each room
 * to the previous with an L-shaped corridor of variable width;
 * place stairs in the first room (entry) and optionally stairs-down
 * in the last; sprinkle chests and traps in the later rooms; place
 * torches against walls, then puddles + moss as cosmetic decoration.
 *
 * **Style branches** parallel the Python:
 *   - `"cave"`   — mountain walls, path-tile floors.
 *   - `"forest"` — tree walls (tile_property override forces them
 *                   non-walkable), grass-floored rooms, corridors and
 *                   edge-stair trails get rewritten to path tiles
 *                   in a post-process pass; entrance/descent stairs
 *                   sit on the map perimeter as forest archways.
 *   - default    — stone-block dungeon (TILE_DFLOOR / TILE_DWALL).
 *
 * **Persistence.** Generation is deterministic on a `seed` integer.
 * Callers seed with `(name, overworldCol, overworldRow) + level` so a
 * given dungeon entry produces the same layout every session — the
 * "generate once and save" requirement maps onto reproducible
 * regeneration plus a per-cell `tiles` grid that the cache mutates
 * in-place as the party explores (chests opened, traps triggered, etc.).
 *
 * The output `DungeonLevel` is a plain data object with no Phaser
 * dependencies so the generator stays unit-testable.
 */
import { mulberry32, type RNG, defaultRng } from "../rng";
import {
  TILE_GRASS, TILE_WATER, TILE_FOREST, TILE_MOUNTAIN, TILE_PATH, TILE_SAND,
  TILE_DFLOOR,
  TILE_DDOOR, TILE_LOCKED_DOOR,
  TILE_WALL_TORCH,
  TILE_FOREST_ARCHWAY_UP, TILE_FOREST_ARCHWAY_DOWN,
} from "./Tiles";
import { sampleEncounter, type EncounterTemplate } from "./Encounters";

// ── Tile id constants used only by the generator ─────────────────
// These mirror src/settings.py ids that aren't already exported by
// Tiles.ts. We keep them local so the public surface of Tiles.ts
// stays narrow.
export const TILE_DWALL = 21;
export const TILE_STAIRS = 22;       // up / entrance
export const TILE_CHEST = 23;
export const TILE_TRAP = 24;
export const TILE_STAIRS_DOWN = 25;
export const TILE_ARTIFACT = 27;
const TILE_PUDDLE = 32;
const TILE_MOSS = 33;

// Tiles that count as "wall" for door placement / torch adjacency.
// Forest dungeons turn trees + water into walls in addition to the
// stone-block default.
const WALL_TILES: ReadonlySet<number> = new Set([
  TILE_DWALL, TILE_MOUNTAIN, TILE_FOREST, TILE_WATER,
]);

// ── Tunable types exposed via dungeons.json ──────────────────────

export type DungeonStyle = "cave" | "forest" | "ruins" | "default";
export type Difficulty = "easy" | "normal" | "hard" | "deadly";
export type LevelSize = "small" | "medium" | "large";
export type TorchDensity = "none" | "sparse" | "moderate" | "abundant";

export interface DifficultyProfile {
  minRooms: number;
  maxRooms: number;
  /** Inclusive level band for random encounter rolls. */
  encMin: number;
  encMax: number;
  /** Per-non-entrance-room probability of rolling an encounter. */
  encChance: number;
}

const DIFFICULTY_PROFILES: Record<Difficulty, DifficultyProfile> = {
  easy:   { minRooms: 4,  maxRooms: 6,  encMin: 1, encMax: 2, encChance: 0.35 },
  normal: { minRooms: 6,  maxRooms: 10, encMin: 2, encMax: 4, encChance: 0.50 },
  hard:   { minRooms: 8,  maxRooms: 14, encMin: 3, encMax: 6, encChance: 0.65 },
  deadly: { minRooms: 10, maxRooms: 18, encMin: 5, encMax: 8, encChance: 0.80 },
};

const ENCOUNTER_LEVEL_MAX = 8;

/**
 * Resolve the difficulty profile for a (tier, floor) pair. Floor index
 * pushes the encounter band upward so a 4-floor "normal" dungeon
 * ramps F1→2..4 through F4→5..7 rather than feeling flat.
 */
export function getDifficultyProfile(
  difficulty: Difficulty | string | undefined,
  floorIdx = 0,
): DifficultyProfile {
  const tier = (difficulty as Difficulty) in DIFFICULTY_PROFILES
    ? (difficulty as Difficulty)
    : "normal";
  const base = DIFFICULTY_PROFILES[tier];
  let encMin = Math.max(1, base.encMin + floorIdx);
  const encMax = Math.min(ENCOUNTER_LEVEL_MAX, base.encMax + floorIdx);
  if (encMin > encMax) encMin = encMax;
  return {
    minRooms: base.minRooms,
    maxRooms: base.maxRooms,
    encMin,
    encMax,
    encChance: base.encChance,
  };
}

// (width, height) for each level_size category. Matches the Python
// _enter_module_dungeon mapping; the generator pads the height by
// BUFFER rows internally.
export const LEVEL_SIZES: Record<LevelSize, { width: number; height: number }> = {
  small:  { width: 30, height: 20 },
  medium: { width: 40, height: 30 },
  large:  { width: 60, height: 40 },
};

// dungeons.json torch_density values map onto the generator's
// internal { "none" | "low" | "medium" | "high" } torch dial.
const TORCH_MAP: Record<TorchDensity, "none" | "low" | "medium" | "high"> = {
  none:     "none",
  sparse:   "low",
  moderate: "medium",
  abundant: "high",
};

// ── Output shape ─────────────────────────────────────────────────

export interface DungeonMonster {
  /** Stable id used to remove this monster from the array on victory. */
  id: string;
  col: number;
  row: number;
  /** Catalog name (resolved against monsters.json). */
  name: string;
  /** Encounter roster. CombatScene receives this as monsterNames. */
  encounterNames: string[];
  /** Display name of the encounter template. */
  encounterName: string;
  /**
   * Quest this monster was placed for. Set by the dungeon's
   * quest-spawn pass for kill-step targets (e.g. Goblin's Nest's
   * "Wolves and Goblins" warbands); undefined for ordinary random
   * encounters. Used by the renderer to add a soft gold halo so the
   * player can see which sprites credit a quest, and by the spawn
   * pass to count "how many do I still owe" on re-entry.
   */
  questName?: string;
  /** Index of the kill step inside the quest definition. Combined
   *  with `questName`, this is the per-step identity used by the
   *  spawn top-up logic. */
  stepIdx?: number;
}

/**
 * One floor of a generated dungeon. The shape parallels
 * `DungeonData.to_dict()` from the Python game so a saved dungeon
 * (in a future save-to-disk) can be rebuilt without going through
 * the generator a second time.
 */
export interface DungeonLevel {
  name: string;
  width: number;
  height: number;
  /** [row][col] tile id grid. Mutated in-place as chests are opened
   *  and traps spring (matches the Python "replace tile with floor"
   *  behaviour so visited cells blend back into the map). */
  tiles: number[][];
  /** Cosmetic overlay layer (puddles, moss, wall torches). Keyed by
   *  "col,row" → tile id. Drawn on top of the base tile with a
   *  transparent sprite background. */
  decorations: Record<string, number>;
  /** Per-cell property overrides — mirrors the overworld TileMap's
   *  `tile_properties` (today: forest tree-wall walkability flips). */
  tileProperties: Record<string, { walkable?: boolean }>;
  entryCol: number;
  entryRow: number;
  style: DungeonStyle;
  monsters: DungeonMonster[];
  /** "col,row" of chests already looted. */
  openedChests: Set<string>;
  /** "col,row" of traps already triggered. */
  triggeredTraps: Set<string>;
  /** Cells the party has stepped onto / seen — drives fog of war. */
  exploredTiles: Set<string>;
  /** "col,row" of stair tiles that exit directly to the overworld
   *  rather than ascending one level (set on the bottom floor of
   *  multi-level non-forest dungeons). */
  overworldExits: Set<string>;
  /** Quest collect-item placements keyed by "col,row". Populated by
   *  DungeonScene on entry when an active quest's collect step
   *  targets this dungeon — the scene paints a TILE_ARTIFACT at the
   *  recorded coords and looks up the quest credit when the party
   *  picks it up. Cleared per artifact on pickup so re-entry
   *  doesn't respawn the item. */
  questArtifacts: Record<string, { questName: string; stepIdx: number; itemName: string }>;
}

/**
 * Floor tile id used by a level's style. Pickup code reads this when
 * restoring a tile after a chest/trap is consumed so the cell blends
 * back into the surrounding floor regardless of style.
 */
export function styleFloorTile(style: DungeonStyle | undefined): number {
  if (style === "cave") return TILE_PATH;
  if (style === "forest") return TILE_GRASS;
  return TILE_DFLOOR;
}

// ── Internal helpers ─────────────────────────────────────────────

class Room {
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
  constructor(x: number, y: number, w: number, h: number) {
    this.x = x;
    this.y = y;
    this.w = w;
    this.h = h;
  }
  get x2(): number { return this.x + this.w; }
  get y2(): number { return this.y + this.h; }
  get center(): [number, number] {
    return [this.x + Math.floor(this.w / 2), this.y + Math.floor(this.h / 2)];
  }
  intersects(other: Room, padding = 1): boolean {
    return (
      this.x - padding < other.x2 + padding &&
      this.x2 + padding > other.x - padding &&
      this.y - padding < other.y2 + padding &&
      this.y2 + padding > other.y - padding
    );
  }
}

interface Grid {
  width: number;
  height: number;
  tiles: number[][];
  decorations: Record<string, number>;
  tileProperties: Record<string, { walkable?: boolean }>;
}

function makeGrid(width: number, height: number, fill: number): Grid {
  const tiles: number[][] = [];
  for (let r = 0; r < height; r++) {
    const row: number[] = [];
    for (let c = 0; c < width; c++) row.push(fill);
    tiles.push(row);
  }
  return { width, height, tiles, decorations: {}, tileProperties: {} };
}

function getTile(g: Grid, c: number, r: number): number {
  if (c < 0 || c >= g.width || r < 0 || r >= g.height) return -1;
  return g.tiles[r][c];
}

function setTile(g: Grid, c: number, r: number, id: number): void {
  if (c < 0 || c >= g.width || r < 0 || r >= g.height) return;
  g.tiles[r][c] = id;
}

function randInt(rng: RNG, lo: number, hi: number): number {
  return Math.floor(rng() * (hi - lo + 1)) + lo;
}

function randomChoice<T>(rng: RNG, arr: T[]): T {
  return arr[Math.floor(rng() * arr.length)];
}

function shuffleInPlace<T>(rng: RNG, arr: T[]): T[] {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    const t = arr[i]; arr[i] = arr[j]; arr[j] = t;
  }
  return arr;
}

/** Weighted choice with weights `[5, 3, 1]` for widths `[1, 2, 3]` —
 *  matches the Python tunnel-width distribution. */
function tunnelWidth(rng: RNG): number {
  const r = rng() * 9;
  if (r < 5) return 1;
  if (r < 8) return 2;
  return 3;
}

function carveRoom(g: Grid, room: Room, floor: number): void {
  for (let r = room.y; r < room.y2; r++) {
    for (let c = room.x; c < room.x2; c++) {
      setTile(g, c, r, floor);
    }
  }
}

function carveHTunnel(g: Grid, x1: number, x2: number, y: number, width: number, floor: number): void {
  const half = Math.floor(width / 2);
  const lo = Math.min(x1, x2);
  const hi = Math.max(x1, x2);
  for (let c = lo; c <= hi; c++) {
    for (let dy = -half; dy < -half + width; dy++) {
      const r = y + dy;
      if (r >= 1 && r < g.height - 1) setTile(g, c, r, floor);
    }
  }
}

function carveVTunnel(g: Grid, y1: number, y2: number, x: number, width: number, floor: number): void {
  const half = Math.floor(width / 2);
  const lo = Math.min(y1, y2);
  const hi = Math.max(y1, y2);
  for (let r = lo; r <= hi; r++) {
    for (let dx = -half; dx < -half + width; dx++) {
      const c = x + dx;
      if (c >= 1 && c < g.width - 1) setTile(g, c, r, floor);
    }
  }
}

function connectRooms(g: Grid, a: Room, b: Room, rng: RNG, floor: number): void {
  const [ax, ay] = a.center;
  const [bx, by] = b.center;
  const w1 = tunnelWidth(rng);
  const w2 = tunnelWidth(rng);
  if (rng() < 0.5) {
    carveHTunnel(g, ax, bx, ay, w1, floor);
    carveVTunnel(g, ay, by, bx, w2, floor);
  } else {
    carveVTunnel(g, ay, by, ax, w1, floor);
    carveHTunnel(g, ax, bx, by, w2, floor);
  }
}

const PASSABLE_FOR_DOORS: ReadonlySet<number> = new Set([
  TILE_DFLOOR, TILE_PATH, TILE_GRASS,
  TILE_STAIRS, TILE_STAIRS_DOWN, TILE_CHEST, TILE_TRAP, TILE_ARTIFACT,
  TILE_FOREST_ARCHWAY_UP, TILE_FOREST_ARCHWAY_DOWN,
]);

/**
 * Place doors flush against walls where corridors enter rooms. A
 * wall-ring tile becomes a door if it has been carved to floor, has a
 * cardinal neighbour inside the room, and is a 1-wide opening (walls
 * on both perpendicular sides).
 */
function placeDoors(g: Grid, rooms: Room[]): void {
  const allRoomTiles = new Set<string>();
  const roomTileSets: Set<string>[] = [];
  for (const room of rooms) {
    const tiles = new Set<string>();
    for (let r = room.y; r < room.y2; r++) {
      for (let c = room.x; c < room.x2; c++) {
        const k = `${c},${r}`;
        tiles.add(k);
        allRoomTiles.add(k);
      }
    }
    roomTileSets.push(tiles);
  }
  for (let i = 0; i < rooms.length; i++) {
    const room = rooms[i];
    const tiles = roomTileSets[i];
    const ring: Array<[number, number]> = [];
    for (let c = room.x; c < room.x2; c++) {
      ring.push([c, room.y - 1]);
      ring.push([c, room.y2]);
    }
    for (let r = room.y; r < room.y2; r++) {
      ring.push([room.x - 1, r]);
      ring.push([room.x2, r]);
    }
    for (const [wc, wr] of ring) {
      const t = getTile(g, wc, wr);
      if (!PASSABLE_FOR_DOORS.has(t)) continue;
      if (allRoomTiles.has(`${wc},${wr}`)) continue;
      let connects = false;
      for (const [dc, dr] of [[0, -1], [0, 1], [-1, 0], [1, 0]] as const) {
        if (tiles.has(`${wc + dc},${wr + dr}`)) { connects = true; break; }
      }
      if (!connects) continue;
      const hWalls = WALL_TILES.has(getTile(g, wc - 1, wr)) && WALL_TILES.has(getTile(g, wc + 1, wr));
      const vWalls = WALL_TILES.has(getTile(g, wc, wr - 1)) && WALL_TILES.has(getTile(g, wc, wr + 1));
      if (hWalls || vWalls) setTile(g, wc, wr, TILE_DDOOR);
    }
  }
}

/**
 * Replace the lone door of a single-entrance room (any room except the
 * entrance room) with a locked door. Run after `placeDoors`.
 */
function placeLockedDoors(g: Grid, rooms: Room[]): void {
  for (let i = 0; i < rooms.length; i++) {
    if (i === 0) continue;
    const room = rooms[i];
    const ring: Array<[number, number]> = [];
    for (let c = room.x; c < room.x2; c++) {
      ring.push([c, room.y - 1]);
      ring.push([c, room.y2]);
    }
    for (let r = room.y; r < room.y2; r++) {
      ring.push([room.x - 1, r]);
      ring.push([room.x2, r]);
    }
    const doors = ring.filter(([c, r]) => getTile(g, c, r) === TILE_DDOOR);
    if (doors.length === 1) {
      const [dc, dr] = doors[0];
      setTile(g, dc, dr, TILE_LOCKED_DOOR);
    }
  }
}

const WALKABLE_FOR_BFS: ReadonlySet<number> = new Set([
  TILE_DFLOOR, TILE_PATH, TILE_GRASS,
  TILE_STAIRS, TILE_STAIRS_DOWN, TILE_CHEST, TILE_TRAP, TILE_ARTIFACT, TILE_DDOOR,
  TILE_FOREST_ARCHWAY_UP, TILE_FOREST_ARCHWAY_DOWN,
]);

/**
 * Iteratively unlock locked doors that disconnect rooms from the
 * entrance. Treats regular doors as walkable but locked doors as
 * impassable; any room whose center is unreachable has its locked
 * doors downgraded to regular doors. Runs to a fixpoint.
 */
function fixDisconnectedLockedDoors(g: Grid, rooms: Room[], stairsCol: number, stairsRow: number): void {
  const bfs = (sc: number, sr: number): Set<string> => {
    const visited = new Set<string>();
    const queue: Array<[number, number]> = [[sc, sr]];
    while (queue.length > 0) {
      const [c, r] = queue.shift()!;
      const k = `${c},${r}`;
      if (visited.has(k)) continue;
      if (c < 0 || c >= g.width || r < 0 || r >= g.height) continue;
      if (!WALKABLE_FOR_BFS.has(getTile(g, c, r))) continue;
      visited.add(k);
      queue.push([c - 1, r], [c + 1, r], [c, r - 1], [c, r + 1]);
    }
    return visited;
  };
  for (let pass = 0; pass < rooms.length; pass++) {
    const reachable = bfs(stairsCol, stairsRow);
    let allOk = true;
    for (const room of rooms) {
      const [cx, cy] = room.center;
      if (reachable.has(`${cx},${cy}`)) continue;
      allOk = false;
      for (let c = room.x; c < room.x2; c++) {
        for (const wr of [room.y - 1, room.y2]) {
          if (getTile(g, c, wr) === TILE_LOCKED_DOOR) setTile(g, c, wr, TILE_DDOOR);
        }
      }
      for (let r = room.y; r < room.y2; r++) {
        for (const wc of [room.x - 1, room.x2]) {
          if (getTile(g, wc, r) === TILE_LOCKED_DOOR) setTile(g, wc, r, TILE_DDOOR);
        }
      }
    }
    if (allOk) break;
  }
}

interface TorchDensityProfile {
  /** Manhattan spacing minimum between torches. */
  minSpacing: number;
  /** Cap on torch count, expressed as a multiplier of room count. */
  maxMultiplier: number;
  /** When true, also consider corridor-wall candidates (high density). */
  includeCorridors: boolean;
}

function torchProfile(d: "none" | "low" | "medium" | "high"): TorchDensityProfile {
  if (d === "none")  return { minSpacing: 999, maxMultiplier: 0,   includeCorridors: false };
  if (d === "high")  return { minSpacing: 2,   maxMultiplier: 5,   includeCorridors: true  };
  if (d === "low")   return { minSpacing: 8,   maxMultiplier: 0.5, includeCorridors: false };
  return                  { minSpacing: 4,   maxMultiplier: 2,   includeCorridors: false };
}

/**
 * Place wall torches, puddles, and moss on the decoration overlay
 * layer. Torches pick wall cells that have a floor neighbour so the
 * pool of light has somewhere to shine. Puddles and moss prefer cells
 * adjacent to walls (corridors / corners).
 */
function placeDecorations(
  g: Grid,
  rooms: Room[],
  torchDensity: "none" | "low" | "medium" | "high",
  floorTile: number,
  rng: RNG,
): void {
  const prof = torchProfile(torchDensity);
  const maxTorches = Math.floor(rooms.length * prof.maxMultiplier);

  // ── Torch candidates: wall tiles bordering a floor tile ──
  const candidates: Array<[number, number]> = [];
  const isFloor = (c: number, r: number): boolean => getTile(g, c, r) === floorTile;
  const isWall  = (c: number, r: number): boolean => WALL_TILES.has(getTile(g, c, r));
  const offsets: Array<[number, number]> = [[0, 1], [0, -1], [1, 0], [-1, 0]];
  for (const room of rooms) {
    for (let c = room.x - 1; c <= room.x + room.w; c++) {
      for (const r of [room.y - 1, room.y + room.h]) {
        if (c < 0 || c >= g.width || r < 0 || r >= g.height) continue;
        if (!isWall(c, r)) continue;
        if (offsets.some(([dx, dy]) => isFloor(c + dx, r + dy))) {
          candidates.push([c, r]);
        }
      }
    }
    for (let r = room.y - 1; r <= room.y + room.h; r++) {
      for (const c of [room.x - 1, room.x + room.w]) {
        if (c < 0 || c >= g.width || r < 0 || r >= g.height) continue;
        if (!isWall(c, r)) continue;
        if (offsets.some(([dx, dy]) => isFloor(c + dx, r + dy))) {
          candidates.push([c, r]);
        }
      }
    }
  }
  if (prof.includeCorridors) {
    for (let r = 0; r < g.height; r++) {
      for (let c = 0; c < g.width; c++) {
        if (!isWall(c, r)) continue;
        if (offsets.some(([dx, dy]) => isFloor(c + dx, r + dy))) {
          candidates.push([c, r]);
        }
      }
    }
  }

  // Dedupe and shuffle.
  const seen = new Set<string>();
  const unique: Array<[number, number]> = [];
  for (const [c, r] of candidates) {
    const k = `${c},${r}`;
    if (!seen.has(k)) { seen.add(k); unique.push([c, r]); }
  }
  shuffleInPlace(rng, unique);

  const placed: Array<[number, number]> = [];
  const isDoor = (c: number, r: number): boolean => {
    const t = getTile(g, c, r);
    return t === TILE_DDOOR || t === TILE_LOCKED_DOOR;
  };
  for (const [tc, tr] of unique) {
    if (placed.length >= maxTorches) break;
    let tooClose = false;
    for (const [pc, pr] of placed) {
      if (Math.abs(tc - pc) + Math.abs(tr - pr) < prof.minSpacing) { tooClose = true; break; }
    }
    if (tooClose) continue;
    if (offsets.some(([dx, dy]) => isDoor(tc + dx, tr + dy))) continue;
    g.decorations[`${tc},${tr}`] = TILE_WALL_TORCH;
    placed.push([tc, tr]);
  }

  // ── Puddles: small water patches on corridor / corner floors ──
  const floors: Array<[number, number]> = [];
  for (let r = 0; r < g.height; r++) {
    for (let c = 0; c < g.width; c++) {
      if (getTile(g, c, r) === floorTile) floors.push([c, r]);
    }
  }
  const numPuddles = Math.max(2, Math.floor(rooms.length / 2));
  shuffleInPlace(rng, floors);
  let puddlesPlaced = 0;
  for (const [fc, fr] of floors) {
    if (puddlesPlaced >= numPuddles) break;
    const wallCount = offsets.reduce((s, [dx, dy]) => s + (isWall(fc + dx, fr + dy) ? 1 : 0), 0);
    if (wallCount >= 1 && rng() < 0.4) {
      g.decorations[`${fc},${fr}`] = TILE_PUDDLE;
      puddlesPlaced += 1;
    }
  }

  // ── Moss: floor-adjacent-to-wall tiles, but not on top of puddles ──
  const numMoss = Math.max(3, rooms.length);
  shuffleInPlace(rng, floors);
  let mossPlaced = 0;
  for (const [fc, fr] of floors) {
    if (mossPlaced >= numMoss) break;
    if (g.decorations[`${fc},${fr}`] !== undefined) continue;
    let wallCount = 0;
    for (const [dx, dy] of offsets) {
      const nc = fc + dx, nr = fr + dy;
      if (isWall(nc, nr)) wallCount += 1;
      else if (g.decorations[`${nc},${nr}`] === TILE_WALL_TORCH) wallCount += 1;
    }
    if (wallCount >= 1 && rng() < 0.35) {
      g.decorations[`${fc},${fr}`] = TILE_MOSS;
      mossPlaced += 1;
    }
  }
}

/**
 * Place a forest archway on the named edge and carve a short trail
 * from the perimeter inward to the nearest carved cell. Returns the
 * archway position, or null if every candidate column/row failed to
 * reach a carved tile.
 */
function placeForestEdgeStairs(
  g: Grid,
  edge: "north" | "south" | "east" | "west",
  tileId: number,
  floor: number,
  wallTile: number,
  rng: RNG,
): { col: number; row: number } | null {
  const horizontal = edge === "north" || edge === "south";
  let fixedIdx: number;
  let step: number;
  if (edge === "south") { fixedIdx = g.height - 2; step = -1; }
  else if (edge === "north") { fixedIdx = 1; step = 1; }
  else if (edge === "east") { fixedIdx = g.width - 2; step = -1; }
  else { fixedIdx = 1; step = 1; }

  const sweepSize = horizontal ? g.width : g.height;
  const sweepStart = Math.max(1, Math.floor(sweepSize / 3));
  const sweepEnd = Math.min(sweepSize - 1, Math.floor((2 * sweepSize) / 3));
  const centered: number[] = [];
  for (let i = sweepStart; i < sweepEnd; i++) centered.push(i);
  const outer: number[] = [];
  for (let i = 1; i < sweepStart; i++) outer.push(i);
  for (let i = sweepEnd; i < sweepSize - 1; i++) outer.push(i);
  shuffleInPlace(rng, centered);
  shuffleInPlace(rng, outer);
  const candidates = [...centered, ...outer];

  if (horizontal) {
    for (const c of candidates) {
      let r = fixedIdx;
      while (r > 0 && r < g.height - 1) {
        if (getTile(g, c, r) !== wallTile) {
          let tr = fixedIdx;
          while (tr !== r) {
            setTile(g, c, tr, floor);
            tr += step;
          }
          setTile(g, c, fixedIdx, tileId);
          return { col: c, row: fixedIdx };
        }
        r += step;
      }
    }
  } else {
    for (const r of candidates) {
      let c = fixedIdx;
      while (c > 0 && c < g.width - 1) {
        if (getTile(g, c, r) !== wallTile) {
          let tc = fixedIdx;
          while (tc !== c) {
            setTile(g, tc, r, floor);
            tc += step;
          }
          setTile(g, fixedIdx, r, tileId);
          return { col: fixedIdx, row: r };
        }
        c += step;
      }
    }
  }
  return null;
}

/**
 * Forest-style post-process: corridor grass → path; small fraction of
 * tree walls flipped to water / mountain; sand patches in a subset of
 * rooms; tree-walls flagged non-walkable per cell so the player can't
 * stroll through woods the way they can on the overworld.
 */
function applyForestTerrain(g: Grid, rooms: Room[], rng: RNG): void {
  const roomCells = new Set<string>();
  for (const room of rooms) {
    for (let r = room.y; r < room.y2; r++) {
      for (let c = room.x; c < room.x2; c++) {
        roomCells.add(`${c},${r}`);
      }
    }
  }
  // 1. Corridor grass → path.
  for (let r = 0; r < g.height; r++) {
    for (let c = 0; c < g.width; c++) {
      if (getTile(g, c, r) === TILE_GRASS && !roomCells.has(`${c},${r}`)) {
        setTile(g, c, r, TILE_PATH);
      }
    }
  }
  // 2. Tree-wall variants — sparse so the forest still reads as forest.
  for (let r = 0; r < g.height; r++) {
    for (let c = 0; c < g.width; c++) {
      if (getTile(g, c, r) !== TILE_FOREST) continue;
      if (g.decorations[`${c},${r}`] !== undefined) continue;
      const roll = rng();
      if (roll < 0.05) setTile(g, c, r, TILE_WATER);
      else if (roll < 0.08) setTile(g, c, r, TILE_MOUNTAIN);
    }
  }
  // 3. Sand patches.
  for (const room of rooms) {
    if (room.w < 3 || room.h < 3) continue;
    if (rng() >= 0.3) continue;
    const n = randInt(rng, 1, 3);
    for (let i = 0; i < n; i++) {
      const cx = randInt(rng, room.x + 1, room.x + room.w - 2);
      const cy = randInt(rng, room.y + 1, room.y + room.h - 2);
      if (getTile(g, cx, cy) === TILE_GRASS) setTile(g, cx, cy, TILE_SAND);
    }
  }
  // 4. Tree-walls non-walkable per cell.
  for (let r = 0; r < g.height; r++) {
    for (let c = 0; c < g.width; c++) {
      if (getTile(g, c, r) === TILE_FOREST) {
        const k = `${c},${r}`;
        const entry = g.tileProperties[k] ?? {};
        entry.walkable = false;
        g.tileProperties[k] = entry;
      }
    }
  }
}

/**
 * Place a stairs-up tile in the middle of the run that exits straight
 * back to the overworld (used on the bottom floor of multi-level
 * non-forest dungeons). Returns the position or null on failure.
 */
function placeOverworldExit(
  g: Grid,
  rooms: Room[],
  floor: number,
  rng: RNG,
): { col: number; row: number } | null {
  if (rooms.length < 2) return null;
  const candidates: Room[] = rooms.length >= 3
    ? rooms.slice(1, -1)
    : [rooms[1]];
  shuffleInPlace(rng, candidates);
  for (const room of candidates) {
    for (let i = 0; i < 20; i++) {
      const cx = randInt(rng, room.x + 1, room.x + room.w - 2);
      const cy = randInt(rng, room.y + 1, room.y + room.h - 2);
      if (getTile(g, cx, cy) === floor) {
        setTile(g, cx, cy, TILE_STAIRS);
        return { col: cx, row: cy };
      }
    }
    const [cc, cr] = room.center;
    if (getTile(g, cc, cr) === floor) {
      setTile(g, cc, cr, TILE_STAIRS);
      return { col: cc, row: cr };
    }
  }
  return null;
}

// ── Public API ───────────────────────────────────────────────────

export interface GenerateLevelOptions {
  name: string;
  width: number;
  height: number;
  style: DungeonStyle;
  difficulty: Difficulty;
  /** 0-based floor index; deeper floors push the encounter band up. */
  floorIdx: number;
  /** When true, place stairs-down in the last room. */
  placeStairsDown: boolean;
  /** When true, the bottom floor of a multi-level dungeon also gets
   *  a stairs-up that exits straight to the overworld. */
  placeOverworldExit: boolean;
  /** When true, place doors at corridor entries, with single-entrance
   *  rooms upgraded to locked doors (then re-checked for connectivity). */
  placeDoors: boolean;
  /** dungeons.json torch_density value. */
  torchDensity: TorchDensity;
  /** Encounter table (loaded from encounters.json). When omitted no
   *  monsters are placed. */
  encounters?: Record<string, EncounterTemplate[]>;
  /** Encounter area key. Defaults to "dungeon". */
  encounterArea?: string;
  /** Deterministic seed. Required so dungeons regenerate identically
   *  across sessions. */
  seed: number;
}

/**
 * Generate one floor of a procedural dungeon. Pure function — output
 * depends only on `opts` and the seeded RNG. Mutated `DungeonLevel`
 * fields (openedChests, etc.) start empty.
 */
export function generateDungeonLevel(opts: GenerateLevelOptions): DungeonLevel {
  const rng = mulberry32(opts.seed);
  const { width, height, style, difficulty, floorIdx } = opts;
  const profile = getDifficultyProfile(difficulty, floorIdx);

  let wallTile: number;
  let floorTile: number;
  if (style === "cave") {
    wallTile = TILE_MOUNTAIN;
    floorTile = TILE_PATH;
  } else if (style === "forest") {
    wallTile = TILE_FOREST;
    floorTile = TILE_GRASS;
  } else {
    wallTile = TILE_DWALL;
    floorTile = TILE_DFLOOR;
  }

  // BUFFER trails the Python "extra rows for HUD visibility" trick — the
  // generator works on a slightly taller grid so corridors near the
  // bottom edge don't get clipped when the HUD bar floats over the map.
  const BUFFER = 3;
  const totalHeight = height + BUFFER;
  const grid = makeGrid(width, totalHeight, wallTile);

  // ── Carve rooms ──
  const rooms: Room[] = [];
  const numRooms = randInt(rng, profile.minRooms, profile.maxRooms);
  const maxAttempts = numRooms * 20;
  let attempts = 0;
  while (rooms.length < numRooms && attempts < maxAttempts) {
    attempts += 1;
    const w = randInt(rng, 4, 8);
    const h = randInt(rng, 4, 8);
    const x = randInt(rng, 1, width - w - 1);
    const y = randInt(rng, 1, height - h - 1);
    const room = new Room(x, y, w, h);
    if (rooms.some((other) => room.intersects(other, 1))) continue;
    carveRoom(grid, room, floorTile);
    if (rooms.length > 0) connectRooms(grid, rooms[rooms.length - 1], room, rng, floorTile);
    rooms.push(room);
  }

  // Bail-out: a malformed dimension combination could starve the room
  // sampler. Fall back to a minimal 1-room dungeon at center.
  if (rooms.length === 0) {
    const fallback = new Room(2, 2, Math.max(4, width - 4), Math.max(4, height - 4));
    carveRoom(grid, fallback, floorTile);
    rooms.push(fallback);
  }

  // ── Entrance stairs ──
  let stairsCol = 0;
  let stairsRow = 0;
  let entranceEdge: "north" | "south" | "east" | "west" | null = null;
  if (style === "forest") {
    const edges: Array<"north" | "south" | "east" | "west"> = ["north", "east", "south", "west"];
    shuffleInPlace(rng, edges);
    for (const e of edges) {
      const placed = placeForestEdgeStairs(grid, e, TILE_FOREST_ARCHWAY_UP, floorTile, wallTile, rng);
      if (placed) {
        stairsCol = placed.col;
        stairsRow = placed.row;
        entranceEdge = e;
        break;
      }
    }
  }
  if (entranceEdge === null && style !== "forest") {
    const [cc, cr] = rooms[0].center;
    stairsCol = cc;
    stairsRow = cr;
    setTile(grid, stairsCol, stairsRow, TILE_STAIRS);
  } else if (entranceEdge === null) {
    // forest fallback when every edge sweep failed
    const [cc, cr] = rooms[0].center;
    stairsCol = cc;
    stairsRow = cr;
    setTile(grid, stairsCol, stairsRow, TILE_STAIRS);
  }

  // ── Chests in the later rooms ──
  for (let i = 2; i < rooms.length; i++) {
    if (rng() < 0.6) {
      const room = rooms[i];
      const cx = room.x + randomChoice(rng, [1, room.w - 2]);
      const cy = room.y + randomChoice(rng, [1, room.h - 2]);
      if (getTile(grid, cx, cy) === floorTile) setTile(grid, cx, cy, TILE_CHEST);
    }
  }

  // ── Traps near the centre of non-entrance rooms ──
  for (let i = 1; i < rooms.length; i++) {
    if (rng() < 0.35) {
      const room = rooms[i];
      let [tx, ty] = room.center;
      tx += randInt(rng, -1, 1);
      ty += randInt(rng, -1, 1);
      if (getTile(grid, tx, ty) === floorTile) setTile(grid, tx, ty, TILE_TRAP);
    }
  }

  // ── Random encounters ──
  const monsters: DungeonMonster[] = [];
  if (opts.encounters) {
    for (let i = 1; i < rooms.length; i++) {
      if (rng() >= profile.encChance) continue;
      const room = rooms[i];
      let [mx, my] = room.center;
      mx += randInt(rng, -1, 1);
      my += randInt(rng, -1, 1);
      if (getTile(grid, mx, my) !== floorTile) continue;
      const enc = sampleEncounter(opts.encounters, opts.encounterArea ?? "dungeon", {
        minLevel: profile.encMin,
        maxLevel: profile.encMax,
        rng,
      });
      if (!enc) continue;
      monsters.push({
        id: `m-${opts.seed}-${i}`,
        col: mx,
        row: my,
        name: enc.monsterPartyTile,
        encounterNames: enc.monsters,
        encounterName: enc.name,
      });
    }
  }

  // ── Stairs down in the last room ──
  if (opts.placeStairsDown && rooms.length >= 2) {
    let placed: { col: number; row: number } | null = null;
    if (style === "forest") {
      const edges: Array<"north" | "south" | "east" | "west"> = ["north", "east", "south", "west"];
      const remaining = edges.filter((e) => e !== entranceEdge);
      shuffleInPlace(rng, remaining);
      for (const e of remaining) {
        placed = placeForestEdgeStairs(grid, e, TILE_FOREST_ARCHWAY_DOWN, floorTile, wallTile, rng);
        if (placed) break;
      }
    }
    if (!placed) {
      const [sc, sr] = rooms[rooms.length - 1].center;
      setTile(grid, sc, sr, TILE_STAIRS_DOWN);
    }
  }

  // ── Doors + locked doors + connectivity check ──
  if (opts.placeDoors) {
    placeDoors(grid, rooms);
    placeLockedDoors(grid, rooms);
  }
  fixDisconnectedLockedDoors(grid, rooms, stairsCol, stairsRow);

  // ── Decorations (overlay layer) ──
  placeDecorations(grid, rooms, TORCH_MAP[opts.torchDensity], floorTile, rng);

  // ── Optional overworld-exit stair for non-forest multi-level dungeons ──
  const overworldExits = new Set<string>();
  if (opts.placeOverworldExit && style !== "forest" && rooms.length >= 2) {
    const exit = placeOverworldExit(grid, rooms, floorTile, rng);
    if (exit) overworldExits.add(`${exit.col},${exit.row}`);
  }

  // ── Forest post-process ──
  if (style === "forest") applyForestTerrain(grid, rooms, rng);

  return {
    name: opts.name,
    width: grid.width,
    height: grid.height,
    tiles: grid.tiles,
    decorations: grid.decorations,
    tileProperties: grid.tileProperties,
    entryCol: stairsCol,
    entryRow: stairsRow,
    style,
    monsters,
    openedChests: new Set<string>(),
    triggeredTraps: new Set<string>(),
    exploredTiles: new Set<string>(),
    overworldExits,
    questArtifacts: {},
  };
}

export interface GenerateDungeonOptions {
  name: string;
  style: DungeonStyle;
  numLevels: number;
  difficulty: Difficulty;
  levelSize: LevelSize;
  torchDensity: TorchDensity;
  lockedDoors: boolean;
  /** Seeds level N as `seedBase + N` for reproducibility. */
  seedBase: number;
  /** Encounter table (loaded from encounters.json). Optional. */
  encounters?: Record<string, EncounterTemplate[]>;
}

/**
 * Generate every floor of a multi-level dungeon. Stairs-up on floor 0
 * is the entrance; stairs-down on floors 0..N-2 connect to the next
 * level; the bottom floor (N-1) of a non-forest multi-level dungeon
 * also gets an overworld-exit stair so the party can leave without
 * climbing all the way back up.
 */
export function generateDungeon(opts: GenerateDungeonOptions): DungeonLevel[] {
  const size = LEVEL_SIZES[opts.levelSize] ?? LEVEL_SIZES.medium;
  const numLevels = Math.max(1, Math.floor(opts.numLevels));
  const out: DungeonLevel[] = [];
  for (let li = 0; li < numLevels; li++) {
    const lname = numLevels > 1 ? `${opts.name} - Floor ${li + 1}` : opts.name;
    out.push(generateDungeonLevel({
      name: lname,
      width: size.width,
      height: size.height,
      style: opts.style,
      difficulty: opts.difficulty,
      floorIdx: li,
      placeStairsDown: li < numLevels - 1,
      placeOverworldExit: li === numLevels - 1 && numLevels > 1,
      placeDoors: opts.lockedDoors,
      torchDensity: opts.torchDensity,
      encounters: opts.encounters,
      encounterArea: "dungeon",
      seed: (opts.seedBase + li) >>> 0,
    }));
  }
  return out;
}

/**
 * Stable seed derived from a dungeon's identity on the overworld. Same
 * (name, col, row) → same seed, so a re-entry mid-session and a load
 * after a future save both regenerate the identical layout.
 *
 * 32-bit FNV-1a is used for the string portion so the result is
 * platform-stable (no reliance on JS engine string hashing).
 */
export function dungeonSeed(name: string, overworldCol: number, overworldRow: number): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < name.length; i++) {
    h ^= name.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  h ^= overworldCol & 0xffff;
  h = Math.imul(h, 0x01000193) >>> 0;
  h ^= overworldRow & 0xffff;
  h = Math.imul(h, 0x01000193) >>> 0;
  return h >>> 0;
}

// ── Quest monster placement ─────────────────────────────────────

/** Subset of the kill-step shape `placeQuestKillMonsters` consumes.
 *  Mirrors `Quests.activeKillStepsForLocation`'s return rows so the
 *  scene can pipe the helper's output straight in without reshaping. */
export interface QuestKillSpawnRow {
  questName: string;
  stepIdx: number;
  /** How many encounters of this step still need to be killed
   *  (`target_count - already_killed`). */
  remaining: number;
  /** Encounter template to clone — usually pulled via
   *  `Quests.rosterFor(encounterTable, step.encounter)`. */
  template: { name: string; monsters: string[]; monsterPartyTile: string };
}

/**
 * Place quest-required monsters into a multi-floor dungeon for every
 * active kill step targeting it. Mirrors `TownScene.spawnInteriorMonstersIfNeeded`
 * but for procedural dungeons.
 *
 * Distribution rule: step N drops onto floor `min(stepIdx, levels.length - 1)`,
 * so step 0 is on the entry floor, step 1 on floor 1, and so on,
 * with later steps clamped to the deepest floor. For Goblin's Nest
 * (2 floors), the "kill 3 warbands" step lands on floor 0 and the
 * "kill the war-leader" step lands on floor 1.
 *
 * Idempotent on re-entry: if an active step already has N monsters
 * placed in `level.monsters` (matched by `questName + stepIdx`), the
 * helper only tops up the missing copies. So re-entering after
 * killing one of three warbands respawns nothing — it adds the
 * remaining two only on the first entry.
 *
 * `isWalkable(col, row, levelIdx)` defers to the scene's tile-
 * walkability rules (per-cell overrides for forest tree-walls,
 * etc.). `entryByLevel` is the per-floor entry tile — we exclude it
 * so a quest monster can't spawn on top of where the player drops in.
 */
export function placeQuestKillMonsters(
  levels: DungeonLevel[],
  rows: readonly QuestKillSpawnRow[],
  isWalkable: (col: number, row: number, levelIdx: number) => boolean,
  rng: () => number = Math.random,
): void {
  if (levels.length === 0) return;
  for (const row of rows) {
    if (row.remaining <= 0) continue;
    if (!row.template.monsters.length) continue;
    const floorIdx = Math.min(row.stepIdx, levels.length - 1);
    const lvl = levels[floorIdx];
    // How many monsters for this step are already on the floor?
    const have = lvl.monsters.filter(
      (m) => m.questName === row.questName && m.stepIdx === row.stepIdx,
    ).length;
    const needed = row.remaining - have;
    if (needed <= 0) continue;
    // Build the candidate cell pool — every walkable tile that
    // isn't the entry stair and isn't already occupied by a
    // monster (random or quest).
    const occupied = new Set<string>();
    occupied.add(`${lvl.entryCol},${lvl.entryRow}`);
    for (const m of lvl.monsters) occupied.add(`${m.col},${m.row}`);
    const pool: Array<[number, number]> = [];
    for (let r = 0; r < lvl.height; r++) {
      for (let c = 0; c < lvl.width; c++) {
        if (!isWalkable(c, r, floorIdx)) continue;
        if (occupied.has(`${c},${r}`)) continue;
        pool.push([c, r]);
      }
    }
    let nextN = lvl.monsters.length;
    for (let n = 0; n < needed; n++) {
      if (pool.length === 0) break;
      const idx = Math.floor(rng() * pool.length);
      const [c, r] = pool.splice(idx, 1)[0];
      lvl.monsters.push({
        id: `q-${row.questName}-${row.stepIdx}-${nextN++}`,
        col: c,
        row: r,
        name: row.template.monsterPartyTile,
        encounterNames: [...row.template.monsters],
        encounterName: row.template.name,
        questName: row.questName,
        stepIdx: row.stepIdx,
      });
    }
  }
}
