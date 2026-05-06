/**
 * TileMap unit tests — bounds, walkability, and JSON parsing.
 *
 * The actual asoloth overworld is loaded at runtime via fetch, which
 * isn't available under Vitest's node environment. We test the parser
 * with a small inline payload that mimics the same shape.
 */

import { describe, it, expect } from "vitest";
import { TileMap, tileMapFromOverview } from "./TileMap";
import {
  TILE_GRASS,
  TILE_WATER,
  TILE_MOUNTAIN,
  TILE_FOREST,
  TILE_PATH,
  TILE_SPAWN_CAMPFIRE,
  isEncounterTrigger,
} from "./Tiles";

function tinyMap(): TileMap {
  // 4 cols × 3 rows:
  //   path  grass grass forest
  //   grass water mountain forest
  //   grass grass campfire grass
  return new TileMap(4, 3, [
    [TILE_PATH, TILE_GRASS, TILE_GRASS, TILE_FOREST],
    [TILE_GRASS, TILE_WATER, TILE_MOUNTAIN, TILE_FOREST],
    [TILE_GRASS, TILE_GRASS, TILE_SPAWN_CAMPFIRE, TILE_GRASS],
  ]);
}

describe("TileMap — bounds", () => {
  it("inBounds is true for valid coords and false for negative or out-of-range", () => {
    const m = tinyMap();
    expect(m.inBounds(0, 0)).toBe(true);
    expect(m.inBounds(3, 2)).toBe(true);
    expect(m.inBounds(-1, 0)).toBe(false);
    expect(m.inBounds(0, -1)).toBe(false);
    expect(m.inBounds(4, 0)).toBe(false);
    expect(m.inBounds(0, 3)).toBe(false);
  });

  it("getTile returns -1 outside the grid", () => {
    const m = tinyMap();
    expect(m.getTile(99, 99)).toBe(-1);
  });
});

describe("TileMap — walkability", () => {
  it("treats grass, forest, path, and the campfire spawn as walkable", () => {
    const m = tinyMap();
    expect(m.isWalkable(0, 0)).toBe(true); // path
    expect(m.isWalkable(1, 0)).toBe(true); // grass
    expect(m.isWalkable(3, 0)).toBe(true); // forest
    expect(m.isWalkable(2, 2)).toBe(true); // campfire
  });

  it("treats water and mountain as blocked", () => {
    const m = tinyMap();
    expect(m.isWalkable(1, 1)).toBe(false); // water
    expect(m.isWalkable(2, 1)).toBe(false); // mountain
  });

  it("treats out-of-bounds as not walkable", () => {
    const m = tinyMap();
    expect(m.isWalkable(-1, 0)).toBe(false);
    expect(m.isWalkable(0, 99)).toBe(false);
  });
});

describe("encounter triggers", () => {
  it("flags monster spawn / campfire / graveyard / explicit encounter", () => {
    expect(isEncounterTrigger(66)).toBe(true);
    expect(isEncounterTrigger(67)).toBe(true);
    expect(isEncounterTrigger(68)).toBe(true);
    expect(isEncounterTrigger(69)).toBe(true);
  });

  it("does not flag plain terrain tiles", () => {
    expect(isEncounterTrigger(TILE_GRASS)).toBe(false);
    expect(isEncounterTrigger(TILE_FOREST)).toBe(false);
    expect(isEncounterTrigger(TILE_WATER)).toBe(false);
  });
});

describe("tileMapFromOverview parser", () => {
  it("accepts the map_config shape used by the module editor", () => {
    const m = tileMapFromOverview({
      map_config: { width: 2, height: 2 },
      tiles: [
        [TILE_GRASS, TILE_WATER],
        [TILE_PATH, TILE_GRASS],
      ],
    });
    expect(m.width).toBe(2);
    expect(m.height).toBe(2);
    expect(m.getTile(1, 0)).toBe(TILE_WATER);
  });

  it("accepts the {size:{width,height}} shape used by overworld.json", () => {
    const m = tileMapFromOverview({
      size: { width: 1, height: 1 },
      tiles: [[TILE_GRASS]],
    });
    expect(m.width).toBe(1);
    expect(m.height).toBe(1);
  });

  it("rejects payloads with mismatched dimensions", () => {
    expect(() =>
      tileMapFromOverview({
        map_config: { width: 3, height: 2 },
        tiles: [[TILE_GRASS]], // wrong row count
      })
    ).toThrow();
  });

  it("rejects payloads missing the tiles array entirely", () => {
    expect(() =>
      tileMapFromOverview({ map_config: { width: 1, height: 1 } })
    ).toThrow();
  });

  it("captures party_start when present", () => {
    const m = tileMapFromOverview({
      map_config: { width: 1, height: 1 },
      tiles: [[TILE_GRASS]],
      party_start: { col: 11, row: 16 },
    });
    expect(m.partyStart).toEqual({ col: 11, row: 16 });
  });

  it("falls back to start_position when party_start is absent", () => {
    const m = tileMapFromOverview({
      size: { width: 1, height: 1 },
      tiles: [[TILE_GRASS]],
      start_position: { col: 32, row: 18 },
    });
    expect(m.partyStart).toEqual({ col: 32, row: 18 });
  });

  it("captures tile_properties verbatim", () => {
    const m = tileMapFromOverview({
      map_config: { width: 1, height: 1 },
      tiles: [[TILE_GRASS]],
      tile_properties: {
        "0,0": { walkable: "no (override)" },
      },
    });
    expect(m.tileProperties["0,0"]).toEqual({ walkable: "no (override)" });
  });
});

