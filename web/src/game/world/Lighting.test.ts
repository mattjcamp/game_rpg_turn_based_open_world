/**
 * Tests for the lighting collector + brightness helper.
 */

import { describe, it, expect } from "vitest";
import { TileMap } from "./TileMap";
import {
  collectLightSources,
  brightnessAt,
  mapIsDark,
} from "./Lighting";
import { TILE_GRASS } from "./Tiles";

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
