import { describe, it, expect } from "vitest";
import { parseTileEffect, collectAnimatedTiles } from "./TileEffects";
import { TileMap } from "./TileMap";

describe("parseTileEffect", () => {
  it("returns the kind for the four supported effects", () => {
    expect(parseTileEffect("torch")).toBe("torch");
    expect(parseTileEffect("fire")).toBe("fire");
    expect(parseTileEffect("fairy_light")).toBe("fairy_light");
    expect(parseTileEffect("rising_smoke")).toBe("rising_smoke");
  });

  it("returns null for unknown / non-string / sentinel values", () => {
    expect(parseTileEffect("(none)")).toBeNull();
    expect(parseTileEffect("flood")).toBeNull();
    expect(parseTileEffect(undefined)).toBeNull();
    expect(parseTileEffect(null)).toBeNull();
    expect(parseTileEffect(42)).toBeNull();
  });
});

describe("collectAnimatedTiles", () => {
  function makeMap(props: Record<string, unknown>): TileMap {
    // 4x4 grid of tile id 0 — content doesn't matter, only properties.
    const tiles = Array.from({ length: 4 }, () => Array(4).fill(0));
    return new TileMap(4, 4, tiles, {
      tileProperties: props as Record<string, never>,
    });
  }

  it("returns the (col,row,effect) triples for animated tiles", () => {
    const m = makeMap({
      "1,1": { effect: "torch" },
      "2,3": { effect: "fairy_light" },
      "0,0": { effect: "fire" },
    });
    const tiles = collectAnimatedTiles(m);
    expect(tiles).toHaveLength(3);
    expect(tiles).toContainEqual({ col: 1, row: 1, effect: "torch" });
    expect(tiles).toContainEqual({ col: 2, row: 3, effect: "fairy_light" });
    expect(tiles).toContainEqual({ col: 0, row: 0, effect: "fire" });
  });

  it("ignores entries without a known effect", () => {
    const m = makeMap({
      "1,1": { walkable: true },
      "2,2": { effect: "(none)" },
      "3,3": { effect: "totally_made_up" },
      "0,0": { item: "Torch" }, // item-only — no effect to animate
    });
    expect(collectAnimatedTiles(m)).toEqual([]);
  });

  it("skips out-of-bounds keys and malformed coordinates", () => {
    const m = makeMap({
      "9,9": { effect: "fire" },           // out of bounds — skip
      "abc,1": { effect: "torch" },        // unparseable — skip
      "1,0": { effect: "rising_smoke" },   // valid
    });
    const tiles = collectAnimatedTiles(m);
    expect(tiles).toEqual([{ col: 1, row: 0, effect: "rising_smoke" }]);
  });
});
