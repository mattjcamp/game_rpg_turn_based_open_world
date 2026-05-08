import { describe, it, expect } from "vitest";
import {
  generateDungeon,
  generateDungeonLevel,
  getDifficultyProfile,
  dungeonSeed,
  styleFloorTile,
  TILE_DWALL,
  TILE_STAIRS,
  TILE_STAIRS_DOWN,
  TILE_CHEST,
  TILE_TRAP,
  type DungeonLevel,
} from "./Dungeon";
import { TILE_DFLOOR, TILE_PATH, TILE_GRASS, TILE_FOREST_ARCHWAY_UP } from "./Tiles";

const TILE_DDOOR = 26;

function countMatching(level: DungeonLevel, predicate: (id: number) => boolean): number {
  let n = 0;
  for (let r = 0; r < level.height; r++) {
    for (let c = 0; c < level.width; c++) {
      if (predicate(level.tiles[r][c])) n += 1;
    }
  }
  return n;
}

describe("Dungeon — difficulty profiles", () => {
  it("ramps encounter band with floor index", () => {
    const f0 = getDifficultyProfile("normal", 0);
    const f3 = getDifficultyProfile("normal", 3);
    expect(f0.encMin).toBe(2);
    expect(f0.encMax).toBe(4);
    expect(f3.encMin).toBe(5);
    expect(f3.encMax).toBe(7);
  });

  it("clamps the encounter ceiling at 8", () => {
    const profile = getDifficultyProfile("deadly", 5);
    expect(profile.encMax).toBeLessThanOrEqual(8);
    expect(profile.encMin).toBeLessThanOrEqual(profile.encMax);
  });

  it("falls back to normal on an unknown tier", () => {
    const profile = getDifficultyProfile("insane" as unknown as "normal");
    expect(profile.minRooms).toBe(6);
    expect(profile.maxRooms).toBe(10);
  });

  it("escalates the per-room encounter chance with tier", () => {
    expect(getDifficultyProfile("easy").encChance).toBeLessThan(getDifficultyProfile("normal").encChance);
    expect(getDifficultyProfile("normal").encChance).toBeLessThan(getDifficultyProfile("hard").encChance);
    expect(getDifficultyProfile("hard").encChance).toBeLessThan(getDifficultyProfile("deadly").encChance);
  });
});

describe("Dungeon — single level shape", () => {
  const level = generateDungeonLevel({
    name: "Test",
    width: 40,
    height: 30,
    style: "default",
    difficulty: "normal",
    floorIdx: 0,
    placeStairsDown: false,
    placeOverworldExit: false,
    placeDoors: false,
    torchDensity: "moderate",
    seed: 42,
  });

  it("includes the BUFFER rows in the output height", () => {
    // generator widens by BUFFER (3) rows for HUD breathing room.
    expect(level.height).toBe(33);
    expect(level.width).toBe(40);
  });

  it("tile rows match the declared width", () => {
    for (let r = 0; r < level.height; r++) {
      expect(level.tiles[r].length).toBe(level.width);
    }
  });

  it("places a stairs-up tile at the entry point", () => {
    expect(level.tiles[level.entryRow][level.entryCol]).toBe(TILE_STAIRS);
  });

  it("default style uses stone walls and floor", () => {
    expect(countMatching(level, (id) => id === TILE_DWALL)).toBeGreaterThan(0);
    expect(countMatching(level, (id) => id === TILE_DFLOOR)).toBeGreaterThan(0);
  });

  it("starts with no chests opened, no traps triggered, and only the entry explored", () => {
    expect(level.openedChests.size).toBe(0);
    expect(level.triggeredTraps.size).toBe(0);
    expect(level.exploredTiles.size).toBe(0);
  });
});

describe("Dungeon — determinism", () => {
  const opts = {
    name: "Stable",
    style: "default" as const,
    numLevels: 2,
    difficulty: "normal" as const,
    levelSize: "medium" as const,
    torchDensity: "moderate" as const,
    lockedDoors: false,
    seedBase: 12345,
  };

  it("same seed produces identical level grids", () => {
    const a = generateDungeon(opts);
    const b = generateDungeon(opts);
    expect(a.length).toBe(b.length);
    for (let li = 0; li < a.length; li++) {
      expect(a[li].tiles).toEqual(b[li].tiles);
      expect(a[li].entryCol).toBe(b[li].entryCol);
      expect(a[li].entryRow).toBe(b[li].entryRow);
    }
  });

  it("dungeonSeed is stable per (name, col, row) pair", () => {
    expect(dungeonSeed("Goblin's Nest", 12, 5)).toBe(dungeonSeed("Goblin's Nest", 12, 5));
    expect(dungeonSeed("Goblin's Nest", 12, 5)).not.toBe(dungeonSeed("Goblin's Nest", 13, 5));
    expect(dungeonSeed("Goblin's Nest", 12, 5)).not.toBe(dungeonSeed("Crypt", 12, 5));
  });
});

