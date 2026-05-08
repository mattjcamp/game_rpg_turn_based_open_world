import { describe, it, expect } from "vitest";
import { classifyBoatMove } from "./Boats";
import { TileMap } from "./TileMap";
import { TILE_GRASS, TILE_WATER, TILE_BOAT, TILE_MOUNTAIN } from "./Tiles";

function makeMap(grid: number[][]): TileMap {
  return new TileMap(grid[0].length, grid.length, grid);
}

const G = TILE_GRASS;
const W = TILE_WATER;
const B = TILE_BOAT;
const M = TILE_MOUNTAIN;

describe("classifyBoatMove", () => {
  // 4×3 layout:
  //   row 0:  G G G G
  //   row 1:  G B W W
  //   row 2:  G G W M
  // Boat sits at (1,1), water around it, mountain at (3,2).
  const tilemap = makeMap([
    [G, G, G, G],
    [G, B, W, W],
    [G, G, W, M],
  ]);

  it("passes through when not boat-related", () => {
    const out = classifyBoatMove(
      tilemap, { onBoat: false, boatPositions: new Set() }, 0, 0, 1, 0,
    );
    expect(out.kind).toBe("passthrough");
  });

  it("boards when stepping onto a TILE_BOAT cell from land", () => {
    const out = classifyBoatMove(
      tilemap, { onBoat: false, boatPositions: new Set() }, 0, 1, 1, 1,
    );
    expect(out.kind).toBe("board");
  });

  it("boards when stepping onto a tracked boat sprite tile", () => {
    // Same scene, but the tile data has been replaced with water and
    // the boat lives in a tracked position set (the runtime layout).
    const tm = makeMap([
      [G, G, G, G],
      [G, W, W, W],
      [G, G, W, M],
    ]);
    const out = classifyBoatMove(
      tm, { onBoat: false, boatPositions: new Set(["1,1"]) }, 0, 1, 1, 1,
    );
    expect(out.kind).toBe("board");
  });

  it("sails when aboard and stepping onto water", () => {
    const out = classifyBoatMove(
      tilemap, { onBoat: true, boatPositions: new Set(["1,1"]) }, 1, 1, 2, 1,
    );
    expect(out.kind).toBe("sail");
  });

  it("disembarks when aboard and stepping onto walkable land", () => {
    const out = classifyBoatMove(
      tilemap, { onBoat: true, boatPositions: new Set(["1,1"]) }, 1, 1, 0, 1,
    );
    expect(out.kind).toBe("disembark");
  });

  it("blocks when aboard and target is non-walkable, non-water", () => {
    // Mountain at (3,2) — boat at (2,2) tries to sail east into it.
    const out = classifyBoatMove(
      tilemap, { onBoat: true, boatPositions: new Set(["2,2"]) }, 2, 2, 3, 2,
    );
    expect(out.kind).toBe("blocked");
  });

  it("blocks when aboard and target is another boat", () => {
    // Two boats at (1,1) and (2,1); aboard the first, can't sail into the second.
    const out = classifyBoatMove(
      tilemap,
      { onBoat: true, boatPositions: new Set(["1,1", "2,1"]) },
      1, 1, 2, 1,
    );
    expect(out.kind).toBe("blocked");
  });

  it("passes through out-of-bounds when not aboard", () => {
    const out = classifyBoatMove(
      tilemap, { onBoat: false, boatPositions: new Set() }, 0, 0, -1, 0,
    );
    expect(out.kind).toBe("passthrough");
  });

  it("blocks out-of-bounds while aboard", () => {
    const out = classifyBoatMove(
      tilemap, { onBoat: true, boatPositions: new Set(["1,1"]) }, 1, 1, -1, 1,
    );
    expect(out.kind).toBe("blocked");
  });
});
