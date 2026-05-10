import { describe, it, expect } from "vitest";
import {
  placeQuestInteriorMonsters,
  placeQuestInteriorItems,
  reachableFrom,
  snapToWalkable,
  type QuestKillRow,
  type QuestCollectRow,
  type WalkOracle,
} from "./InteriorSpawn";
import type { EncounterTemplate } from "./Encounters";
import type { QuestStep } from "./Quests";
import type { InteriorMonster, InteriorQuestItem } from "../state";

// 5×5 grid where every cell is walkable. Tests that need an obstacle
// build their own oracle.
function openGrid(w = 5, h = 5): WalkOracle {
  return { width: w, height: h, isWalkable: () => true };
}

const ENCOUNTERS: Record<string, EncounterTemplate[]> = {
  any: [
    {
      name: "Cellar Rats", level: 1, weight: 1, terrain: "land",
      monsterPartyTile: "Giant Rat", monsters: ["Giant Rat"],
    },
    {
      name: "Cursed Battalion", level: 4, weight: 1, terrain: "land",
      monsterPartyTile: "Skeleton Knight",
      monsters: ["Skeleton Knight", "Skeleton Knight", "Wraith"],
    },
  ],
};

function collectStep(over: Partial<QuestStep> = {}): QuestStep {
  return {
    description: "Pick it up",
    stepType: "collect",
    encounter: "",
    collectItem: "scroll",
    hasGuardian: false,
    guardianEncounter: "",
    spawnLocation: "space:Abandoned Building/Basement",
    targetCount: 1,
    ...over,
  };
}

describe("placeQuestInteriorMonsters", () => {
  it("places one monster per row.remaining onto walkable cells", () => {
    const rows: QuestKillRow[] = [
      { questName: "Q1", stepIdx: 0, encounter: "Cellar Rats", remaining: 3 },
    ];
    const out = placeQuestInteriorMonsters(rows, {
      walk: openGrid(),
      reserved: [],
      existing: [],
      encounters: ENCOUNTERS,
      // Deterministic RNG — picks the first cell every time.
      rng: () => 0,
    });
    expect(out).toHaveLength(3);
    for (const m of out) {
      expect(m.questName).toBe("Q1");
      expect(m.stepIdx).toBe(0);
      expect(m.name).toBe("Giant Rat");
      expect(m.encounterNames).toEqual(["Giant Rat"]);
      expect(m.encounterName).toBe("Cellar Rats");
      expect(m.isGuardian).toBeUndefined();
    }
  });

  it("preserves existing monsters and only tops up the missing copies", () => {
    const existing: InteriorMonster[] = [{
      id: "q-Q1-0-0",
      col: 1, row: 1,
      name: "Giant Rat",
      encounterNames: ["Giant Rat"],
      encounterName: "Cellar Rats",
      questName: "Q1",
      stepIdx: 0,
    }];
    const rows: QuestKillRow[] = [
      { questName: "Q1", stepIdx: 0, encounter: "Cellar Rats", remaining: 3 },
    ];
    const out = placeQuestInteriorMonsters(rows, {
      walk: openGrid(),
      reserved: [],
      existing,
      encounters: ENCOUNTERS,
      rng: () => 0,
    });
    // 1 carried over + 2 fresh = 3.
    expect(out).toHaveLength(3);
    expect(out[0].id).toBe("q-Q1-0-0");
    // The two fresh entries are tagged with the next ids.
    expect(out[1].id).toBe("q-Q1-0-1");
    expect(out[2].id).toBe("q-Q1-0-2");
  });

  it("flags collect-step guardians via isGuardian + 'g-' id prefix", () => {
    const rows: QuestKillRow[] = [
      {
        questName: "Veyron Heirloom",
        stepIdx: 0,
        encounter: "Cursed Battalion",
        remaining: 1,
        isGuardian: true,
      },
    ];
    const out = placeQuestInteriorMonsters(rows, {
      walk: openGrid(),
      reserved: [],
      existing: [],
      encounters: ENCOUNTERS,
      rng: () => 0,
    });
    expect(out).toHaveLength(1);
    expect(out[0].isGuardian).toBe(true);
    expect(out[0].id.startsWith("g-Veyron Heirloom-0-")).toBe(true);
    expect(out[0].encounterNames).toHaveLength(3);
    expect(out[0].name).toBe("Skeleton Knight");
  });

  it("counts kill spawns and guardian spawns as separate populations", () => {
    // Existing: one kill-step monster for the same (quest, step). The
    // guardian top-up should still place one even though `existing.have`
    // is 1 — guardians are counted separately.
    const existing: InteriorMonster[] = [{
      id: "q-Q1-0-0",
      col: 0, row: 0,
      name: "Giant Rat",
      encounterNames: ["Giant Rat"],
      encounterName: "Cellar Rats",
      questName: "Q1",
      stepIdx: 0,
    }];
    const rows: QuestKillRow[] = [
      {
        questName: "Q1", stepIdx: 0,
        encounter: "Cursed Battalion",
        remaining: 1,
        isGuardian: true,
      },
    ];
    const out = placeQuestInteriorMonsters(rows, {
      walk: openGrid(),
      reserved: [],
      existing,
      encounters: ENCOUNTERS,
      rng: () => 0,
    });
    expect(out).toHaveLength(2);
    expect(out[1].isGuardian).toBe(true);
  });

  it("respects reserved cells (entry / NPC tiles)", () => {
    const reserved: Array<readonly [number, number]> = [];
    for (let r = 0; r < 5; r++) {
      for (let c = 0; c < 5; c++) {
        if (!(c === 2 && r === 2)) reserved.push([c, r] as const);
      }
    }
    const rows: QuestKillRow[] = [
      { questName: "Q1", stepIdx: 0, encounter: "Cellar Rats", remaining: 3 },
    ];
    const out = placeQuestInteriorMonsters(rows, {
      walk: openGrid(),
      reserved,
      existing: [],
      encounters: ENCOUNTERS,
      rng: () => 0,
    });
    // Only one walkable cell remains → one spawn lands, the other two
    // can't fit and are dropped.
    expect(out).toHaveLength(1);
    expect(out[0].col).toBe(2);
    expect(out[0].row).toBe(2);
  });

  it("returns existing unchanged when the encounter isn't in the table", () => {
    const rows: QuestKillRow[] = [
      { questName: "Q1", stepIdx: 0, encounter: "Mythical Yeti", remaining: 2 },
    ];
    const out = placeQuestInteriorMonsters(rows, {
      walk: openGrid(),
      reserved: [],
      existing: [],
      encounters: ENCOUNTERS,
      rng: () => 0,
    });
    expect(out).toEqual([]);
  });
});

