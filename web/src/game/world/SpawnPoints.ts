/**
 * Monster Spawn tiles — port of `data/spawn_points.json` and the
 * Python OverworldScene's spawn loop (`_spawn_from_spawn_tiles`).
 *
 * A spawn tile sits on the overworld map (TILE_SPAWN, TILE_SPAWN_CAMPFIRE,
 * TILE_SPAWN_GRAVEYARD, …). On every player step, each spawn tile within
 * a scan radius rolls its own `spawn_chance`; on success it picks a
 * monster from `spawn_monsters`, tries to drop one on an open neighbour
 * tile, and that monster joins a roaming list that pursues the party
 * one step at a time. Stepping onto the spawn tile (or being caught by
 * a roamer) starts combat against the boss list. Winning at the spawn
 * tile destroys it permanently — the tile reverts to grass and no
 * further monsters spawn from it.
 *
 * This module is the data layer + the pure helpers. The scene wires
 * them into the player loop and renders the roaming sprites.
 */

import { dataPath } from "./Module";

export interface SpawnPoint {
  /** Display name shown in the Approach Lair? prompt. */
  name: string;
  description: string;
  /** Roster the per-step roller picks from. Random uniform pick. */
  spawn_monsters: string[];
  /** Percent chance per step (1..100). Default 20. */
  spawn_chance: number;
  /** Max distance (Chebyshev) from this tile a roamer can be before
   *  the tile considers itself "saturated" and stops spawning. */
  spawn_radius: number;
  /** Hard cap on simultaneous roamers tied to this spawn tile. */
  max_spawned: number;
  /** Composition of the boss fight when the player steps on the tile. */
  boss_monsters: string[];
  xp_reward: number;
  gold_reward: number;
  loot: string[];
}

export interface RoamingMonster {
  /** Stable id — combat uses this to remove the right entry on victory. */
  id: string;
  /** Catalog name — looked up via makeMonsterByName when combat opens. */
  name: string;
  col: number;
  row: number;
  /** "col,row" of the spawn tile that bore this monster, when known. */
  sourceKey?: string;
  /** Resolved /assets/... sprite path; the scene draws this image. */
  sprite?: string;
}

interface RawSpawnPoint {
  name?: string;
  description?: string;
  spawn_monsters?: string[];
  spawn_chance?: number;
  spawn_radius?: number;
  max_spawned?: number;
  boss_monsters?: string[];
  boss_monster?: string;
  xp_reward?: number;
  gold_reward?: number;
  loot?: string[];
}

interface RawSpawnPointsFile {
  spawn_points?: Record<string, RawSpawnPoint>;
}

/** Module-scope cache; cleared by tests via `_clearSpawnPointsCache`. */
let _cache: Map<number, SpawnPoint> | null = null;

export async function loadSpawnPoints(
  url = dataPath("spawn_points.json"),
): Promise<Map<number, SpawnPoint>> {
  if (_cache) return _cache;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as RawSpawnPointsFile;
  _cache = parseSpawnPoints(raw);
  return _cache;
}

/** Parse a raw JSON blob into the typed map. Exported for tests. */
export function parseSpawnPoints(raw: RawSpawnPointsFile): Map<number, SpawnPoint> {
  const out = new Map<number, SpawnPoint>();
  const entries = raw.spawn_points ?? {};
  for (const [tidStr, sp] of Object.entries(entries)) {
    const tid = parseInt(tidStr, 10);
    if (!Number.isFinite(tid)) continue;
    // Some entries store a single boss_monster string instead of (or
    // alongside) the boss_monsters array. Honour either spelling.
    const bosses = sp.boss_monsters && sp.boss_monsters.length > 0
      ? [...sp.boss_monsters]
      : (sp.boss_monster ? [sp.boss_monster] : []);
    out.set(tid, {
      name:           sp.name ?? "Monster Spawn",
      description:    sp.description ?? "A monster lair.",
      spawn_monsters: sp.spawn_monsters ?? [],
      spawn_chance:   typeof sp.spawn_chance === "number" ? sp.spawn_chance : 20,
      spawn_radius:   typeof sp.spawn_radius === "number" ? sp.spawn_radius : 3,
      max_spawned:    typeof sp.max_spawned  === "number" ? sp.max_spawned  : 2,
      boss_monsters:  bosses,
      xp_reward:      typeof sp.xp_reward    === "number" ? sp.xp_reward    : 50,
      gold_reward:    typeof sp.gold_reward  === "number" ? sp.gold_reward  : 25,
      loot:           sp.loot ?? [],
    });
  }
  return out;
}

/** Test-only escape hatch for the module-scope cache. */
export function _clearSpawnPointsCache(): void {
  _cache = null;
}

