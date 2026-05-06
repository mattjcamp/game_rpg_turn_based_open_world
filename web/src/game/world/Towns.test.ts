/**
 * Tests for Towns parser + sprite-path normaliser.
 */

import { describe, it, expect } from "vitest";
import {
  normalizeSpritePath,
  normalizeTownTiles,
  townFromRaw,
  tileMapForTown,
  getTownByName,
  getInteriorByPath,
  resolveTownOrInterior,
  parentTownName,
} from "./Towns";

describe("normalizeSpritePath", () => {
  it("translates Python source paths to /assets/ web paths", () => {
    expect(
      normalizeSpritePath("src/assets/game/characters/cleric.png")
    ).toBe("/assets/characters/cleric.png");
  });

  it("leaves already-web paths unchanged", () => {
    expect(normalizeSpritePath("/assets/characters/cleric.png")).toBe(
      "/assets/characters/cleric.png"
    );
  });

  it("strips a leading 'src/' and the 'game/' subdir", () => {
    expect(normalizeSpritePath("src/assets/game/monsters/orc.png")).toBe(
      "/assets/monsters/orc.png"
    );
  });

  it("handles paths without the 'game/' subdir", () => {
    expect(normalizeSpritePath("src/assets/terrain/water.png")).toBe(
      "/assets/terrain/water.png"
    );
  });

  it("returns empty string for empty input", () => {
    expect(normalizeSpritePath("")).toBe("");
  });
});

describe("normalizeTownTiles", () => {
  it("expands a sparse dict into a full 2D grid, missing cells = void (36)", () => {
    const grid = normalizeTownTiles(
      {
        "0,0": { tile_id: 50 },
        "1,0": 46,
        "0,1": { tile_id: 49 },
      },
      2,
      2
    );
    expect(grid).toEqual([
      [50, 46],
      [49, 36], // missing 1,1 → void
    ]);
  });

  it("accepts a 2D-array input as-is and pads with void on short rows", () => {
    const grid = normalizeTownTiles(
      [
        [1, 2],
        [3], // short row → second cell becomes void
      ],
      2,
      2
    );
    expect(grid).toEqual([
      [1, 2],
      [3, 36],
    ]);
  });
});

describe("townFromRaw", () => {
  const sample = {
    name: "Plainstown",
    width: 2,
    height: 2,
    tiles: {
      "0,0": { tile_id: 50 },
      "1,0": { tile_id: 46 },
      "0,1": { tile_id: 49 },
      "1,1": { tile_id: 49 },
    },
    entry_col: 1,
    entry_row: 0,
    npcs: [
      {
        name: "Lonny",
        npc_type: "villager",
        sprite: "src/assets/game/characters/alchemist.png",
        col: 1,
        row: 1,
        dialogue: ["Hello, traveller."],
      },
    ],
    tile_properties: {
      "0,0": { walkable: "yes (override)" },
    },
  };

  it("parses width/height/tiles into a normalised Town", () => {
    const t = townFromRaw(sample);
    expect(t.name).toBe("Plainstown");
    expect(t.width).toBe(2);
    expect(t.height).toBe(2);
    expect(t.tiles[0][0]).toBe(50);
    expect(t.entry).toEqual({ col: 1, row: 0 });
  });

  it("normalises NPC sprite paths and wraps single-string dialogue", () => {
    const t = townFromRaw(sample);
    expect(t.npcs).toHaveLength(1);
    expect(t.npcs[0].sprite).toBe("/assets/characters/alchemist.png");
    expect(t.npcs[0].dialogue).toEqual(["Hello, traveller."]);
  });

  it("wraps a string dialogue into a one-element array", () => {
    const t = townFromRaw({
      ...sample,
      npcs: [{ ...sample.npcs[0], dialogue: "Just one line." as unknown as string[] }],
    });
    expect(t.npcs[0].dialogue).toEqual(["Just one line."]);
  });

  it("throws on missing width/height", () => {
    expect(() => townFromRaw({ name: "X", tiles: {} })).toThrow();
  });
});

