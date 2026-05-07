import { describe, it, expect } from "vitest";
import {
  parseSpawnPoints,
  trySpawnMonster,
  roamStep,
  type SpawnPoint,
  type RoamingMonster,
} from "./SpawnPoints";
import { mulberry32 } from "../rng";

describe("SpawnPoints — loader", () => {
  it("parses a basic spawn_points.json structure", () => {
    const m = parseSpawnPoints({
      spawn_points: {
        "66": {
          name: "Monster Spawn",
          spawn_monsters: ["Goblin", "Orc"],
          spawn_chance: 5,
          spawn_radius: 4,
          max_spawned: 3,
          boss_monsters: ["Goblin", "Orc"],
          xp_reward: 50,
          gold_reward: 25,
          loot: ["Arrows"],
        },
      },
    });
    expect(m.size).toBe(1);
    const sp = m.get(66)!;
    expect(sp.name).toBe("Monster Spawn");
    expect(sp.spawn_monsters).toEqual(["Goblin", "Orc"]);
    expect(sp.spawn_chance).toBe(5);
    expect(sp.spawn_radius).toBe(4);
    expect(sp.max_spawned).toBe(3);
    expect(sp.boss_monsters).toEqual(["Goblin", "Orc"]);
  });

  it("falls back to single boss_monster when boss_monsters missing", () => {
    const m = parseSpawnPoints({
      spawn_points: {
        "66": { boss_monster: "Goblin" },
      },
    });
    expect(m.get(66)!.boss_monsters).toEqual(["Goblin"]);
  });

  it("provides sensible defaults for missing fields", () => {
    const m = parseSpawnPoints({ spawn_points: { "66": {} } });
    const sp = m.get(66)!;
    expect(sp.spawn_chance).toBe(20);   // default
    expect(sp.spawn_radius).toBe(3);
    expect(sp.max_spawned).toBe(2);
    expect(sp.spawn_monsters).toEqual([]);
    expect(sp.boss_monsters).toEqual([]);
  });

  it("ignores non-numeric tile-id keys", () => {
    const m = parseSpawnPoints({
      spawn_points: { "abc": { name: "X" } },
    });
    expect(m.size).toBe(0);
  });
});

describe("trySpawnMonster", () => {
  // Helper to build a SpawnPoint quickly.
  function point(over: Partial<SpawnPoint> = {}): SpawnPoint {
    return {
      name: "Monster Spawn",
      description: "",
      spawn_monsters: ["Goblin"],
      spawn_chance: 100,        // always rolls success unless overridden
      spawn_radius: 4,
      max_spawned: 4,
      boss_monsters: [],
      xp_reward: 0, gold_reward: 0, loot: [],
      ...over,
    };
  }

  // Always-walkable everywhere.
  const walkable = (): boolean => true;

  it("returns null when spawn_chance fails", () => {
    const out = trySpawnMonster({
      spawnTile: { col: 5, row: 5, tileId: 66 },
      point: point({ spawn_chance: 0 }),  // 0% — always fails the roll
      party: { col: 0, row: 0 },
      existing: [],
      isWalkable: walkable,
      rng: mulberry32(1),
    });
    expect(out).toBeNull();
  });

  it("returns a roamer on the spawn tile when the roll lands", () => {
    const out = trySpawnMonster({
      spawnTile: { col: 5, row: 5, tileId: 66 },
      point: point(),
      party: { col: 0, row: 0 },
      existing: [],
      isWalkable: walkable,
      rng: mulberry32(2),
    });
    expect(out).not.toBeNull();
    expect(out!.name).toBe("Goblin");
    expect(out!.sourceKey).toBe("5,5");
    // Position is on-or-adjacent to the spawn tile.
    expect(Math.max(Math.abs(out!.col - 5), Math.abs(out!.row - 5))).toBeLessThanOrEqual(1);
  });

  it("respects max_spawned by counting nearby roamers", () => {
    const existing: RoamingMonster[] = [
      { id: "a", name: "Goblin", col: 5, row: 5, sourceKey: "5,5" },
      { id: "b", name: "Goblin", col: 6, row: 5, sourceKey: "5,5" },
    ];
    const out = trySpawnMonster({
      spawnTile: { col: 5, row: 5, tileId: 66 },
      point: point({ max_spawned: 2 }),
      party: { col: 0, row: 0 },
      existing,
      isWalkable: walkable,
      rng: mulberry32(3),
    });
    expect(out).toBeNull();
  });

  it("refuses to spawn adjacent to the party (Manhattan ≤ 1)", () => {
    // Party right next to the spawn tile so every neighbour would be
    // too close — only the diagonals two tiles out should qualify.
    const out = trySpawnMonster({
      spawnTile: { col: 5, row: 5, tileId: 66 },
      point: point(),
      party: { col: 5, row: 4 },          // one step north of the tile
      existing: [],
      isWalkable: walkable,
      rng: mulberry32(4),
    });
    if (out) {
      const manhattan = Math.abs(out.col - 5) + Math.abs(out.row - 4);
      expect(manhattan).toBeGreaterThan(1);
    }
  });

  it("skips occupied cells when picking a spawn position", () => {
    const existing: RoamingMonster[] = [
      { id: "a", name: "Goblin", col: 5, row: 5, sourceKey: "5,5" },
    ];
    const out = trySpawnMonster({
      spawnTile: { col: 5, row: 5, tileId: 66 },
      point: point({ max_spawned: 5 }),
      party: { col: 0, row: 0 },
      existing,
      isWalkable: walkable,
      rng: mulberry32(5),
    });
    if (out) {
      // Not on top of the existing roamer.
      expect(out.col === 5 && out.row === 5).toBe(false);
    }
  });
});