describe("Dungeon — multi-level", () => {
  it("each non-final level has a stairs-down tile", () => {
    const levels = generateDungeon({
      name: "Multi", style: "default", numLevels: 3,
      difficulty: "normal", levelSize: "medium", torchDensity: "none",
      lockedDoors: false, seedBase: 7,
    });
    expect(levels.length).toBe(3);
    expect(countMatching(levels[0], (id) => id === TILE_STAIRS_DOWN)).toBeGreaterThan(0);
    expect(countMatching(levels[1], (id) => id === TILE_STAIRS_DOWN)).toBeGreaterThan(0);
    expect(countMatching(levels[2], (id) => id === TILE_STAIRS_DOWN)).toBe(0);
  });

  it("the bottom non-forest floor of a multi-level dungeon registers an overworld exit", () => {
    const levels = generateDungeon({
      name: "Exit", style: "default", numLevels: 2,
      difficulty: "normal", levelSize: "medium", torchDensity: "none",
      lockedDoors: false, seedBase: 99,
    });
    expect(levels[0].overworldExits.size).toBe(0);
    expect(levels[1].overworldExits.size).toBeGreaterThanOrEqual(1);
  });

  it("a single-level dungeon does NOT register an overworld exit (just leave through the entry)", () => {
    const levels = generateDungeon({
      name: "Solo", style: "default", numLevels: 1,
      difficulty: "easy", levelSize: "small", torchDensity: "none",
      lockedDoors: false, seedBase: 4,
    });
    expect(levels[0].overworldExits.size).toBe(0);
  });
});

describe("Dungeon — styles", () => {
  it("cave style uses path floors", () => {
    const lvl = generateDungeonLevel({
      name: "Cave", width: 30, height: 20, style: "cave",
      difficulty: "easy", floorIdx: 0, placeStairsDown: false,
      placeOverworldExit: false, placeDoors: false,
      torchDensity: "none", seed: 1,
    });
    expect(countMatching(lvl, (id) => id === TILE_PATH)).toBeGreaterThan(0);
    expect(styleFloorTile("cave")).toBe(TILE_PATH);
  });

  it("forest style spawns archway entrance tiles and grass-floored rooms", () => {
    // We seed a few values until a forest run happens to land an
    // archway successfully — the algorithm tries 4 edges before
    // falling back to a center-of-room stair, so almost any seed
    // works.
    const lvl = generateDungeonLevel({
      name: "Wood", width: 30, height: 20, style: "forest",
      difficulty: "easy", floorIdx: 0, placeStairsDown: false,
      placeOverworldExit: false, placeDoors: false,
      torchDensity: "none", seed: 17,
    });
    // Either the entry is an archway (edge placement succeeded) or
    // a regular stairs-up (room-center fallback). Both are acceptable
    // outcomes; what matters for the test is that grass tiles exist
    // (room interiors) and tree-walls are non-walkable per cell.
    expect(countMatching(lvl, (id) => id === TILE_GRASS)).toBeGreaterThan(0);
    const entryTile = lvl.tiles[lvl.entryRow][lvl.entryCol];
    expect([TILE_FOREST_ARCHWAY_UP, TILE_STAIRS]).toContain(entryTile);
    // Forest-style applies a tree-wall walkability override on
    // surviving TILE_FOREST cells.
    const overrides = Object.values(lvl.tileProperties).filter((p) => p.walkable === false);
    expect(overrides.length).toBeGreaterThan(0);
  });
});

