import { describe, it, expect, beforeEach } from "vitest";
import {
  ensureQuestStates,
  acceptQuest,
  markTurnedIn,
  findQuest,
  locationMatches,
  creditKills,
  creditCollect,
  activeCollectStepFor,
  locationHint,
  applyWorldUnlocks,
  applyTurnedInWorldUnlocks,
  summariseUnlocks,
  worldUnlockTileName,
  type AppliedUnlock,
  type QuestDef,
  type QuestState,
  type WorldUnlock,
} from "./Quests";
import type { EncounterTemplate } from "./Encounters";
import { TileMap } from "./TileMap";

function killStep(overrides: Partial<QuestDef["steps"][number]> = {}): QuestDef["steps"][number] {
  return {
    description: "Kill them",
    stepType: "kill",
    encounter: "Cellar Rats",
    collectItem: "",
    hasGuardian: false,
    guardianEncounter: "",
    spawnLocation: "dungeon:Goblin's Nest",
    targetCount: 1,
    ...overrides,
  };
}

function collectStep(overrides: Partial<QuestDef["steps"][number]> = {}): QuestDef["steps"][number] {
  return {
    description: "Recover the Sealstone",
    stepType: "collect",
    encounter: "",
    collectItem: "Seal of Binding",
    hasGuardian: true,
    guardianEncounter: "Necromancer's Guard",
    spawnLocation: "dungeon:The Old Forest by the Sea",
    targetCount: 1,
    ...overrides,
  };
}

function quest(name: string, overrides: Partial<QuestDef> = {}): QuestDef {
  return {
    name,
    description: "",
    giverNpc: name + "'s Giver",
    giverSprite: "",
    giverLocation: "town:Plainstown",
    giverDialogue: "",
    giverCol: 0,
    giverRow: 0,
    rewardXp: 100,
    rewardGold: 50,
    rewardItems: [],
    rewardWorldUnlocks: [],
    isFinalQuest: false,
    victoryText: "",
    steps: [killStep()],
    ...overrides,
  };
}

const ENCOUNTERS: Record<string, EncounterTemplate[]> = {
  dungeon: [
    {
      name: "Cellar Rats", level: 1, weight: 1, terrain: "land",
      monsterPartyTile: "Giant Rat", monsters: ["Giant Rat"],
    },
    {
      name: "Goblin Ambush", level: 2, weight: 1, terrain: "land",
      monsterPartyTile: "Goblin", monsters: ["Goblin", "Goblin"],
    },
    {
      name: "Wolves and Goblins", level: 2, weight: 1, terrain: "land",
      monsterPartyTile: "Wolf", monsters: ["Wolf", "Goblin"],
    },
  ],
};

describe("Quests — locationMatches", () => {
  it("empty step location credits any combat", () => {
    expect(locationMatches("", "dungeon:X")).toBe(true);
    expect(locationMatches("", "")).toBe(true);
  });
  it("'overview' matches overworld combat", () => {
    expect(locationMatches("overview", "overview")).toBe(true);
    expect(locationMatches("overview", "overworld")).toBe(true);
    expect(locationMatches("overview", "")).toBe(true);
    expect(locationMatches("overview", "dungeon:X")).toBe(false);
  });
  it("dungeon:X matches dungeon:X regardless of floor", () => {
    expect(locationMatches("dungeon:Crypt", "dungeon:Crypt")).toBe(true);
    expect(locationMatches("dungeon:Crypt", "dungeon:Crypt - Floor 1")).toBe(true);
    expect(locationMatches("dungeon:Crypt", "dungeon:Crypt - Floor 4")).toBe(true);
    expect(locationMatches("dungeon:Crypt", "dungeon:Mage Coven")).toBe(false);
  });
  it("building:X matches space:X/Y", () => {
    expect(locationMatches("building:Inn", "space:Inn/Common Room")).toBe(true);
    expect(locationMatches("building:Inn", "space:Tavern/Common Room")).toBe(false);
  });
  it("non-empty step location with no combat location returns false", () => {
    expect(locationMatches("dungeon:X", "")).toBe(false);
  });
});