// ── Pure helpers ───────────────────────────────────────────────────

export interface PartyPos { col: number; row: number }

/**
 * Per-step roll from a single spawn tile. Mirrors the Python
 * `_spawn_from_spawn_tiles` loop body for one tile:
 *   1. Skip if `random.randint(1, 100) > spawn_chance`.
 *   2. Skip if the count of monsters tied to this tile already meets
 *      `max_spawned` (within `spawn_radius` Chebyshev).
 *   3. Try the spawn tile itself, then the 8 neighbours, in shuffled
 *      order. Pick the first one that is walkable, not the party tile,
 *      not adjacent to the party (Manhattan > 1), and not occupied by
 *      another roamer.
 *
 * Returns the new RoamingMonster on success, or null on any skip.
 */
export function trySpawnMonster(args: {
  spawnTile: { col: number; row: number; tileId: number };
  point: SpawnPoint;
  party: PartyPos;
  existing: ReadonlyArray<RoamingMonster>;
  isWalkable: (col: number, row: number) => boolean;
  rng: () => number;
  /** id → sprite path; if missing the scene falls back to a coloured square. */
  spriteFor?: (name: string) => string | undefined;
  /** Provider for unique combatant ids. Defaults to a counter on Math.random. */
  makeId?: () => string;
}): RoamingMonster | null {
  const { spawnTile, point, party, existing, isWalkable, rng } = args;
  if (point.spawn_monsters.length === 0) return null;

  // 1. Spawn-chance roll.
  if (Math.floor(rng() * 100) + 1 > point.spawn_chance) return null;

  // 2. Cap by current population around this tile.
  const radius = point.spawn_radius;
  let nearby = 0;
  for (const m of existing) {
    if (Math.max(Math.abs(m.col - spawnTile.col),
                 Math.abs(m.row - spawnTile.row)) <= radius) {
      nearby += 1;
    }
  }
  if (nearby >= point.max_spawned) return null;

  // 3. Find an open spawn cell.
  const offsets: Array<[number, number]> = [
    [0, 0],
    [-1, 0], [1, 0], [0, -1], [0, 1],
    [-1, -1], [1, -1], [-1, 1], [1, 1],
  ];
  // Shuffle (Fisher-Yates with the supplied rng so tests are stable).
  for (let i = offsets.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = offsets[i]; offsets[i] = offsets[j]; offsets[j] = tmp;
  }

  const chosen = point.spawn_monsters[
    Math.floor(rng() * point.spawn_monsters.length)
  ];

  for (const [dc, dr] of offsets) {
    const sc = spawnTile.col + dc;
    const sr = spawnTile.row + dr;
    if (!isWalkable(sc, sr)) continue;
    if (sc === party.col && sr === party.row) continue;
    if (Math.abs(sc - party.col) + Math.abs(sr - party.row) <= 1) continue;
    if (existing.some((m) => m.col === sc && m.row === sr)) continue;
    const idMaker = args.makeId
      ?? (() => `roam-${spawnTile.col}-${spawnTile.row}-${Math.floor(rng() * 1e9)}`);
    return {
      id: idMaker(),
      name: chosen,
      col: sc, row: sr,
      sourceKey: `${spawnTile.col},${spawnTile.row}`,
      sprite: args.spriteFor ? args.spriteFor(chosen) : undefined,
    };
  }
  return null;
}

/**
 * Decide where a roaming monster should step this turn. Picks the
 * cardinal direction (N/S/E/W) that most reduces Chebyshev distance
 * to the party. Returns the new (col,row), or the same position if
 * there's no improvement (the monster sits and waits).
 *
 * Mirrors the Python overworld monster pursuit loop in spirit but
 * stays cardinal-only so the path reads cleanly on a grid.
 */
export function roamStep(
  monster: { col: number; row: number },
  party: PartyPos,
  isWalkable: (col: number, row: number) => boolean,
  blocked?: (col: number, row: number) => boolean,
): { col: number; row: number } {
  const here = { col: monster.col, row: monster.row };
  const startDist = Math.max(
    Math.abs(here.col - party.col),
    Math.abs(here.row - party.row),
  );
  if (startDist === 0) return here;
  const dirs: Array<[number, number]> = [
    [0, -1], [0, 1], [-1, 0], [1, 0],
  ];
  let best = here;
  let bestDist = startDist;
  for (const [dc, dr] of dirs) {
    const nc = here.col + dc;
    const nr = here.row + dr;
    if (!isWalkable(nc, nr)) continue;
    if (blocked && blocked(nc, nr)) continue;
    const d = Math.max(Math.abs(nc - party.col), Math.abs(nr - party.row));
    if (d < bestDist) { bestDist = d; best = { col: nc, row: nr }; }
  }
  return best;
}
