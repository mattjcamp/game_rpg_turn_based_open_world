/**
 * Pure placement helpers for interior + building-space quest spawns.
 *
 * TownScene calls into these on every entry to keep the spawn-pass
 * code testable without standing up Phaser. The companion tests live
 * in `InteriorSpawn.test.ts`.
 *
 * These helpers don't read or write `gameState` directly — the scene
 * passes in the existing list and gets back the new one. That keeps
 * the contract a pure (existing → next) transform that can be
 * exercised in isolation.
 */

import type { TileMap } from "./TileMap";
import type { EncounterTemplate } from "./Encounters";
import type { QuestStep } from "./Quests";
import { rosterFor } from "./Quests";
import type { InteriorMonster, InteriorQuestItem } from "../state";

/** RNG hook — defaults to `Math.random`. Tests inject a deterministic
 *  generator so a placement assertion picks a known cell. */
export type Rng = () => number;

/** Walkability + per-cell occupancy oracle. We don't take a TileMap
 *  directly because tests want to drive specific layouts without
 *  setting up the full tile_defs catalog. */
export interface WalkOracle {
  width: number;
  height: number;
  isWalkable(col: number, row: number): boolean;
}

/**
 * Flood-fill the walkable cells reachable from `(startCol, startRow)`
 * using 4-connected steps. Returns the set of `"col,row"` keys —
 * `null` when the start tile itself isn't walkable (or out of bounds),
 * which signals to callers that the supplied entry can't anchor a
 * reachability check (they should fall back to plain walkability).
 *
 * Used by the spawn pass so a quest artifact / guardian never lands in
 * a cut-off room the player can't reach. Without this, a basement with
 * a walled-off chamber could still pass the per-cell `isWalkable`
 * filter and trap the scroll behind a wall.
 */
export function reachableFrom(
  walk: WalkOracle,
  startCol: number,
  startRow: number,
): Set<string> | null {
  if (
    startCol < 0 || startCol >= walk.width ||
    startRow < 0 || startRow >= walk.height
  ) return null;
  if (!walk.isWalkable(startCol, startRow)) return null;
  const visited = new Set<string>();
  const queue: Array<[number, number]> = [[startCol, startRow]];
  visited.add(`${startCol},${startRow}`);
  while (queue.length > 0) {
    const [c, r] = queue.shift()!;
    for (const [dc, dr] of [[0, -1], [0, 1], [-1, 0], [1, 0]] as const) {
      const nc = c + dc;
      const nr = r + dr;
      if (nc < 0 || nc >= walk.width || nr < 0 || nr >= walk.height) continue;
      const k = `${nc},${nr}`;
      if (visited.has(k)) continue;
      if (!walk.isWalkable(nc, nr)) continue;
      visited.add(k);
      queue.push([nc, nr]);
    }
  }
  return visited;
}

/** Minimum context every spawn-row needs. Both kill-step rows and
 *  guardian rows funnel through `placeQuestInteriorMonsters` to
 *  share occupancy bookkeeping, so they share the input shape. */
export interface QuestKillRow {
  questName: string;
  stepIdx: number;
  /** Encounter name to look up in `encounters` for the roster + the
   *  monster_party_tile (used as the on-map sprite). */
  encounter: string;
  /** How many copies still need to be on the floor. After the spawn
   *  pass, the placed list will hold `existing.count(this row) +
   *  remaining` entries for the row, capped by walkable cells. */
  remaining: number;
  /** True for collect-step guardians (they're identified separately
   *  from kill-step monsters when topping up so a return visit
   *  doesn't double-count them). */
  isGuardian?: boolean;
}

/** Subset of TownScene state the placement pass needs. */
export interface PlacementContext {
  walk: WalkOracle;
  /** Cells the placement pass should treat as already occupied even
   *  before any prior spawns: the entry tile, every NPC home tile. */
  reserved: Iterable<readonly [number, number]>;
  /** Monsters left over from a prior visit that we should keep —
   *  also reserves their cells so we don't drop a new spawn on top. */
  existing: ReadonlyArray<InteriorMonster>;
  /** Encounter table (encounters.json) — keyed by category, but we
   *  flatten it via `rosterFor` so callers don't need to know the
   *  shape. */
  encounters: Record<string, EncounterTemplate[]>;
  rng?: Rng;
  /** Stable id-suffix counter so tests can assert id strings. Defaults
   *  to the existing.length so re-entries produce monotonically
   *  growing ids. */
  startId?: number;
  /** Optional entry tile for reachability filtering. When provided, the
   *  placement pass restricts the walkable pool to cells reachable
   *  from `(entryCol, entryRow)` — so a cut-off chamber never receives
   *  a spawn the player can't reach. Falls back to plain walkability
   *  when the entry tile itself isn't walkable (the safer of two
   *  bad options — "spawn somewhere" beats "spawn nothing"). */
  entryCol?: number;
  entryRow?: number;
}