describe("reachableFrom", () => {
  it("returns every walkable cell in a fully open grid", () => {
    const set = reachableFrom(openGrid(3, 3), 1, 1);
    expect(set).not.toBeNull();
    expect(set!.size).toBe(9);
  });

  it("returns null when the start tile is unwalkable", () => {
    const allBlocked: WalkOracle = {
      width: 3, height: 3, isWalkable: () => false,
    };
    expect(reachableFrom(allBlocked, 1, 1)).toBeNull();
  });

  it("excludes cells cut off by a wall", () => {
    // 3x3 with a wall column at c=1 — left and right halves disconnected.
    const split: WalkOracle = {
      width: 3, height: 3,
      isWalkable: (c) => c !== 1,
    };
    const set = reachableFrom(split, 0, 0);
    expect(set).not.toBeNull();
    // Left column (c=0) is reachable (3 cells); right column (c=2) is
    // not, even though it's walkable on its own.
    expect(set!.size).toBe(3);
    expect(set!.has("0,0")).toBe(true);
    expect(set!.has("0,2")).toBe(true);
    expect(set!.has("2,0")).toBe(false);
  });
});

describe("snapToWalkable", () => {
  it("returns the original coords when they're already walkable", () => {
    expect(snapToWalkable(openGrid(), 2, 2)).toEqual({ col: 2, row: 2 });
  });

  it("snaps an unwalkable position to the nearest walkable neighbour", () => {
    // Wall at (2, 2) only; everything else walkable.
    const oneWall: WalkOracle = {
      width: 5, height: 5,
      isWalkable: (c, r) => !(c === 2 && r === 2),
    };
    const out = snapToWalkable(oneWall, 2, 2);
    // Ring iteration walks the 8 cells at Chebyshev 1 in (dc, dr)
    // order — the first hit is (1, 1).
    expect(out).toEqual({ col: 1, row: 1 });
  });

  it("respects the reachable filter when snapping", () => {
    const split: WalkOracle = {
      width: 5, height: 5,
      isWalkable: (c) => c !== 2,
    };
    // Pinned to (2, 0), wall column. Left and right halves are
    // disconnected. With reachable=left, snap should go to the
    // nearest left-side cell (1, 0).
    const left = reachableFrom(split, 0, 0);
    const out = snapToWalkable(split, 2, 0, { reachable: left });
    expect(out).toEqual({ col: 1, row: 0 });
  });

  it("avoids occupied cells when snapping", () => {
    const oneWall: WalkOracle = {
      width: 5, height: 5,
      isWalkable: (c, r) => !(c === 2 && r === 2),
    };
    // (1, 1) would be the natural snap, but it's already occupied.
    const out = snapToWalkable(oneWall, 2, 2, {
      occupied: [[1, 1] as const],
    });
    // Next ring-1 cell in iteration order is (1, 2).
    expect(out).toEqual({ col: 1, row: 2 });
  });

  it("returns the original coords if no walkable cell exists within the radius", () => {
    const allBlocked: WalkOracle = {
      width: 5, height: 5, isWalkable: () => false,
    };
    expect(snapToWalkable(allBlocked, 2, 2)).toEqual({ col: 2, row: 2 });
  });
});

