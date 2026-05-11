/**
 * Tests for the lighting collector + brightness helper.
 */

import { describe, it, expect } from "vitest";
import { TileMap } from "./TileMap";
import {
  collectLightSources,
  brightnessAt,
  hasLineOfSight,
  mapIsDark,
  tileLightBlocker,
} from "./Lighting";
import { TILE_GRASS, TILE_MOUNTAIN } from "./Tiles";

function blank(w = 5, h = 5): TileMap {
  const tiles = Array.from({ length: h }, () =>
    Array.from({ length: w }, () => TILE_GRASS)
  );
  return new TileMap(w, h, tiles);
}

describe("collectLightSources", () => {
  it("returns no lights for a map without any light data", () => {
    const m = blank();
    expect(collectLightSources(m)).toEqual([]);
    expect(mapIsDark(collectLightSources(m))).toBe(false);
  });

  it("picks up tile_properties light_source entries with default radius", () => {
    const m = new TileMap(3, 3, [
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 0],
    ], {
      tileProperties: {
        "1,1": { light_source: true },
      },
    });
    const lights = collectLightSources(m);
    expect(lights).toHaveLength(1);
    expect(lights[0]).toMatchObject({ col: 1, row: 1 });
    expect(lights[0].radius).toBeGreaterThan(0);
  });

  it("respects an explicit light_range, accepting both number and string", () => {
    const m = new TileMap(3, 3, [
      [0, 0, 0], [0, 0, 0], [0, 0, 0],
    ], {
      tileProperties: {
        "0,0": { light_source: true, light_range: "5" },
        "2,2": { light_source: true, light_range: 7 },
      },
    });
    const lights = collectLightSources(m);
    const byPos = Object.fromEntries(lights.map(L => [`${L.col},${L.row}`, L.radius]));
    expect(byPos["0,0"]).toBe(5);
    expect(byPos["2,2"]).toBe(7);
  });

  it("ignores light_source: false / undefined", () => {
    const m = new TileMap(2, 2, [[0,0],[0,0]], {
      tileProperties: { "0,0": { light_source: false }, "1,1": {} },
    });
    expect(collectLightSources(m)).toEqual([]);
  });
});

describe("brightnessAt", () => {
  const party = { col: 0, row: 0 };

  it("returns 1.0 at the party tile (party light)", () => {
    expect(brightnessAt(0, 0, [], party, 3)).toBeCloseTo(1.0);
  });

  it("falls off linearly with Chebyshev distance from a light", () => {
    const lights = [{ col: 5, row: 5, radius: 4 }];
    const farParty = { col: 100, row: 100 };
    expect(brightnessAt(5, 5, lights, farParty)).toBeCloseTo(1.0);
    expect(brightnessAt(6, 5, lights, farParty)).toBeCloseTo(0.75);
    expect(brightnessAt(7, 5, lights, farParty)).toBeCloseTo(0.5);
    expect(brightnessAt(9, 5, lights, farParty)).toBeCloseTo(0.0);
    expect(brightnessAt(10, 5, lights, farParty)).toBe(0);
  });

  it("uses Chebyshev (king) distance — diagonals count as 1 step", () => {
    const lights = [{ col: 0, row: 0, radius: 2 }];
    const farParty = { col: 100, row: 100 };
    expect(brightnessAt(2, 2, lights, farParty)).toBeCloseTo(0.0);
    // 1 diagonal step away → bright
    expect(brightnessAt(1, 1, lights, farParty)).toBeCloseTo(0.5);
  });

  it("returns the brightest light's value when multiple lights overlap", () => {
    const lights = [
      { col: 0, row: 0, radius: 2 },
      { col: 5, row: 5, radius: 5 }, // bigger, brighter at a distance
    ];
    const farParty = { col: 100, row: 100 };
    // Standing on the second light → 1.0 even though far from first.
    expect(brightnessAt(5, 5, lights, farParty)).toBeCloseTo(1.0);
  });
});

describe("hasLineOfSight", () => {
  const NEVER_BLOCKS = (): boolean => false;
  const ALWAYS_BLOCKS = (): boolean => true;

  it("returns true for the same tile", () => {
    expect(hasLineOfSight(3, 3, 3, 3, NEVER_BLOCKS)).toBe(true);
  });

  it("returns true for adjacent tiles regardless of the blocker", () => {
    // Adjacent — there are no intermediate cells to block.
    expect(hasLineOfSight(0, 0, 1, 0, ALWAYS_BLOCKS)).toBe(true);
    expect(hasLineOfSight(0, 0, 1, 1, ALWAYS_BLOCKS)).toBe(true);
    expect(hasLineOfSight(0, 0, 0, 1, ALWAYS_BLOCKS)).toBe(true);
  });

  it("returns false when an intermediate tile blocks", () => {
    // Walk (0,0) → (4,0). One blocker at (2,0).
    const blocker = (c: number, r: number): boolean => c === 2 && r === 0;
    expect(hasLineOfSight(0, 0, 4, 0, blocker)).toBe(false);
  });

  it("the start tile is exempt from blocking (wall-mounted torch case)", () => {
    // The torch sits on a wall at (0,0). Light should still reach
    // the floor at (2,0) even though the start tile would say block.
    const blocker = (c: number, r: number): boolean => c === 0 && r === 0;
    expect(hasLineOfSight(0, 0, 2, 0, blocker)).toBe(true);
  });

  it("the end tile is exempt from blocking (wall lit by adjacent torch)", () => {
    // Floor torch at (0,0), wall at (3,0). The wall itself shouldn't
    // self-block — the player should see the wall lit when adjacent.
    const blocker = (c: number, r: number): boolean => c === 3 && r === 0;
    expect(hasLineOfSight(0, 0, 3, 0, blocker)).toBe(true);
  });

  it("works on diagonals — Bresenham steps both axes", () => {
    // Diagonal from (0,0) → (4,4). One blocker at (2,2).
    const blocker = (c: number, r: number): boolean => c === 2 && r === 2;
    expect(hasLineOfSight(0, 0, 4, 4, blocker)).toBe(false);
  });
});

