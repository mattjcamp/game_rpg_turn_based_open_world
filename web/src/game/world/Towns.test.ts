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
  wanderTownNpcs,
  STATIONARY_NPC_TYPES,
  type NpcDef,
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

describe("wanderTownNpcs", () => {
  function npc(over: Partial<NpcDef> = {}): NpcDef {
    return {
      name: "X", npcType: "villager", sprite: "",
      col: 5, row: 5, homeCol: 5, homeRow: 5,
      dialogue: [], wanderRange: 2,
      ...over,
    };
  }
  // Always-walkable open arena.
  const openMap = () => true;
  // RNG that yields 0 for every call — passes the per-turn dice roll
  // (0 < 0.5) and picks index 0 on every Fisher-Yates swap, leaving
  // the dirs array in its declared order [up, down, left, right].
  const rngZero = () => 0;

  it("townFromRaw seeds homeCol/homeRow from the NPC's initial col/row", () => {
    const t = townFromRaw({
      name: "T", width: 2, height: 2, tiles: {},
      npcs: [{ name: "Pip", npc_type: "villager", col: 1, row: 0, dialogue: [] }],
    });
    expect(t.npcs[0].homeCol).toBe(1);
    expect(t.npcs[0].homeRow).toBe(0);
  });

  it("STATIONARY_NPC_TYPES includes the four Python types", () => {
    expect(STATIONARY_NPC_TYPES.has("shopkeep")).toBe(true);
    expect(STATIONARY_NPC_TYPES.has("innkeeper")).toBe(true);
    expect(STATIONARY_NPC_TYPES.has("priest")).toBe(true);
    expect(STATIONARY_NPC_TYPES.has("quest_item")).toBe(true);
    expect(STATIONARY_NPC_TYPES.has("villager")).toBe(false);
  });

  it("does not move stationary NPC types", () => {
    const npcs = [npc({ npcType: "shopkeep" }), npc({ npcType: "priest" })];
    const moved = wanderTownNpcs(npcs, 0, 0, openMap, rngZero);
    expect(moved).toEqual([]);
    expect(npcs[0].col).toBe(5);
    expect(npcs[1].col).toBe(5);
  });

  it("steps a wandering villager one cardinal tile when nothing blocks", () => {
    const npcs = [npc()];
    const moved = wanderTownNpcs(npcs, 0, 0, openMap, rngZero);
    expect(moved).toHaveLength(1);
    // With rng=0 the Fisher-Yates pass leaves dirs = [down, left, right, up];
    // first attempted dir is "down" (0,+1).
    expect(npcs[0].col).toBe(5);
    expect(npcs[0].row).toBe(6);
  });

  it("respects wanderRange — won't step past the home anchor's range", () => {
    // Range 1 with NPC already at the north edge of its leash.
    const stuck = npc({ row: 4, homeRow: 5, wanderRange: 1 });
    const npcs = [stuck];
    wanderTownNpcs(npcs, 0, 0, openMap, rngZero);
    // Up would push to row 3 (range 2 from home) — skip. Next dir
    // tried is down (row 5). That's allowed.
    expect(npcs[0].row).toBe(5);
  });

  it("won't step onto the player's tile", () => {
    const onlyPath = npc({ col: 5, row: 5, homeCol: 5, homeRow: 5 });
    const npcs = [onlyPath];
    // Player is directly above; first direction tried is up — must skip.
    wanderTownNpcs(npcs, 5, 4, openMap, rngZero);
    // Falls through to down (row 6).
    expect(npcs[0].row).toBe(6);
  });

  it("won't step onto a non-walkable tile", () => {
    const npcs = [npc()];
    // Block the entire upper row — first dir tried is up, must skip
    // and fall through to down.
    const wall = (_c: number, r: number) => r !== 4;
    wanderTownNpcs(npcs, 0, 0, wall, rngZero);
    expect(npcs[0].row).toBe(6);
  });

  it("won't pile two NPCs onto the same tile", () => {
    // A and B — A wants to step into B's tile; the collision check
    // must redirect or skip A.
    const a = npc({ name: "A", col: 5, row: 5, homeCol: 5, homeRow: 5 });
    const b = npc({ name: "B", col: 5, row: 4, homeCol: 5, homeRow: 4 });
    // rng=0 picks dir up first for each. A wants (5,4) which B holds.
    wanderTownNpcs([a, b], 0, 0, openMap, rngZero);
    // A should NOT have landed on B's tile.
    expect(a.col === b.col && a.row === b.row).toBe(false);
  });

  it("respects the per-turn dice roll — high rng skips the move entirely", () => {
    const npcs = [npc()];
    // rng() returns 0.99 ≥ 0.5 NPC_STEP_CHANCE → skip.
    wanderTownNpcs(npcs, 0, 0, openMap, () => 0.99);
    expect(npcs[0].col).toBe(5);
    expect(npcs[0].row).toBe(5);
  });
});
