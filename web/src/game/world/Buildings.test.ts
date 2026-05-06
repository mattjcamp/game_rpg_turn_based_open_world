import { describe, it, expect } from "vitest";
import {
  buildingFromRaw,
  buildingPath,
  parseBuildingPath,
  getBuildingByName,
  getBuildingSpace,
} from "./Buildings";

describe("buildingPath / parseBuildingPath", () => {
  it("round-trips a building+space path", () => {
    const p = buildingPath("Sea Shrine", "Main Hall");
    expect(p).toBe("building:Sea Shrine:Main Hall");
    expect(parseBuildingPath(p)).toEqual({ building: "Sea Shrine", space: "Main Hall" });
  });

  it("supports building-only paths (no space)", () => {
    const p = buildingPath("Abandoned Building");
    expect(p).toBe("building:Abandoned Building");
    expect(parseBuildingPath(p)).toEqual({ building: "Abandoned Building", space: null });
  });

  it("returns null for paths that aren't buildings", () => {
    expect(parseBuildingPath("Plainstown")).toBeNull();
    expect(parseBuildingPath("town:Plainstown")).toBeNull();
    expect(parseBuildingPath("Plainstown/General Shop")).toBeNull();
  });

  it("preserves colons in space names beyond the first", () => {
    // Treat the first colon as the building/space separator. Anything
    // after that is the space name (Python editor allows colons in
    // space names — rare but possible).
    expect(parseBuildingPath("building:Sea Shrine:Citadel 2")).toEqual({
      building: "Sea Shrine", space: "Citadel 2",
    });
  });
});

describe("buildingFromRaw", () => {
  const raw = {
    name: "Abandoned Building",
    description: "A merchant's house gone derelict.",
    spaces: [
      {
        name: "Main Hall",
        width: 4, height: 4,
        tiles: { "0,0": { tile_id: 47 } },
        entry_col: 1, entry_row: 1,
        npcs: [],
        tile_properties: {
          "0,12": {
            walkable: "inherit (yes)",
            linked: true,
            link_map: "building:Abandoned Building:Basement",
            link_x: "8", link_y: "1",
          },
        },
      },
      {
        name: "Basement",
        width: 4, height: 4,
        tiles: { "0,0": { tile_id: 3 } },
      },
    ],
  };

  it("parses each space into a Town-shaped object with buildingName attached", () => {
    const b = buildingFromRaw(raw);
    expect(b.name).toBe("Abandoned Building");
    expect(b.spaces).toHaveLength(2);
    expect(b.spaces[0].name).toBe("Main Hall");
    expect(b.spaces[0].buildingName).toBe("Abandoned Building");
    expect(b.spaces[0].entry).toEqual({ col: 1, row: 1 });
    // tile_properties pass through verbatim — TileMap reads the
    // walkable / linked / link_map fields from there.
    expect(b.spaces[0].tileProperties["0,12"]).toMatchObject({
      link_map: "building:Abandoned Building:Basement",
    });
  });
});

describe("getBuildingSpace", () => {
  const buildings = [
    buildingFromRaw({
      name: "Sea Shrine", description: "",
      spaces: [
        { name: "Main Hall", width: 1, height: 1, tiles: {} },
        { name: "Citadel 2", width: 1, height: 1, tiles: {} },
        { name: "Citadel 3", width: 1, height: 1, tiles: {} },
      ],
    }),
    buildingFromRaw({
      name: "Abandoned Building", description: "",
      spaces: [
        { name: "Main Hall", width: 1, height: 1, tiles: {} },
        { name: "Basement", width: 1, height: 1, tiles: {} },
      ],
    }),
  ];

  it("looks up an explicit Building:Space reference", () => {
    expect(getBuildingSpace(buildings, "Sea Shrine:Citadel 2")?.name).toBe("Citadel 2");
  });

  it("falls back to the first space when the ref omits the space", () => {
    expect(getBuildingSpace(buildings, "Abandoned Building")?.name).toBe("Main Hall");
  });

  it("returns null for unknown buildings or unknown spaces", () => {
    expect(getBuildingSpace(buildings, "Nowhere")).toBeNull();
    expect(getBuildingSpace(buildings, "Sea Shrine:Cellar")).toBeNull();
  });

  it("getBuildingByName finds a building or returns null", () => {
    expect(getBuildingByName(buildings, "Sea Shrine")?.spaces).toHaveLength(3);
    expect(getBuildingByName(buildings, "Nope")).toBeNull();
  });
});