describe("tileLightBlocker", () => {
  it("treats walkable tiles as non-blocking", () => {
    const m = new TileMap(3, 3, [
      [TILE_GRASS, TILE_GRASS, TILE_GRASS],
      [TILE_GRASS, TILE_GRASS, TILE_GRASS],
      [TILE_GRASS, TILE_GRASS, TILE_GRASS],
    ]);
    const blocks = tileLightBlocker(m);
    expect(blocks(1, 1)).toBe(false);
  });

  it("treats non-walkable tiles as blocking", () => {
    const m = new TileMap(3, 3, [
      [TILE_GRASS, TILE_MOUNTAIN, TILE_GRASS],
      [TILE_GRASS, TILE_GRASS, TILE_GRASS],
      [TILE_GRASS, TILE_GRASS, TILE_GRASS],
    ]);
    const blocks = tileLightBlocker(m);
    expect(blocks(1, 0)).toBe(true);
  });

  it("treats out-of-bounds as blocking (light can't escape the map)", () => {
    const m = new TileMap(2, 2, [[TILE_GRASS, TILE_GRASS], [TILE_GRASS, TILE_GRASS]]);
    const blocks = tileLightBlocker(m);
    expect(blocks(-1, 0)).toBe(true);
    expect(blocks(0, -1)).toBe(true);
    expect(blocks(2, 0)).toBe(true);
    expect(blocks(0, 2)).toBe(true);
  });
});

describe("brightnessAt with LOS", () => {
  it("a light contributes nothing when blocked by an intermediate wall", () => {
    // Light at (0, 0) radius 4. Target at (4, 0). Wall at (2, 0).
    const lights = [{ col: 0, row: 0, radius: 4 }];
    const farParty = { col: 100, row: 100 };
    const blocker = (c: number, r: number): boolean => c === 2 && r === 0;
    // Without LOS: light reaches with brightness 1 - 4/4 = 0.
    // Actually 1 - 4/4 = 0, so use radius=8 to test mid-pool blocking.
    const lights2 = [{ col: 0, row: 0, radius: 8 }];
    expect(brightnessAt(4, 0, lights2, farParty, 0, blocker)).toBe(0);
    expect(brightnessAt(4, 0, lights2, farParty)).toBeGreaterThan(0);
    void lights;
  });

  it("party light is also LOS-gated", () => {
    // Party at (0, 0), target at (4, 0), wall at (2, 0).
    const blocker = (c: number, r: number): boolean => c === 2 && r === 0;
    expect(brightnessAt(4, 0, [], { col: 0, row: 0 }, 6, blocker)).toBe(0);
    expect(brightnessAt(4, 0, [], { col: 0, row: 0 }, 6)).toBeGreaterThan(0);
  });

  it("a wall-mounted torch still illuminates the wall and adjacent floor", () => {
    // Torch on a wall at (0, 0). Wall counts as the source — exempt
    // from its own blocking. Adjacent floor tile gets lit.
    const torch = [{ col: 0, row: 0, radius: 3 }];
    const farParty = { col: 100, row: 100 };
    const blocker = (c: number, r: number): boolean => c === 0 && r === 0;
    expect(brightnessAt(1, 0, torch, farParty, 0, blocker)).toBeGreaterThan(0);
  });

  it("an unblocked light contributes the same with or without LOS", () => {
    const torch = [{ col: 0, row: 0, radius: 4 }];
    const farParty = { col: 100, row: 100 };
    const noBlock = (): boolean => false;
    const a = brightnessAt(2, 0, torch, farParty);
    const b = brightnessAt(2, 0, torch, farParty, undefined, noBlock);
    expect(a).toBeCloseTo(b);
  });

  it("a torch in a sealed-off chamber doesn't light up cells the party can't see", () => {
    // Layout: party at (0, 0). Wall at (5, 0) blocks sight of cell
    // (6, 0). A torch sits at (6, 0) lighting (7, 0) within its own
    // chamber. The party→cell LOS gate should drop the torch's
    // contribution to (7, 0) — without the gate, the torch's pool
    // would brighten (7, 0) and the player would see the chamber
    // through stone walls.
    const torch = [{ col: 6, row: 0, radius: 3 }];
    const party = { col: 0, row: 0 };
    const blocker = (c: number, r: number): boolean => c === 5 && r === 0;
    expect(brightnessAt(7, 0, torch, party, 0, blocker)).toBe(0);
    // Sanity: without the wall, the same torch DOES brighten (7, 0).
    const noBlock = (): boolean => false;
    expect(brightnessAt(7, 0, torch, party, 0, noBlock)).toBeGreaterThan(0);
  });

  it("a torch the party CAN see still contributes (LOS gate is symmetric)", () => {
    // Open corridor — no wall between party and torch. Even though
    // the cell is far from the party's own light pool, the torch's
    // contribution lands because party→cell LOS is clear.
    const torch = [{ col: 4, row: 0, radius: 3 }];
    const party = { col: 0, row: 0 };
    const noBlock = (): boolean => false;
    expect(brightnessAt(5, 0, torch, party, 0, noBlock)).toBeGreaterThan(0);
  });
});
