import { describe, expect, it, afterEach } from "vitest";
import { populateRuntimeDefs, _clearRuntimeTileDefs, tileDef } from "./Tiles";
import { TileMap } from "./TileMap";
import { townFromRaw, tileMapForTown } from "./Towns";
import * as fs from "node:fs";
import * as path from "node:path";

const TILE_DEFS_PATH = path.resolve(
  __dirname,
  "../../../public/data/tile_defs.json"
);
const TOWNS_PATH = path.resolve(
  __dirname,
  "../../../public/modules/the_dragon_of_dagorn/towns.json"
);

afterEach(() => _clearRuntimeTileDefs());

describe("Plainstown General Shop Interior — counter resolution", () => {
  it("the bump tile (1,2) Armor Counter resolves to 'general' via shop_type override", () => {
    populateRuntimeDefs(JSON.parse(fs.readFileSync(TILE_DEFS_PATH, "utf-8")));
    const towns = JSON.parse(fs.readFileSync(TOWNS_PATH, "utf-8"));
    const plainstown = towns.find((t: { name: string }) => t.name === "Plainstown");
    const interior = plainstown.interiors.find(
      (i: { name: string }) => i.name === "General Shop Interior"
    );
    const town = townFromRaw(interior);
    const m = tileMapForTown(town);

    // The override path
    expect(m.getCounterKey(1, 2)).toBe("general");
    expect(m.isWalkable(1, 2)).toBe(false);

    // The tile-id default path (Counter, id 12)
    expect(m.getCounterKey(1, 3)).toBe("general");
    expect(m.isWalkable(1, 3)).toBe(false);

    // Weapon Counter, id 57 — walkable per tile_defs
    expect(m.getCounterKey(1, 1)).toBe("weapon");
    expect(m.isWalkable(1, 1)).toBe(true);

    // tile_def reads
    expect(tileDef(12).interactionType).toBe("shop");
    expect(tileDef(12).interactionData).toBe("general");
  });
});