// ── Walkability overrides ────────────────────────────────────────────

describe("TileMap — walkability overrides", () => {
  it("'yes (override)' on a normally-blocked tile makes it walkable", () => {
    const m = new TileMap(1, 1, [[TILE_WATER]], {
      tileProperties: { "0,0": { walkable: "yes (override)" } },
    });
    expect(m.isWalkable(0, 0)).toBe(true);
  });

  it("'no (override)' on a normally-walkable tile blocks it", () => {
    const m = new TileMap(1, 1, [[TILE_GRASS]], {
      tileProperties: { "0,0": { walkable: "no (override)" } },
    });
    expect(m.isWalkable(0, 0)).toBe(false);
  });

  it("boolean true/false overrides work the same as the (override) strings", () => {
    const blocked = new TileMap(1, 1, [[TILE_GRASS]], {
      tileProperties: { "0,0": { walkable: false } },
    });
    expect(blocked.isWalkable(0, 0)).toBe(false);
    const opened = new TileMap(1, 1, [[TILE_WATER]], {
      tileProperties: { "0,0": { walkable: true } },
    });
    expect(opened.isWalkable(0, 0)).toBe(true);
  });

  it("'inherit (yes)' / 'inherit (no)' defer to the tile-id default", () => {
    const grass = new TileMap(1, 1, [[TILE_GRASS]], {
      tileProperties: { "0,0": { walkable: "inherit (yes)" } },
    });
    expect(grass.isWalkable(0, 0)).toBe(true); // grass default is walkable
    const water = new TileMap(1, 1, [[TILE_WATER]], {
      tileProperties: { "0,0": { walkable: "inherit (no)" } },
    });
    expect(water.isWalkable(0, 0)).toBe(false); // water default is blocked
  });
});

// ── Tile linking ─────────────────────────────────────────────────────

describe("TileMap — getTileLink", () => {
  it("returns null for tiles without any link metadata", () => {
    const m = new TileMap(1, 1, [[TILE_GRASS]]);
    expect(m.getTileLink(0, 0)).toBeNull();
  });

  it("parses 'town:Plainstown' into kind + name + numeric coords", () => {
    const m = new TileMap(2, 2, [
      [TILE_GRASS, TILE_GRASS],
      [TILE_GRASS, TILE_GRASS],
    ], {
      tileProperties: {
        "1,0": {
          linked: true,
          link_map: "town:Plainstown",
          link_x: "11",
          link_y: "2",
        },
      },
    });
    expect(m.getTileLink(1, 0)).toEqual({
      kind: "town",
      name: "Plainstown",
      x: 11,
      y: 2,
    });
  });

  it("handles dungeon links without coords", () => {
    const m = new TileMap(1, 1, [[TILE_GRASS]], {
      tileProperties: {
        "0,0": { linked: true, link_map: "dungeon:Goblin's Nest" },
      },
    });
    expect(m.getTileLink(0, 0)).toEqual({
      kind: "dungeon",
      name: "Goblin's Nest",
      x: undefined,
      y: undefined,
    });
  });

  it("ignores property entries that have no link_map", () => {
    const m = new TileMap(1, 1, [[TILE_GRASS]], {
      tileProperties: { "0,0": { walkable: "yes (override)" } },
    });
    expect(m.getTileLink(0, 0)).toBeNull();
  });

  it("parses bare 'overworld' (no colon, no name) — used by town exit tiles", () => {
    // The town editor writes `link_map: "overworld"` on the gate tile;
    // there's no name because the overworld is unique. The parser must
    // still return a link with kind === "overworld" so TownScene's
    // exit check can fire.
    const m = new TileMap(1, 1, [[TILE_GRASS]], {
      tileProperties: {
        "0,0": {
          linked: true,
          link_map: "overworld",
          link_x: "10",
          link_y: "14",
        },
      },
    });
    const link = m.getTileLink(0, 0);
    expect(link).not.toBeNull();
    expect(link?.kind).toBe("overworld");
    expect(link?.name).toBe("");
    expect(link?.x).toBe(10);
    expect(link?.y).toBe(14);
  });
});