/**
 * Top up the interior-monster list to satisfy each row's remaining
 * count. Mirrors the body of `TownScene.spawnInteriorMonstersIfNeeded`
 * — we keep both copies in sync so the scene stays a thin shell over
 * the testable helper.
 */
export function placeQuestInteriorMonsters(
  rows: ReadonlyArray<QuestKillRow>,
  ctx: PlacementContext,
): InteriorMonster[] {
  const rng = ctx.rng ?? Math.random;
  const placed: InteriorMonster[] = [...ctx.existing];
  const occupied = new Set<string>();
  for (const [c, r] of ctx.reserved) occupied.add(`${c},${r}`);
  for (const m of ctx.existing) occupied.add(`${m.col},${m.row}`);

  const reachable = ctx.entryCol !== undefined && ctx.entryRow !== undefined
    ? reachableFrom(ctx.walk, ctx.entryCol, ctx.entryRow)
    : null;
  const walkable: Array<[number, number]> = [];
  for (let r = 0; r < ctx.walk.height; r++) {
    for (let c = 0; c < ctx.walk.width; c++) {
      if (!ctx.walk.isWalkable(c, r)) continue;
      if (reachable && !reachable.has(`${c},${r}`)) continue;
      if (occupied.has(`${c},${r}`)) continue;
      walkable.push([c, r]);
    }
  }

  let nextId = ctx.startId ?? placed.length;
  for (const row of rows) {
    const tmpl = rosterFor(ctx.encounters, row.encounter);
    if (!tmpl || tmpl.monsters.length === 0) continue;
    const have = ctx.existing.filter(
      (m) =>
        m.questName === row.questName &&
        m.stepIdx === row.stepIdx &&
        Boolean(m.isGuardian) === Boolean(row.isGuardian),
    ).length;
    const needed = row.remaining - have;
    for (let n = 0; n < needed; n++) {
      if (walkable.length === 0) break;
      const idx = Math.floor(rng() * walkable.length);
      const [c, r] = walkable.splice(idx, 1)[0];
      const idPrefix = row.isGuardian ? "g" : "q";
      placed.push({
        id: `${idPrefix}-${row.questName}-${row.stepIdx}-${nextId++}`,
        col: c,
        row: r,
        name: tmpl.monsterPartyTile,
        encounterNames: [...tmpl.monsters],
        encounterName: tmpl.name,
        questName: row.questName,
        stepIdx: row.stepIdx,
        isGuardian: row.isGuardian,
      });
    }
  }
  return placed;
}

export interface QuestCollectRow {
  questName: string;
  stepIdx: number;
  step: QuestStep;
}

export interface ItemPlacementContext {
  walk: WalkOracle;
  reserved: Iterable<readonly [number, number]>;
  existing: ReadonlyArray<InteriorQuestItem>;
  /** Cells held by interior monsters — quest items shouldn't land on
   *  top of a guardian's tile (the player would walk into combat
   *  rather than picking up the artifact, so the artifact would be
   *  unreachable until the guardian moved). */
  monsterCells?: Iterable<readonly [number, number]>;
  rng?: Rng;
  startId?: number;
  /** Entry tile for reachability filtering — see PlacementContext. */
  entryCol?: number;
  entryRow?: number;
}

/**
 * Top up the interior-item list to satisfy each row's collect step.
 * One item per (quest, step) pair — duplicates are ignored. Honours
 * `step.spawnCol` / `step.spawnRow` overrides when the pinned cell
 * is walkable and unoccupied; otherwise falls back to a random
 * walkable cell.
 *
 * This is the helper the Veyron Heirloom fix hinges on — without it
 * the scroll never lands in the basement.
 */