describe("Quests — state lifecycle", () => {
  let states: Map<string, QuestState>;
  let defs: QuestDef[];

  beforeEach(() => {
    states = new Map();
    defs = [quest("Q1"), quest("Q2", { steps: [killStep(), killStep({ targetCount: 3 })] })];
  });

  it("ensureQuestStates seeds an entry per quest with status=available", () => {
    ensureQuestStates(defs, states);
    expect(states.size).toBe(2);
    expect(states.get("Q1")?.status).toBe("available");
    expect(states.get("Q1")?.stepProgress).toEqual([false]);
    expect(states.get("Q2")?.stepProgress).toEqual([false, false]);
  });

  it("ensureQuestStates pads stepProgress when a quest grew steps", () => {
    states.set("Q1", { status: "active", stepProgress: [], stepKills: {} });
    ensureQuestStates([quest("Q1", { steps: [killStep(), killStep()] })], states);
    expect(states.get("Q1")?.stepProgress).toEqual([false, false]);
  });

  it("acceptQuest flips available → active, no-op otherwise", () => {
    ensureQuestStates(defs, states);
    expect(acceptQuest(states, "Q1")).toBe(true);
    expect(states.get("Q1")?.status).toBe("active");
    expect(acceptQuest(states, "Q1")).toBe(false); // already active
  });

  it("markTurnedIn flips completed → turned_in only", () => {
    ensureQuestStates(defs, states);
    states.get("Q1")!.status = "completed";
    expect(markTurnedIn(states, "Q1")).toBe(true);
    expect(states.get("Q1")?.status).toBe("turned_in");
    expect(markTurnedIn(states, "Q1")).toBe(false); // already turned in
  });

  it("findQuest returns null on miss", () => {
    expect(findQuest(defs, "Nope")).toBeNull();
    expect(findQuest(defs, "Q2")?.steps.length).toBe(2);
  });
});

describe("Quests — creditKills", () => {
  let states: Map<string, QuestState>;
  let defs: QuestDef[];

  beforeEach(() => {
    states = new Map();
  });

  it("credits a kill step when location + roster match", () => {
    defs = [quest("Q1")];
    ensureQuestStates(defs, states);
    acceptQuest(states, "Q1");
    const result = creditKills(defs, states, ENCOUNTERS, ["Giant Rat"], "dungeon:Goblin's Nest");
    expect(result.messages.length).toBeGreaterThan(0);
    expect(result.newlyCompleted).toContain("Q1");
    expect(states.get("Q1")?.status).toBe("completed");
    expect(result.callouts.length).toBe(1);
    expect(result.callouts[0].questComplete).toBe(true);
  });

  it("doesn't credit a kill at the wrong location", () => {
    defs = [quest("Q1")];
    ensureQuestStates(defs, states);
    acceptQuest(states, "Q1");
    const result = creditKills(defs, states, ENCOUNTERS, ["Giant Rat"], "dungeon:Crypt");
    expect(result.messages).toEqual([]);
    expect(states.get("Q1")?.status).toBe("active");
  });

  it("doesn't credit when status is not active", () => {
    defs = [quest("Q1")];
    ensureQuestStates(defs, states);
    // status is still "available"
    const result = creditKills(defs, states, ENCOUNTERS, ["Giant Rat"], "dungeon:Goblin's Nest");
    expect(result.messages).toEqual([]);
  });

  it("multi-target steps report progress and complete on the right roll", () => {
    defs = [quest("Q1", { steps: [killStep({ targetCount: 3 })] })];
    ensureQuestStates(defs, states);
    acceptQuest(states, "Q1");

    let result = creditKills(defs, states, ENCOUNTERS, ["Giant Rat"], "dungeon:Goblin's Nest");
    expect(states.get("Q1")?.stepKills[0]).toBe(1);
    expect(states.get("Q1")?.stepProgress[0]).toBe(false);
    expect(result.messages[0]).toContain("(1/3)");

    creditKills(defs, states, ENCOUNTERS, ["Giant Rat"], "dungeon:Goblin's Nest");
    creditKills(defs, states, ENCOUNTERS, ["Giant Rat"], "dungeon:Goblin's Nest");
    expect(states.get("Q1")?.stepProgress[0]).toBe(true);
    expect(states.get("Q1")?.status).toBe("completed");
  });

  it("matches monster names case-insensitively and across snake_case", () => {
    defs = [quest("Q1")];
    ensureQuestStates(defs, states);
    acceptQuest(states, "Q1");
    // Roster has "Giant Rat"; killed list has "giant_rat" — must still credit.
    const result = creditKills(defs, states, ENCOUNTERS, ["giant_rat"], "dungeon:Goblin's Nest");
    expect(result.newlyCompleted).toContain("Q1");
  });

  it("credits any roster member (encounter has multiple monsters)", () => {
    defs = [quest("Q1", { steps: [killStep({ encounter: "Wolves and Goblins" })] })];
    ensureQuestStates(defs, states);
    acceptQuest(states, "Q1");
    // Killed only the goblin from the Wolves and Goblins encounter.
    const result = creditKills(defs, states, ENCOUNTERS, ["Goblin"], "dungeon:Goblin's Nest");
    expect(result.newlyCompleted).toContain("Q1");
  });
});

