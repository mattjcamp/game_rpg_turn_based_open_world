/**
 * Lighting model for the web port.
 *
 * Two sources of "this tile is a light":
 *   1. Per-cell `tile_properties[col,row].light_source: true` with
 *      optional `light_range` (string or number).
 *   2. Per-tile-id flags from `tile_defs.json` — `light_source`
 *      (e.g., wall torches) and `feature_light` (e.g., doors, altars).
 *
 * If a map carries any explicit lights it's treated as a "dark" map:
 * the renderer paints a darkness overlay over every cell, and we
 * "punch" pools of light around each source plus a small one around
 * the party. Maps without any light data stay fully bright (overworld
 * towns and the open-world map fall into this bucket).
 *
 * The visibility set is computed by simple Chebyshev (king-move)
 * distance — fast, no FOV raycasting. That matches the Python
 * INTERIOR_DARKNESS mode for towns where authors want a soft pool of
 * light per source.
 */

import type { TileMap } from "./TileMap";
import { tileDef } from "./Tiles";

export interface LightSource {
  col: number;
  row: number;
  /** Tiles of light radius (Chebyshev). */
  radius: number;
}

interface LightProps {
  light_source?: boolean | string;
  light_range?: string | number;
}

/** Default radii when the data doesn't specify one. */
const DEFAULT_LIGHT_RADIUS = 3;
const DEFAULT_FEATURE_RADIUS = 2;
/** The party always emits this much light around itself (in tiles). */
export const PARTY_LIGHT_RADIUS = 2;

function asNumber(v: unknown, fallback: number): number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = parseFloat(v);
    if (Number.isFinite(n)) return n;
  }
  return fallback;
}

function isTruthyFlag(v: unknown): boolean {
  if (v === true) return true;
  if (typeof v === "string") {
    const s = v.trim().toLowerCase();
    return s === "true" || s === "yes" || s === "yes (override)";
  }
  return false;
}

/**
 * Collect every light source on a map.
 *
 * Walks the tile_properties dict for explicit `light_source: true`
 * entries, and walks the tile grid checking each placed tile_id's
 * tile_defs flags for `light_source` / `feature_light`.
 */
export function collectLightSources(map: TileMap): LightSource[] {
  const lights: LightSource[] = [];

  // 1. Per-cell tile_properties light_source entries.
  for (const [key, raw] of Object.entries(map.tileProperties)) {
    if (!raw || typeof raw !== "object") continue;
    const props = raw as LightProps;
    if (!isTruthyFlag(props.light_source)) continue;
    const [c, r] = key.split(",").map((s) => parseInt(s, 10));
    if (!Number.isFinite(c) || !Number.isFinite(r)) continue;
    const radius = asNumber(props.light_range, DEFAULT_LIGHT_RADIUS);
    lights.push({ col: c, row: r, radius });
  }

  // 2. Per-tile-id flags from tile_defs.json — apply to every cell
  //    where that id is placed. Light sources (torches) get the full
  //    radius; "features" (doors, altars) get a smaller pool.
  for (let r = 0; r < map.height; r++) {
    for (let c = 0; c < map.width; c++) {
      const def = tileDef(map.getTile(c, r));
      const flags = def.flags;
      if (!flags) continue;
      if (flags.light_source) {
        // Skip if tile_properties already added a light at this cell;
        // otherwise we'd render two stacked pools.
        const k = `${c},${r}`;
        if (!isTruthyFlag((map.tileProperties[k] as LightProps | undefined)?.light_source)) {
          lights.push({
            col: c, row: r,
            radius: flags.light_radius ?? DEFAULT_LIGHT_RADIUS,
          });
        }
      } else if (flags.feature_light) {
        lights.push({
          col: c, row: r,
          radius: flags.feature_radius ?? DEFAULT_FEATURE_RADIUS,
        });
      }
    }
  }

  return lights;
}

/**
 * Returns true if the map should be rendered with darkness — i.e. it
 * has at least one light source. Maps without lights stay bright.
 */
export function mapIsDark(lights: LightSource[]): boolean {
  return lights.length > 0;
}

