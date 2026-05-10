import { describe, it, expect } from "vitest";
import {
  generateDungeon,
  generateDungeonLevel,
  getDifficultyProfile,
  dungeonSeed,
  styleFloorTile,
  placeQuestKillMonsters,
  cleanupCompletedQuestMonsters,
  TILE_DWALL,
  TILE_STAIRS,
  TILE_STAIRS_DOWN,
  TILE_CHEST,
  TILE_TRAP,
  type DungeonLevel,
  type QuestKillSpawnRow,
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

describe("placeQuestKillMonsters", () => {
  /** Build a tiny 2-floor "dungeon" of all-walkable cells with no
   *  random monsters. Each floor is a 4x4 grid; entry is (0,0). */
  function blankDungeon(numLevels = 2): DungeonLevel[] {
    const levels: DungeonLevel[] = [];
    for (let i = 0; i < numLevels; i++) {
      levels.push({
        name: `Floor ${i}`,
        width: 4,
        height: 4,
        tiles: [
          [0, 0, 0, 0],
          [0, 0, 0, 0],
          [0, 0, 0, 0],
          [0, 0, 0, 0],
        ],
        decorations: {},
        tileProperties: {},
        entryCol: 0,
        entryRow: 0,
        style: "default",
        monsters: [],
        openedChests: new Set(),
        triggeredTraps: new Set(),
        exploredTiles: new Set(),
        overworldExits: new Set(),
        questArtifacts: {},
      });
    }
    return levels;
  }

  function row(
    questName: string,
    stepIdx: number,
    remaining: number,
    name = "Wolves and Goblins",
    monsters = ["Goblin", "Wolf"],
  ): QuestKillSpawnRow {
    return {
      questName,
      stepIdx,
      remaining,
      template: { name, monsters, monsterPartyTile: monsters[0] },
    };
  }

  it("places `remaining` monsters on the matching floor for each step", () => {
    const levels = blankDungeon(2);
    placeQuestKillMonsters(
      levels,
      [row("Goblins in the Hill", 0, 3), row("Goblins in the Hill", 1, 1, "Goblin Ambush", ["Goblin", "Goblin"])],
      () => true,
    );
    // Step 0 → floor 0 (entry), step 1 → floor 1 (deepest).
    const f0 = levels[0].monsters.filter((m) => m.questName === "Goblins in the Hill" && m.stepIdx === 0);
    const f1 = levels[1].monsters.filter((m) => m.questName === "Goblins in the Hill" && m.stepIdx === 1);
    expect(f0).toHaveLength(3);
    expect(f1).toHaveLength(1);
    // Each placed monster carries the encounter roster + display name.
    for (const m of f0) {
      expect(m.encounterName).toBe("Wolves and Goblins");
      expect(m.encounterNames).toEqual(["Goblin", "Wolf"]);
    }
  });

  it("clamps step index to the deepest floor when stepIdx >= levels.length", () => {
    const levels = blankDungeon(2);
    placeQuestKillMonsters(levels, [row("Q", 5, 2)], () => true);
    expect(levels[0].monsters).toHaveLength(0);
    expect(levels[1].monsters).toHaveLength(2);
  });

  it("never spawns on the entry tile", () => {
    const levels = blankDungeon(1);
    // Force every cell to be available — the entry exclusion should
    // still hold.
    placeQuestKillMonsters(levels, [row("Q", 0, 16)], () => true);
    const onEntry = levels[0].monsters.find(
      (m) => m.col === levels[0].entryCol && m.row === levels[0].entryRow,
    );
    expect(onEntry).toBeUndefined();
  });

  it("only tops up to remaining — re-running is idempotent", () => {
    const levels = blankDungeon(1);
    // First pass — places 3.
    placeQuestKillMonsters(levels, [row("Q", 0, 3)], () => true);
    expect(levels[0].monsters).toHaveLength(3);
    // Pretend the player killed one — `remaining` drops to 2. Now
    // there are 2 already on the floor (have=2). Top-up needed = 0.
    levels[0].monsters.pop();
    placeQuestKillMonsters(levels, [row("Q", 0, 2)], () => true);
    expect(levels[0].monsters).toHaveLength(2);
    // Same call again — still 2 (idempotent).
    placeQuestKillMonsters(levels, [row("Q", 0, 2)], () => true);
    expect(levels[0].monsters).toHaveLength(2);
  });

  it("respects the isWalkable predicate (forest tree-walls etc.)", () => {
    const levels = blankDungeon(1);
    // Mark every column except col 0 as un-walkable. The placement
    // pool collapses to {(0,1), (0,2), (0,3)} — entry at (0,0) is
    // excluded — so we can place at most 3.
    placeQuestKillMonsters(
      levels,
      [row("Q", 0, 10)],
      (col) => col === 0,
    );
    expect(levels[0].monsters.length).toBeLessThanOrEqual(3);
    for (const m of levels[0].monsters) expect(m.col).toBe(0);
  });

  it("no-op when remaining is zero or the template has no monsters", () => {
    const levels = blankDungeon(1);
    placeQuestKillMonsters(levels, [row("Q", 0, 0)], () => true);
    placeQuestKillMonsters(levels, [{
      questName: "Q", stepIdx: 0, remaining: 5,
      template: { name: "Empty", monsters: [], monsterPartyTile: "" },
    }], () => true);
    expect(levels[0].monsters).toHaveLength(0);
  });

  it("each placed monster carries questName + stepIdx for the renderer", () => {
    const levels = blankDungeon(1);
    placeQuestKillMonsters(levels, [row("Goblins", 0, 1)], () => true);
    const m = levels[0].monsters[0];
    expect(m.questName).toBe("Goblins");
    expect(m.stepIdx).toBe(0);
    // ID prefix follows the q-<questName>-<stepIdx>-<n> pattern so
    // it can't collide with the random `m-<seed>-<i>` ids.
    expect(m.id.startsWith("q-Goblins-0-")).toBe(true);
  });

  it("strips random encounters from floors that get quest monsters", () => {
    const levels = blankDungeon(2);
    // Pretend the dungeon generator already placed 3 random rat
    // encounters on floor 0 (the dominant pool at low levels).
    levels[0].monsters.push(
      { id: "m-1-0", col: 1, row: 1, name: "Giant Rat", encounterNames: ["Giant Rat"], encounterName: "Cellar Rats" },
      { id: "m-1-1", col: 2, row: 2, name: "Giant Rat", encounterNames: ["Giant Rat"], encounterName: "Rat Nest" },
      { id: "m-1-2", col: 3, row: 3, name: "Giant Rat", encounterNames: ["Giant Rat"], encounterName: "Cellar Rats" },
    );
    // Floor 1 has random encounters too — they should NOT be cleared,
    // because no quest step targets that floor in this test.
    levels[1].monsters.push(
      { id: "m-2-0", col: 1, row: 1, name: "Giant Rat", encounterNames: ["Giant Rat"], encounterName: "Cellar Rats" },
    );
    placeQuestKillMonsters(levels, [row("Q", 0, 3)], () => true);
    // Floor 0: only the 3 quest monsters remain.
    expect(levels[0].monsters.every((m) => m.questName === "Q")).toBe(true);
    expect(levels[0].monsters).toHaveLength(3);
    // Floor 1 untouched.
    expect(levels[1].monsters).toHaveLength(1);
    expect(levels[1].monsters[0].questName).toBeUndefined();
  });

  it("two steps targeting the same floor strip random monsters once", () => {
    // 1-floor dungeon: both step 0 and step 1 land on floor 0 (clamp).
    const levels = blankDungeon(1);
    levels[0].monsters.push(
      { id: "m-1-0", col: 1, row: 1, name: "Giant Rat", encounterNames: ["Giant Rat"], encounterName: "Cellar Rats" },
    );
    placeQuestKillMonsters(levels, [row("Q", 0, 2), row("Q", 1, 1, "Boss", ["Goblin"])], () => true);
    // No random monsters; 2 + 1 = 3 quest monsters placed.
    expect(levels[0].monsters.every((m) => m.questName === "Q")).toBe(true);
    expect(levels[0].monsters).toHaveLength(3);
  });

  it("relocates stale quest monsters off the wrong floor onto their target floor", () => {
    // Simulates a player whose dungeon was generated under an older
    // version that placed step-1 monsters on floor 0 (everything on
    // the entry floor). On re-entry under the new floor-distribution
    // code, the helper should DELETE the misplaced monster from
    // floor 0 and spawn a fresh copy on floor 1 — net total stays at
    // `target_count` but the layout is now correct.
    const levels = blankDungeon(2);
    levels[0].monsters.push({
      id: "q-Q-1-stale",
      col: 1, row: 1,
      name: "Goblin",
      encounterNames: ["Goblin", "Goblin"],
      encounterName: "Goblin Ambush",
      questName: "Q",
      stepIdx: 1,
    });
    placeQuestKillMonsters(levels, [row("Q", 1, 1, "Goblin Ambush", ["Goblin"])], () => true);
    // Floor 0 has no step-1 monsters left.
    expect(levels[0].monsters.filter(
      (m) => m.questName === "Q" && m.stepIdx === 1,
    )).toHaveLength(0);
    // Floor 1 has exactly one — the relocation.
    expect(levels[1].monsters.filter(
      (m) => m.questName === "Q" && m.stepIdx === 1,
    )).toHaveLength(1);
    // Total = target_count, no duplicates.
    const total = levels.flatMap((l) => l.monsters).filter(
      (m) => m.questName === "Q" && m.stepIdx === 1,
    ).length;
    expect(total).toBe(1);
  });

  it("caps over-spawned quest monsters on the target floor at `remaining`", () => {
    // Simulates a prior run that placed FOUR step-0 monsters when
    // the quest only wants three (older code with no cap). Cleanup
    // should drop the extra so the player doesn't fight an extra
    // warband.
    const levels = blankDungeon(1);
    for (let i = 0; i < 4; i++) {
      levels[0].monsters.push({
        id: `q-Q-0-${i}`,
        col: i, row: 0,
        name: "Wolf",
        encounterNames: ["Wolf"],
        encounterName: "Wolves",
        questName: "Q",
        stepIdx: 0,
      });
    }
    placeQuestKillMonsters(levels, [row("Q", 0, 3)], () => true);
    expect(levels[0].monsters).toHaveLength(3);
    expect(levels[0].monsters.every((m) => m.questName === "Q")).toBe(true);
  });

  it("re-entry doesn't re-strip or duplicate quest monsters", () => {
    const levels = blankDungeon(1);
    // First entry: 3 random + 0 quest.
    levels[0].monsters.push(
      { id: "m-1-0", col: 0, row: 1, name: "Giant Rat", encounterNames: ["Giant Rat"], encounterName: "Cellar Rats" },
    );
    placeQuestKillMonsters(levels, [row("Q", 0, 3)], () => true);
    expect(levels[0].monsters).toHaveLength(3);
    // Pretend the player killed one quest monster, then re-entered.
    levels[0].monsters.pop();
    expect(levels[0].monsters).toHaveLength(2);
    placeQuestKillMonsters(levels, [row("Q", 0, 2)], () => true);
    // Top-up math gives have=2, remaining=2, needed=0 — no new spawns.
    expect(levels[0].monsters).toHaveLength(2);
    // And the random monsters didn't come back either.
    expect(levels[0].monsters.every((m) => m.questName === "Q")).toBe(true);
  });
});

describe("cleanupCompletedQuestMonsters", () => {
  function levelWithMonsters(...monsters: ReadonlyArray<{
    id: string;
    questName?: string;
    stepIdx?: number;
  }>): DungeonLevel {
    return {
      name: "L",
      width: 4, height: 4,
      tiles: [[0,0,0,0],[0,0,0,0],[0,0,0,0],[0,0,0,0]],
      decorations: {},
      tileProperties: {},
      entryCol: 0, entryRow: 0,
      style: "default",
      monsters: monsters.map((m, i) => ({
        col: i, row: 0,
        name: "Goblin",
        encounterNames: ["Goblin"],
        encounterName: "Whatever",
        ...m,
      })),
      openedChests: new Set(), triggeredTraps: new Set(),
      exploredTiles: new Set(), overworldExits: new Set(),
      questArtifacts: {},
    };
  }

  it("removes quest monsters whose step is no longer active", () => {
    const lvl = levelWithMonsters(
      { id: "live", questName: "Q", stepIdx: 0 },
      { id: "stale", questName: "Q", stepIdx: 1 },     // step 1 just completed
      { id: "ancient", questName: "Old Quest", stepIdx: 0 }, // turned-in quest
    );
    cleanupCompletedQuestMonsters([lvl], new Set(["Q|0"]));
    expect(lvl.monsters.map((m) => m.id)).toEqual(["live"]);
  });

  it("preserves random (non-quest) monsters untouched", () => {
    const lvl = levelWithMonsters(
      { id: "rat-1" },                                  // random — keep
      { id: "boss", questName: "Q", stepIdx: 0 },       // active — keep
      { id: "stale", questName: "Q", stepIdx: 1 },      // stale — drop
    );
    cleanupCompletedQuestMonsters([lvl], new Set(["Q|0"]));
    expect(lvl.monsters.map((m) => m.id)).toEqual(["rat-1", "boss"]);
  });

  it("sweeps every floor when called on a multi-level dungeon", () => {
    const a = levelWithMonsters({ id: "stale-a", questName: "Q", stepIdx: 0 });
    const b = levelWithMonsters({ id: "stale-b", questName: "Q", stepIdx: 0 });
    cleanupCompletedQuestMonsters([a, b], new Set());
    expect(a.monsters).toHaveLength(0);
    expect(b.monsters).toHaveLength(0);
  });

  it("is a no-op for an empty levels array", () => {
    expect(() => cleanupCompletedQuestMonsters([], new Set())).not.toThrow();
  });

  it("is idempotent — running twice with the same active set is a no-op", () => {
    const lvl = levelWithMonsters(
      { id: "live", questName: "Q", stepIdx: 0 },
      { id: "stale", questName: "Q", stepIdx: 1 },
    );
    cleanupCompletedQuestMonsters([lvl], new Set(["Q|0"]));
    const after = lvl.monsters.map((m) => m.id);
    cleanupCompletedQuestMonsters([lvl], new Set(["Q|0"]));
    expect(lvl.monsters.map((m) => m.id)).toEqual(after);
  });
});
