/**
 * Boat boarding / sailing / disembarking logic.
 *
 * Mirrors the Python game's `OverworldState._try_boat_move`
 * (in `src/states/overworld.py`). The party can step onto a boat
 * tile to board, then sail across water until they step onto
 * walkable land — at which point the boat stays behind on the last
 * water tile they were on and the party disembarks.
 *
 * This module is a pure decision helper; the scene owns the actual
 * sprite movement and `gameState` mutations.
 */

import { TILE_BOAT, TILE_WATER } from "./Tiles";
import type { TileMap } from "./TileMap";

export type BoatMoveOutcome =
  | { kind: "passthrough" }       // not boat-related; caller falls back to normal walking
  | { kind: "board" }             // step onto a boat tile from land — mount up
  | { kind: "sail" }              // already aboard, stepping onto water — boat moves with us
  | { kind: "disembark" }         // already aboard, stepping onto walkable land — leave boat
  | { kind: "blocked"; reason: "out_of_bounds" | "non_walkable" };

export interface BoatMoveContext {
  /** True iff the party is currently on a boat. */
  onBoat: boolean;
  /** Boats present on the map, keyed by `${col},${row}`. */
  boatPositions: ReadonlySet<string>;
}

/**
 * Decide what should happen when the party tries to step from
 * (fromCol, fromRow) to (targetCol, targetRow). Read-only — never
 * mutates the tile map or context. The caller applies the outcome.
 */
export function classifyBoatMove(
  tileMap: TileMap,
  ctx: BoatMoveContext,
  fromCol: number,
  fromRow: number,
  targetCol: number,
  targetRow: number,
): BoatMoveOutcome {
  if (!tileMap.inBounds(targetCol, targetRow)) {
    // Boarding/sailing always need a valid target. Out-of-bounds is
    // only "blocked" if we'd otherwise be doing something with a boat.
    if (ctx.onBoat) return { kind: "blocked", reason: "out_of_bounds" };
    return { kind: "passthrough" };
  }
  const targetTile = tileMap.getTile(targetCol, targetRow);
  const targetKey = `${targetCol},${targetRow}`;
  const targetHasBoat = ctx.boatPositions.has(targetKey);

  // Boarding — party is on land, walking onto a boat.
  if (!ctx.onBoat) {
    if (targetHasBoat) return { kind: "board" };
    if (targetTile === TILE_BOAT) return { kind: "board" };
    return { kind: "passthrough" };
  }

  // Already aboard — stepping back onto the same tile is a no-op.
  if (targetCol === fromCol && targetRow === fromRow) {
    return { kind: "passthrough" };
  }

  // Aboard, target has another boat → blocked. Must be checked before
  // the "water → sail" branch, since the second boat sits on a water
  // tile (boats are rendered as a sprite layer over water).
  if (targetHasBoat || targetTile === TILE_BOAT) {
    return { kind: "blocked", reason: "non_walkable" };
  }

  // Aboard, target is water → sail.
  if (targetTile === TILE_WATER) return { kind: "sail" };

  // Aboard, target is walkable land → disembark.
  if (tileMap.isWalkable(targetCol, targetRow)) {
    return { kind: "disembark" };
  }

  // Aboard, target is non-walkable, non-water (mountain in the sea, etc.).
  return { kind: "blocked", reason: "non_walkable" };
}