describe("roamStep", () => {
  const walkable = (): boolean => true;

  it("steps cardinally toward the party", () => {
    // Party west of the monster — westward step.
    const next = roamStep({ col: 5, row: 5 }, { col: 1, row: 5 }, walkable);
    expect(next).toEqual({ col: 4, row: 5 });
  });

  it("does not move when no cardinal step closes Chebyshev distance", () => {
    // Party diagonally adjacent: any cardinal step keeps the same
    // Chebyshev distance, so the monster sits.
    const next = roamStep({ col: 5, row: 5 }, { col: 6, row: 6 }, walkable);
    expect(next).toEqual({ col: 5, row: 5 });
  });

  it("returns the same tile when already on top of the party", () => {
    const next = roamStep({ col: 3, row: 3 }, { col: 3, row: 3 }, walkable);
    expect(next).toEqual({ col: 3, row: 3 });
  });

  it("respects walls — blocking the only improving direction makes it sit", () => {
    // Party due west of the monster — westward step is the single
    // improving direction (Chebyshev pursuit). Block that tile and
    // the monster has no good move, so it stays put.
    const isWall = (c: number, r: number): boolean => c === 4 && r === 5;
    const next = roamStep(
      { col: 5, row: 5 }, { col: 1, row: 5 },
      (c, r) => !isWall(c, r),
    );
    expect(next).toEqual({ col: 5, row: 5 });
  });

  it("respects an extra blocked predicate (other roamers)", () => {
    // Same alignment as the wall test, but using the optional
    // blocked() callback to model an occupied tile.
    const blockedAt = (c: number, r: number): boolean => c === 4 && r === 5;
    const next = roamStep(
      { col: 5, row: 5 }, { col: 1, row: 5 },
      () => true, blockedAt,
    );
    expect(next).toEqual({ col: 5, row: 5 });
  });
});

describe("destroyed spawns short-circuit", () => {
  // The OverworldScene calls trySpawnMonster only for tiles NOT in
  // gameState.destroyedSpawns. We don't simulate the scene here, but
  // we verify the spawn-tile id and key shape so the integration
  // layer keeps lining up.
  it("spawn tile key uses the col,row shape that destroyedSpawns expects", () => {
    const out = trySpawnMonster({
      spawnTile: { col: 7, row: 9, tileId: 66 },
      point: {
        name: "X", description: "", spawn_monsters: ["Goblin"],
        spawn_chance: 100, spawn_radius: 3, max_spawned: 4,
        boss_monsters: [], xp_reward: 0, gold_reward: 0, loot: [],
      },
      party: { col: 0, row: 0 },
      existing: [],
      isWalkable: () => true,
      rng: mulberry32(8),
    });
    expect(out?.sourceKey).toBe("7,9");
  });
});