describe("placeQuestInteriorMonsters reachability", () => {
  it("excludes cut-off cells when entry is provided", () => {
    // 5x5 with col=2 walls — entry at (0, 0) reaches only the left
    // half. Spawn three monsters with remaining=3.
    const split: WalkOracle = {
      width: 5, height: 5,
      isWalkable: (c) => c !== 2,
    };
    const out = placeQuestInteriorMonsters(
      [{ questName: "Q1", stepIdx: 0, encounter: "Cellar Rats", remaining: 3 }],
      {
        walk: split,
        reserved: [],
        existing: [],
        encounters: ENCOUNTERS,
        rng: () => 0,
        entryCol: 0,
        entryRow: 0,
      },
    );
    // Every spawn lands on the left half (c=0 or 1), never the
    // disconnected right half (c=3 or 4).
    for (const m of out) {
      expect(m.col).toBeLessThan(2);
    }
  });
});

describe("placeQuestInteriorItems", () => {
  it("drops one item per active collect row on a walkable cell", () => {
    const rows: QuestCollectRow[] = [
      { questName: "Veyron Heirloom", stepIdx: 0, step: collectStep() },
    ];
    const out = placeQuestInteriorItems(rows, {
      walk: openGrid(),
      reserved: [],
      existing: [],
      rng: () => 0,
    });
    expect(out).toHaveLength(1);
    expect(out[0].questName).toBe("Veyron Heirloom");
    expect(out[0].itemName).toBe("scroll");
    expect(out[0].id).toMatch(/^qi-Veyron Heirloom-0-/);
  });

  it("honours pinned spawn_col/spawn_row when the cell is walkable", () => {
    const rows: QuestCollectRow[] = [
      { questName: "Q1", stepIdx: 0, step: collectStep({ spawnCol: 3, spawnRow: 2 }) },
    ];
    const out = placeQuestInteriorItems(rows, {
      walk: openGrid(),
      reserved: [],
      existing: [],
      // RNG that would pick the LAST cell — proves the pin overrode it.
      rng: () => 0.999,
    });
    expect(out).toHaveLength(1);
    expect(out[0].col).toBe(3);
    expect(out[0].row).toBe(2);
  });

  it("falls back to a random walkable cell when pinned coords aren't walkable", () => {
    const wallAt = (cx: number, cy: number): WalkOracle => ({
      width: 5, height: 5,
      isWalkable: (c, r) => !(c === cx && r === cy),
    });
    const rows: QuestCollectRow[] = [
      { questName: "Q1", stepIdx: 0, step: collectStep({ spawnCol: 1, spawnRow: 1 }) },
    ];
    const out = placeQuestInteriorItems(rows, {
      walk: wallAt(1, 1),
      reserved: [],
      existing: [],
      rng: () => 0,
    });
    expect(out).toHaveLength(1);
    // (1, 1) is unwalkable so we fell back to the first walkable cell
    // — (0, 0) under our deterministic rng.
    expect(out[0].col).toBe(0);
    expect(out[0].row).toBe(0);
  });

  it("never replaces an existing item for the same (quest, step)", () => {
    const existing: InteriorQuestItem[] = [{
      id: "qi-Q1-0-0",
      col: 4, row: 4,
      itemName: "scroll",
      questName: "Q1",
      stepIdx: 0,
    }];
    const rows: QuestCollectRow[] = [
      { questName: "Q1", stepIdx: 0, step: collectStep() },
    ];
    const out = placeQuestInteriorItems(rows, {
      walk: openGrid(),
      reserved: [],
      existing,
      rng: () => 0,
    });
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe("qi-Q1-0-0");
    expect(out[0].col).toBe(4);
    expect(out[0].row).toBe(4);
  });

  it("avoids cells held by interior monsters (e.g. the guardian)", () => {
    const monsterCells: Array<readonly [number, number]> = [
      [0, 0] as const,
    ];
    const rows: QuestCollectRow[] = [
      { questName: "Q1", stepIdx: 0, step: collectStep({ spawnCol: 0, spawnRow: 0 }) },
    ];
    const out = placeQuestInteriorItems(rows, {
      walk: openGrid(),
      reserved: [],
      existing: [],
      monsterCells,
      rng: () => 0,
    });
    expect(out).toHaveLength(1);
    // Pinned cell was occupied by the guardian → fell back to first
    // walkable non-occupied cell (0, 1) under deterministic rng.
    expect([out[0].col, out[0].row]).toEqual([1, 0]);
  });
});