describe("Quests — creditCollect", () => {
  it("credits a collect step and flips quest to completed when last", () => {
    const defs = [quest("Q1", { steps: [collectStep()] })];
    const states = new Map<string, QuestState>();
    ensureQuestStates(defs, states);
    acceptQuest(states, "Q1");
    const result = creditCollect(defs, states, "Q1", 0, "Seal of Binding");
    expect(result.questNowCompleted).toBe(true);
    expect(states.get("Q1")?.status).toBe("completed");
    expect(states.get("Q1")?.stepProgress[0]).toBe(true);
    expect(result.callout?.questComplete).toBe(true);
  });

  it("credits a single collect step in a multi-step quest without flipping status", () => {
    const defs = [quest("Q1", { steps: [collectStep(), killStep()] })];
    const states = new Map<string, QuestState>();
    ensureQuestStates(defs, states);
    acceptQuest(states, "Q1");
    const result = creditCollect(defs, states, "Q1", 0, "Seal of Binding");
    expect(result.questNowCompleted).toBe(false);
    expect(states.get("Q1")?.status).toBe("active");
  });

  it("returns a fallback message when the quest is unknown", () => {
    const result = creditCollect([], new Map(), "Nope", 0, "Foo");
    expect(result.message).toContain("Foo");
    expect(result.questNowCompleted).toBe(false);
  });
});

describe("Quests — activeCollectStepFor", () => {
  it("returns the first active collect step matching the location", () => {
    const defs = [
      quest("Q1", { steps: [killStep()] }),
      quest("Q2", { steps: [collectStep()] }),
    ];
    const states = new Map<string, QuestState>();
    ensureQuestStates(defs, states);
    acceptQuest(states, "Q2");
    const found = activeCollectStepFor(defs, states, "dungeon:The Old Forest by the Sea");
    expect(found?.questName).toBe("Q2");
    expect(found?.stepIdx).toBe(0);
  });

  it("returns null when no active collect targets the location", () => {
    const defs = [quest("Q1", { steps: [collectStep()] })];
    const states = new Map<string, QuestState>();
    ensureQuestStates(defs, states);
    acceptQuest(states, "Q1");
    expect(activeCollectStepFor(defs, states, "dungeon:Crypt")).toBeNull();
  });

  it("skips quests not in active state", () => {
    const defs = [quest("Q1", { steps: [collectStep()] })];
    const states = new Map<string, QuestState>();
    ensureQuestStates(defs, states);
    // Q1 still available, not active
    expect(activeCollectStepFor(defs, states, "dungeon:The Old Forest by the Sea")).toBeNull();
  });
});

describe("Quests — locationHint", () => {
  it("returns empty string for non-dungeon quests", () => {
    expect(locationHint(quest("Q1", { steps: [killStep({ spawnLocation: "town:X" })] }))).toBe("");
  });
  it("lists single dungeon name", () => {
    const hint = locationHint(quest("Q1", { steps: [killStep({ spawnLocation: "dungeon:Crypt" })] }));
    expect(hint).toContain("Crypt");
    expect(hint).toContain("tread carefully");
  });
  it("flags guardian for collect steps", () => {
    const hint = locationHint(quest("Q1", { steps: [collectStep()] }));
    expect(hint).toContain("guardian");
  });
});

// ── World-unlock rewards ─────────────────────────────────────────

// 5×4 sandbox tile map: 0 = TILE_GRASS by convention, 4 = TILE_WATER
// stand-ins. We don't need real tile_defs entries for these tests
// because applyWorldUnlocks just calls setTile / getTile — both of
// which are pure positional ops on the array.
function makeTileMap(): TileMap {
  const tiles: number[][] = [];
  for (let r = 0; r < 4; r++) {
    const row: number[] = [];
    for (let c = 0; c < 5; c++) row.push(0);
    tiles.push(row);
  }
  return new TileMap(5, 4, tiles);
}

