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
  type QuestDef,
  type QuestState,
} from "./Quests";
import type { EncounterTemplate } from "./Encounters";

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
