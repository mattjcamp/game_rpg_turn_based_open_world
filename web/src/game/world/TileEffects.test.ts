import { describe, it, expect } from "vitest";
import {
  parseTileEffect,
  collectAnimatedTiles,
  ANIMATED_ITEM_ICONS,
} from "./TileEffects";
import { TileMap } from "./TileMap";
import type { Item } from "./Items";

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

  it("ignores entries without a known effect when no items catalog is passed", () => {
    const m = makeMap({
      "1,1": { walkable: true },
      "2,2": { effect: "(none)" },
      "3,3": { effect: "totally_made_up" },
      // item-only — without an items catalog the helper can't tell
      // what the icon is, so it stays static (Decorations renders a
      // glyph for it instead).
      "0,0": { item: "Torch" },
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

  it("animates tiles whose item resolves to icon: torch", () => {
    // The town puts wall sconces on tiles via `item: "Torch"` rather
    // than `effect: "torch"` — when the items catalog is supplied we
    // promote those tiles to the animated path so the player sees a
    // flickering flame instead of a static glyph.
    const items = new Map<string, Item>([
      ["Torch", { name: "Torch", category: "general", icon: "torch" } as Item],
      ["Healing Potion", { name: "Healing Potion", category: "general", icon: "potion" } as Item],
    ]);
    const m = makeMap({
      "1,1": { item: "Torch" },
      "2,2": { item: "Healing Potion" },  // potion isn't animated
      "3,3": { effect: "fire" },          // explicit effect still wins
    });
    const tiles = collectAnimatedTiles(m, items);
    expect(tiles).toContainEqual({ col: 1, row: 1, effect: "torch" });
    expect(tiles).toContainEqual({ col: 3, row: 3, effect: "fire" });
    // Potion should NOT be in the list — it's a static decoration.
    expect(tiles.some((t) => t.col === 2 && t.row === 2)).toBe(false);
  });

  it("explicit effect on a tile wins over its item icon", () => {
    const items = new Map<string, Item>([
      ["Torch", { name: "Torch", category: "general", icon: "torch" } as Item],
    ]);
    // Tile has both — we want the author's explicit `effect: "fire"`
    // to override the item-derived "torch" so the tile flickers as
    // a campfire, not a wall sconce.
    const m = makeMap({ "1,1": { item: "Torch", effect: "fire" } });
    expect(collectAnimatedTiles(m, items)).toEqual([
      { col: 1, row: 1, effect: "fire" },
    ]);
  });

  it("ANIMATED_ITEM_ICONS exports the icons that map to animations", () => {
    // Decorations.ts depends on this set to suppress its static glyph
    // for animated icons. Lock the contract.
    expect(ANIMATED_ITEM_ICONS.has("torch")).toBe(true);
    expect(ANIMATED_ITEM_ICONS.has("potion")).toBe(false);
  });
});