describe("Quests — applyWorldUnlocks", () => {
  it("mutates the tile map for in-bounds ops", () => {
    const tm = makeTileMap();
    const unlocks: WorldUnlock[] = [
      { kind: "add_tile", col: 2, row: 1, tile: 8 },
      { kind: "remove_obstacle", col: 0, row: 0, tile: 1 },
    ];
    const applied = applyWorldUnlocks(tm, unlocks);
    expect(tm.getTile(2, 1)).toBe(8);
    expect(tm.getTile(0, 0)).toBe(1);
    expect(applied).toEqual([
      [2, 1, 8],
      [0, 0, 1],
    ]);
  });

  it("skips out-of-bounds ops without throwing", () => {
    const tm = makeTileMap();
    const unlocks: WorldUnlock[] = [
      { kind: "add_tile", col: -1, row: 0, tile: 8 },
      { kind: "add_tile", col: 0, row: 99, tile: 8 },
      { kind: "add_tile", col: 5, row: 0, tile: 8 },  // width = 5 → 5 is OOB
      { kind: "add_tile", col: 4, row: 3, tile: 7 },  // last cell, in bounds
    ];
    const applied = applyWorldUnlocks(tm, unlocks);
    expect(applied).toEqual([[4, 3, 7]]);
    expect(tm.getTile(4, 3)).toBe(7);
  });

  it("returns an empty list when the tile map is null or unlocks empty", () => {
    expect(applyWorldUnlocks(null, [])).toEqual([]);
    expect(applyWorldUnlocks(makeTileMap(), [])).toEqual([]);
    expect(applyWorldUnlocks(null, [{ kind: "add_tile", col: 0, row: 0, tile: 1 }])).toEqual([]);
  });
});

describe("Quests — applyTurnedInWorldUnlocks", () => {
  it("re-applies every turned-in quest's unlocks and skips others", () => {
    const tm = makeTileMap();
    const defs = [
      quest("DoneQ", {
        rewardWorldUnlocks: [{ kind: "add_tile", col: 1, row: 1, tile: 8 }],
      }),
      quest("ActiveQ", {
        rewardWorldUnlocks: [{ kind: "add_tile", col: 2, row: 2, tile: 9 }],
      }),
      quest("AvailableQ", {
        rewardWorldUnlocks: [{ kind: "add_tile", col: 3, row: 3, tile: 7 }],
      }),
    ];
    const states = new Map<string, QuestState>();
    ensureQuestStates(defs, states);
    // DoneQ → turned_in via the lifecycle helpers (status-gated).
    acceptQuest(states, "DoneQ");
    states.get("DoneQ")!.status = "completed";
    markTurnedIn(states, "DoneQ");
    // ActiveQ stays in `active`; AvailableQ stays in `available`.
    acceptQuest(states, "ActiveQ");

    const applied = applyTurnedInWorldUnlocks(tm, defs, states);

    expect(applied).toEqual([[1, 1, 8]]);
    expect(tm.getTile(1, 1)).toBe(8);
    expect(tm.getTile(2, 2)).toBe(0);  // active quest — not yet
    expect(tm.getTile(3, 3)).toBe(0);  // never accepted
  });

  it("is idempotent — replaying the pass leaves the map identical", () => {
    const tm = makeTileMap();
    const defs = [
      quest("Q", { rewardWorldUnlocks: [{ kind: "add_tile", col: 0, row: 0, tile: 5 }] }),
    ];
    const states = new Map<string, QuestState>();
    ensureQuestStates(defs, states);
    acceptQuest(states, "Q");
    states.get("Q")!.status = "completed";
    markTurnedIn(states, "Q");

    applyTurnedInWorldUnlocks(tm, defs, states);
    const snap = JSON.stringify(tm.tiles);
    applyTurnedInWorldUnlocks(tm, defs, states);
    expect(JSON.stringify(tm.tiles)).toBe(snap);
  });

  it("no-ops on a null tile map", () => {
    const defs = [quest("Q", { rewardWorldUnlocks: [{ kind: "add_tile", col: 0, row: 0, tile: 1 }] })];
    const states = new Map<string, QuestState>();
    ensureQuestStates(defs, states);
    expect(applyTurnedInWorldUnlocks(null, defs, states)).toEqual([]);
  });
});

describe("Quests — summary helpers", () => {
  it("worldUnlockTileName falls back to a numeric label for unknown ids", () => {
    // tile id 9999 is not in the runtime def table — name should be "Tile 9999".
    expect(worldUnlockTileName(9999)).toBe("Tile 9999");
  });

  it("summariseUnlocks formats single vs. multi cleanly", () => {
    expect(summariseUnlocks([])).toBe("");
    const single: AppliedUnlock[] = [[5, 13, 8]];
    expect(summariseUnlocks(single)).toContain("at (5,13)");
    const multi: AppliedUnlock[] = [
      [5, 13, 8],
      [6, 13, 8],
    ];
    expect(summariseUnlocks(multi)).toBe("World changed: 2 tiles updated");
  });
});