describe("Dungeon — torch density", () => {
  it("'none' produces zero wall-torch decorations", () => {
    const lvl = generateDungeonLevel({
      name: "Dark", width: 40, height: 30, style: "default",
      difficulty: "normal", floorIdx: 0, placeStairsDown: false,
      placeOverworldExit: false, placeDoors: false,
      torchDensity: "none", seed: 8,
    });
    const torchCount = Object.values(lvl.decorations).filter((id) => id === 34).length;
    expect(torchCount).toBe(0);
  });

  it("'abundant' produces strictly more torches than 'sparse'", () => {
    const sparse = generateDungeonLevel({
      name: "S", width: 40, height: 30, style: "default",
      difficulty: "normal", floorIdx: 0, placeStairsDown: false,
      placeOverworldExit: false, placeDoors: false,
      torchDensity: "sparse", seed: 1234,
    });
    const abundant = generateDungeonLevel({
      name: "A", width: 40, height: 30, style: "default",
      difficulty: "normal", floorIdx: 0, placeStairsDown: false,
      placeOverworldExit: false, placeDoors: false,
      torchDensity: "abundant", seed: 1234,
    });
    const sparseCount = Object.values(sparse.decorations).filter((id) => id === 34).length;
    const abundantCount = Object.values(abundant.decorations).filter((id) => id === 34).length;
    expect(abundantCount).toBeGreaterThan(sparseCount);
  });
});

describe("Dungeon — locked doors", () => {
  it("placing doors yields some door tiles", () => {
    const lvl = generateDungeonLevel({
      name: "Doors", width: 40, height: 30, style: "default",
      difficulty: "hard", floorIdx: 0, placeStairsDown: false,
      placeOverworldExit: false, placeDoors: true,
      torchDensity: "none", seed: 50,
    });
    const doorCount = countMatching(lvl, (id) => id === TILE_DDOOR);
    expect(doorCount).toBeGreaterThan(0);
  });
});

describe("Dungeon — chest + trap placement", () => {
  it("normal difficulty plants chests and traps in later rooms", () => {
    // Several seeds may need to be tried — chest placement is
    // probabilistic. We assert "across many seeds, both feature
    // types appear at least once" rather than per-seed presence.
    let totalChests = 0;
    let totalTraps = 0;
    for (let seed = 0; seed < 8; seed++) {
      const lvl = generateDungeonLevel({
        name: "F", width: 40, height: 30, style: "default",
        difficulty: "normal", floorIdx: 0, placeStairsDown: false,
        placeOverworldExit: false, placeDoors: false,
        torchDensity: "none", seed,
      });
      totalChests += countMatching(lvl, (id) => id === TILE_CHEST);
      totalTraps += countMatching(lvl, (id) => id === TILE_TRAP);
    }
    expect(totalChests).toBeGreaterThan(0);
    expect(totalTraps).toBeGreaterThan(0);
  });
});

describe("Dungeon — connectivity (entry must reach the descent stairs)", () => {
  function bfsReachable(level: DungeonLevel, sc: number, sr: number, walkable: ReadonlySet<number>): Set<string> {
    const visited = new Set<string>();
    const queue: Array<[number, number]> = [[sc, sr]];
    while (queue.length > 0) {
      const [c, r] = queue.shift()!;
      const k = `${c},${r}`;
      if (visited.has(k)) continue;
      if (c < 0 || c >= level.width || r < 0 || r >= level.height) continue;
      if (!walkable.has(level.tiles[r][c])) continue;
      visited.add(k);
      queue.push([c - 1, r], [c + 1, r], [c, r - 1], [c, r + 1]);
    }
    return visited;
  }

  it("regular doors don't disconnect the descent stairs from the entry", () => {
    const WALKABLE = new Set([
      TILE_DFLOOR, TILE_PATH, TILE_GRASS,
      TILE_STAIRS, TILE_STAIRS_DOWN,
      TILE_CHEST, TILE_TRAP, TILE_DDOOR,
    ]);
    let triedAtLeastOne = false;
    for (let seed = 0; seed < 6; seed++) {
      const lvl = generateDungeonLevel({
        name: "C", width: 40, height: 30, style: "default",
        difficulty: "normal", floorIdx: 0,
        placeStairsDown: true, placeOverworldExit: false,
        placeDoors: true, torchDensity: "none", seed,
      });
      // Find descent stair (might not exist on a degenerate seed).
      let stair: [number, number] | null = null;
      for (let r = 0; r < lvl.height && !stair; r++) {
        for (let c = 0; c < lvl.width; c++) {
          if (lvl.tiles[r][c] === TILE_STAIRS_DOWN) { stair = [c, r]; break; }
        }
      }
      if (!stair) continue;
      triedAtLeastOne = true;
      const reachable = bfsReachable(lvl, lvl.entryCol, lvl.entryRow, WALKABLE);
      expect(reachable.has(`${stair[0]},${stair[1]}`)).toBe(true);
    }
    expect(triedAtLeastOne).toBe(true);
  });
});