export function placeQuestInteriorItems(
  rows: ReadonlyArray<QuestCollectRow>,
  ctx: ItemPlacementContext,
): InteriorQuestItem[] {
  const rng = ctx.rng ?? Math.random;
  const placed: InteriorQuestItem[] = [...ctx.existing];
  const occupied = new Set<string>();
  for (const [c, r] of ctx.reserved) occupied.add(`${c},${r}`);
  for (const [c, r] of ctx.monsterCells ?? []) occupied.add(`${c},${r}`);
  for (const it of ctx.existing) occupied.add(`${it.col},${it.row}`);

  const reachable = ctx.entryCol !== undefined && ctx.entryRow !== undefined
    ? reachableFrom(ctx.walk, ctx.entryCol, ctx.entryRow)
    : null;
  const walkable: Array<[number, number]> = [];
  for (let r = 0; r < ctx.walk.height; r++) {
    for (let c = 0; c < ctx.walk.width; c++) {
      if (!ctx.walk.isWalkable(c, r)) continue;
      if (reachable && !reachable.has(`${c},${r}`)) continue;
      if (occupied.has(`${c},${r}`)) continue;
      walkable.push([c, r]);
    }
  }

  let nextId = ctx.startId ?? placed.length;
  for (const row of rows) {
    const already = ctx.existing.some(
      (it) => it.questName === row.questName && it.stepIdx === row.stepIdx,
    );
    if (already) continue;

    let pos: [number, number] | null = null;
    const sc = row.step.spawnCol;
    const sr = row.step.spawnRow;
    // Pinned coords also have to be reachable — otherwise an author
    // typo could pin the artifact behind a wall the player can't get
    // to. Falls back to a random walkable+reachable cell when the pin
    // is unwalkable, occupied, or in a cut-off room.
    if (
      typeof sc === "number" && typeof sr === "number" &&
      ctx.walk.isWalkable(sc, sr) &&
      (!reachable || reachable.has(`${sc},${sr}`)) &&
      !occupied.has(`${sc},${sr}`)
    ) {
      pos = [sc, sr];
      const idx = walkable.findIndex(([c, r]) => c === sc && r === sr);
      if (idx >= 0) walkable.splice(idx, 1);
    } else if (walkable.length > 0) {
      const idx = Math.floor(rng() * walkable.length);
      pos = walkable.splice(idx, 1)[0];
    }
    if (!pos) break;

    const [c, r] = pos;
    occupied.add(`${c},${r}`);
    placed.push({
      id: `qi-${row.questName}-${row.stepIdx}-${nextId++}`,
      col: c,
      row: r,
      itemName: row.step.collectItem,
      questName: row.questName,
      stepIdx: row.stepIdx,
    });
  }
  return placed;
}

/**
 * Build a `WalkOracle` from a TileMap. Trivial wrapper, kept here so
 * TownScene doesn't have to know about the oracle shape.
 */
export function tileMapWalk(tileMap: TileMap): WalkOracle {
  return {
    width: tileMap.width,
    height: tileMap.height,
    isWalkable: (c, r) => tileMap.isWalkable(c, r),
  };
}

/**
 * If `(col, row)` is walkable (and reachable from `reachable`, when
 * provided), return it as-is. Otherwise spiral outward looking for the
 * nearest walkable cell that satisfies the same constraints, returning
 * the first hit. Returns the original coords as a last-resort fallback
 * — the caller can decide whether to render anyway.
 *
 * Used to fix authoring mistakes where an NPC / quest-giver position
 * lands on a wall or water tile (Calla in Shanty Town, Laird Marrowen
 * in the Seat of the Realm). Without this, the player would see a
 * bandit standing on a brick wall — and couldn't talk to them because
 * the bump-to-converse flow needs an adjacent walkable cell to end up
 * on.
 *
 * Search radius caps at `maxRadius` so a giver in a sealed-off region
 * doesn't trigger a whole-map scan; defaults to a conservative 8 tiles
 * which is plenty for "the author was off by one".
 */
export function snapToWalkable(
  walk: WalkOracle,
  col: number,
  row: number,
  opts: {
    reachable?: Set<string> | null;
    maxRadius?: number;
    /** Cells to treat as occupied — e.g. other NPCs already placed.
     *  Skipping them prevents two snapped NPCs from sharing a tile. */
    occupied?: Iterable<readonly [number, number]>;
  } = {},
): { col: number; row: number } {
  const reach = opts.reachable ?? null;
  const occupied = new Set<string>();
  for (const [c, r] of opts.occupied ?? []) occupied.add(`${c},${r}`);
  const acceptable = (c: number, r: number): boolean => {
    if (c < 0 || c >= walk.width || r < 0 || r >= walk.height) return false;
    if (!walk.isWalkable(c, r)) return false;
    if (reach && !reach.has(`${c},${r}`)) return false;
    if (occupied.has(`${c},${r}`)) return false;
    return true;
  };
  if (acceptable(col, row)) return { col, row };
  const maxR = opts.maxRadius ?? 8;
  for (let r = 1; r <= maxR; r++) {
    // Walk the ring at Chebyshev distance r and pick the first hit.
    // Ring iteration mirrors the Python game's nearest-empty search
    // in `_find_quest_dungeon_location`.
    for (let dc = -r; dc <= r; dc++) {
      for (let dr = -r; dr <= r; dr++) {
        if (Math.max(Math.abs(dc), Math.abs(dr)) !== r) continue;
        const nc = col + dc;
        const nr = row + dr;
        if (acceptable(nc, nr)) return { col: nc, row: nr };
      }
    }
  }
  return { col, row };
}