/**
 * Bresenham-walk a line from (x0, y0) to (x1, y1) and return false
 * if any **intermediate** cell satisfies `isBlocking`. The endpoints
 * themselves are exempt — a wall-mounted torch (start tile is a
 * wall) can still illuminate adjacent floor tiles, and a wall (end
 * tile) doesn't self-block when a nearby light hits it.
 *
 * Used by `brightnessAt` to enforce line-of-sight so light doesn't
 * leak through walls / locked doors / dense forest. The check is
 * direction-symmetric (LOS A→B === LOS B→A) so it's fine to walk
 * either way; we walk source → target by convention.
 */
export function hasLineOfSight(
  x0: number, y0: number,
  x1: number, y1: number,
  isBlocking: (col: number, row: number) => boolean,
): boolean {
  if (x0 === x1 && y0 === y1) return true;
  const dx = Math.abs(x1 - x0);
  const dy = Math.abs(y1 - y0);
  const sx = x0 < x1 ? 1 : -1;
  const sy = y0 < y1 ? 1 : -1;
  let err = dx - dy;
  let x = x0;
  let y = y0;
  // Walk one Bresenham step at a time. We step BEFORE checking so
  // the start tile is skipped naturally; once we land on the end
  // tile we return true without re-checking it.
  while (true) {
    const e2 = 2 * err;
    if (e2 > -dy) { err -= dy; x += sx; }
    if (e2 <  dx) { err += dx; y += sy; }
    if (x === x1 && y === y1) return true;
    if (isBlocking(x, y)) return false;
  }
}

/**
 * Compute the brightness 0..1 at a given cell.
 *
 * Each light contributes `1 - dist/radius` clamped to [0, 1] using
 * Chebyshev distance (so light pools are square-ish; matches the
 * tile-based Python overworld lights). The brightest contribution
 * wins (we don't sum them — that washes out close torches).
 *
 * The party position and party light radius are passed in; the party
 * is always treated as a light source so the player is never standing
 * in pitch black.
 *
 * `isBlocking`, when supplied, enforces line-of-sight: each light's
 * contribution is dropped when an intermediate tile blocks the
 * Bresenham line from light to target. Without it (back-compat for
 * tests that don't care), all lights illuminate radially. Apply this
 * uniformly to map lights AND the party pool — a wall between the
 * party and a tile blocks the party's own pool too, which is what
 * "respects LOS" means in conventional roguelike lighting.
 */
export function brightnessAt(
  col: number,
  row: number,
  lights: LightSource[],
  party: { col: number; row: number },
  partyRadius = PARTY_LIGHT_RADIUS,
  isBlocking?: (col: number, row: number) => boolean,
): number {
  let best = 0;
  // Party light
  const dPartyC = Math.abs(col - party.col);
  const dPartyR = Math.abs(row - party.row);
  const dParty = Math.max(dPartyC, dPartyR);
  if (dParty <= partyRadius) {
    if (!isBlocking || hasLineOfSight(party.col, party.row, col, row, isBlocking)) {
      best = Math.max(best, 1 - dParty / Math.max(partyRadius, 1));
    }
  }
  for (const L of lights) {
    const d = Math.max(Math.abs(col - L.col), Math.abs(row - L.row));
    if (d > L.radius) continue;
    if (isBlocking && !hasLineOfSight(L.col, L.row, col, row, isBlocking)) continue;
    const b = 1 - d / Math.max(L.radius, 1);
    if (b > best) best = b;
  }
  return Math.max(0, Math.min(1, best));
}

/**
 * Build an `isBlocking` callback for a `TileMap` — a tile blocks
 * light when it's non-walkable AND not flagged `transparent`.
 * That picks up walls, locked doors, and forest tree-walls (which
 * use a `tile_properties.walkable` override) while letting water
 * (already flagged transparent) pass light through normally.
 *
 * Out-of-bounds cells are treated as blockers so a light near the
 * edge of the map doesn't escape and illuminate void tiles.
 */
export function tileLightBlocker(
  map: TileMap,
): (col: number, row: number) => boolean {
  return (col, row) => {
    if (!map.inBounds(col, row)) return true;
    const def = tileDef(map.getTile(col, row));
    if (def.flags?.transparent) return false;
    return !map.isWalkable(col, row);
  };
}