describe("tileMapForTown", () => {
  it("returns a TileMap whose dimensions and tile_properties match the town", () => {
    const t = townFromRaw({
      name: "T",
      width: 2,
      height: 2,
      tiles: { "0,0": { tile_id: 50 } },
      tile_properties: { "0,0": { walkable: "no (override)" } },
    });
    const m = tileMapForTown(t);
    expect(m.width).toBe(2);
    expect(m.height).toBe(2);
    expect(m.label).toBe("T");
    // The override forces tile (0,0) blocked even though id 50 is
    // walkable per tile_defs.
    expect(m.isWalkable(0, 0)).toBe(false);
  });
});

describe("getTownByName", () => {
  it("finds a town by exact name and returns null for unknown names", () => {
    const towns = [
      townFromRaw({ name: "Plainstown", width: 1, height: 1, tiles: {} }),
      townFromRaw({ name: "Shanty Town", width: 1, height: 1, tiles: {} }),
    ];
    expect(getTownByName(towns, "Plainstown")?.name).toBe("Plainstown");
    expect(getTownByName(towns, "Nowhere")).toBeNull();
  });
});

describe("interior parsing & resolution", () => {
  // Mirrors the real towns.json shape: a town with a nested interiors[]
  // whose entries are full Town payloads.
  const raw = {
    name: "Plainstown",
    width: 4,
    height: 4,
    tiles: { "0,0": { tile_id: 50 } },
    interiors: [
      {
        name: "General Shop Interior",
        width: 4,
        height: 4,
        tiles: { "0,0": { tile_id: 49 } },
        entry_col: 2,
        entry_row: 1,
        npcs: [
          {
            name: "Brennan",
            npc_type: "shopkeep",
            sprite: "src/assets/game/characters/alchemist.png",
            col: 2,
            row: 2,
            dialogue: ["Welcome."],
          },
        ],
      },
      {
        name: "Inside House",
        width: 4,
        height: 4,
        tiles: { "0,0": { tile_id: 49 } },
      },
    ],
  };

  it("parses interiors[] into a recursive Town tree", () => {
    const t = townFromRaw(raw);
    expect(t.interiors).toHaveLength(2);
    expect(t.interiors[0].name).toBe("General Shop Interior");
    // Recursive parse means NPC sprite paths are normalised inside
    // interiors too.
    expect(t.interiors[0].npcs[0].sprite).toBe(
      "/assets/characters/alchemist.png"
    );
    expect(t.interiors[0].entry).toEqual({ col: 2, row: 1 });
  });

  it("defaults the interiors array to empty when missing", () => {
    const t = townFromRaw({
      name: "T",
      width: 1,
      height: 1,
      tiles: {},
    });
    expect(t.interiors).toEqual([]);
  });

  it("getInteriorByPath finds an interior by 'Town/Interior' path", () => {
    const towns = [townFromRaw(raw)];
    const inn = getInteriorByPath(towns, "Plainstown/Inside House");
    expect(inn?.name).toBe("Inside House");
  });

  it("getInteriorByPath returns null for unknown town or interior", () => {
    const towns = [townFromRaw(raw)];
    expect(getInteriorByPath(towns, "Nowhere/Anything")).toBeNull();
    expect(getInteriorByPath(towns, "Plainstown/Nope")).toBeNull();
    // Missing slash isn't an interior path.
    expect(getInteriorByPath(towns, "Plainstown")).toBeNull();
  });

  it("resolveTownOrInterior dispatches based on the slash", () => {
    const towns = [townFromRaw(raw)];
    expect(resolveTownOrInterior(towns, "Plainstown")?.name).toBe("Plainstown");
    expect(
      resolveTownOrInterior(towns, "Plainstown/General Shop Interior")?.name
    ).toBe("General Shop Interior");
    expect(resolveTownOrInterior(towns, "Missing")).toBeNull();
  });

  it("parentTownName extracts the town segment from interior paths", () => {
    expect(parentTownName("Plainstown/General Shop Interior")).toBe("Plainstown");
    expect(parentTownName("Plainstown")).toBeNull();
  });
});
