import { describe, it, expect } from "vitest";
import {
  countReagent,
  consumeReagent,
  recipeIsAffordable,
  recipeAvailability,
  attemptBrew,
  type Recipe,
} from "./Potions";
import { partyFromRaw, activeMembers, type Party } from "./Party";

function makeParty(): Party {
  return partyFromRaw({
    start_position: { col: 0, row: 0 },
    gold: 0,
    roster: [
      { name: "Selina", class: "Alchemist", race: "Gnome", level: 1, hp: 18, intelligence: 14 },
      { name: "Gimli",  class: "Fighter",   race: "Dwarf", level: 1, hp: 20, intelligence: 10 },
    ],
    active_party: [0, 1],
    inventory: [],
  });
}

function makePartyNoAlchemist(): Party {
  return partyFromRaw({
    gold: 0,
    roster: [
      { name: "Gimli", class: "Fighter", race: "Dwarf", level: 1, hp: 20, intelligence: 10 },
    ],
    active_party: [0],
    inventory: [],
  });
}

const healingPotion: Recipe = {
  id: "Healing Potion",
  name: "Healing Potion",
  description: "",
  reagents: { Moonpetal: 1, "Spring Water": 1 },
  dc: 10,
  resultItem: "Healing Potion",
  resultCount: 1,
  category: "restoration",
};

describe("countReagent — mixed stash shapes", () => {
  it("counts a single per-entry reagent", () => {
    const p = makeParty();
    p.inventory.push({ item: "Moonpetal" });
    expect(countReagent(p, "Moonpetal")).toBe(1);
  });

  it("counts a stacked reagent's charges", () => {
    const p = makeParty();
    p.inventory.push({ item: "Moonpetal", charges: 5 });
    expect(countReagent(p, "Moonpetal")).toBe(5);
  });

  it("sums per-entry and stacked rows for the same reagent", () => {
    const p = makeParty();
    p.inventory.push({ item: "Moonpetal", charges: 3 });
    p.inventory.push({ item: "Moonpetal" }); // one more bare row
    p.inventory.push({ item: "Moonpetal" });
    expect(countReagent(p, "Moonpetal")).toBe(5);
  });

  it("returns 0 when the reagent isn't present", () => {
    const p = makeParty();
    expect(countReagent(p, "Moonpetal")).toBe(0);
  });
});

describe("consumeReagent", () => {
  it("removes a per-entry reagent and returns true on full consume", () => {
    const p = makeParty();
    p.inventory.push({ item: "Moonpetal" });
    p.inventory.push({ item: "Rock" });
    expect(consumeReagent(p, "Moonpetal", 1)).toBe(true);
    expect(p.inventory.map((e) => e.item)).toEqual(["Rock"]);
  });

  it("decrements a stack's charges before dropping the row", () => {
    const p = makeParty();
    p.inventory.push({ item: "Spring Water", charges: 4 });
    expect(consumeReagent(p, "Spring Water", 1)).toBe(true);
    expect(p.inventory).toEqual([{ item: "Spring Water", charges: 3 }]);
    expect(consumeReagent(p, "Spring Water", 3)).toBe(true);
    expect(p.inventory).toEqual([]);
  });

  it("walks across multiple rows to satisfy qty", () => {
    const p = makeParty();
    p.inventory.push({ item: "Moonpetal" });
    p.inventory.push({ item: "Moonpetal", charges: 2 });
    p.inventory.push({ item: "Moonpetal" });
    expect(consumeReagent(p, "Moonpetal", 3)).toBe(true);
    // The walk goes end → start, charges before plain rows; we expect
    // one Moonpetal row to remain (either bare or as the head of the
    // original stack — either is correct, the count is what matters).
    expect(countReagent(p, "Moonpetal")).toBe(1);
  });

  it("returns false when the stash runs short", () => {
    const p = makeParty();
    p.inventory.push({ item: "Moonpetal" });
    expect(consumeReagent(p, "Moonpetal", 3)).toBe(false);
    // Anything that was there gets consumed even on shortfall — the
    // engine relies on pre-validation via `recipeIsAffordable`.
    expect(countReagent(p, "Moonpetal")).toBe(0);
  });
});

describe("recipeIsAffordable / recipeAvailability", () => {
  it("flags a recipe affordable when every reagent meets quantity", () => {
    const p = makeParty();
    p.inventory.push({ item: "Moonpetal", charges: 1 });
    p.inventory.push({ item: "Spring Water", charges: 1 });
    expect(recipeIsAffordable(p, healingPotion)).toBe(true);
    expect(recipeAvailability(p, healingPotion)).toEqual({
      affordable: true,
      missing: [],
    });
  });

  it("flags missing reagents in the availability report", () => {
    const p = makeParty();
    p.inventory.push({ item: "Moonpetal" });
    // Spring Water absent.
    const r = recipeAvailability(p, healingPotion);
    expect(r.affordable).toBe(false);
    expect(r.missing).toEqual(["Spring Water"]);
  });

  it("treats partial quantities as missing", () => {
    const p = makeParty();
    const multiCost: Recipe = {
      ...healingPotion,
      reagents: { Moonpetal: 2, "Spring Water": 1 },
    };
    p.inventory.push({ item: "Moonpetal" }); // only 1
    p.inventory.push({ item: "Spring Water" });
    expect(recipeAvailability(p, multiCost).missing).toEqual(["Moonpetal"]);
  });
});

describe("attemptBrew", () => {
  it("refuses without an Alchemist (no reagents consumed)", () => {
    const p = makePartyNoAlchemist();
    p.inventory.push({ item: "Moonpetal" });
    p.inventory.push({ item: "Spring Water" });
    const r = attemptBrew(p, activeMembers(p), healingPotion, () => 0);
    expect(r.ok).toBe(false);
    expect(r.message).toContain("Alchemist");
    expect(countReagent(p, "Moonpetal")).toBe(1);
    expect(countReagent(p, "Spring Water")).toBe(1);
  });

  it("refuses when reagents are missing (no consume)", () => {
    const p = makeParty();
    p.inventory.push({ item: "Moonpetal" });
    // Spring Water missing.
    const r = attemptBrew(p, activeMembers(p), healingPotion, () => 0);
    expect(r.ok).toBe(false);
    expect(r.message.toLowerCase()).toContain("missing");
    expect(countReagent(p, "Moonpetal")).toBe(1);
  });

  it("on success: consumes reagents, adds the potion, surfaces the roll", () => {
    const p = makeParty();
    p.inventory.push({ item: "Moonpetal" });
    p.inventory.push({ item: "Spring Water" });
    // INT 14 = +2 mod. DC 10. Need roll ≥ 8. rng = 0.5 → floor(10)+1 = 11 → success (11+2 = 13).
    const r = attemptBrew(p, activeMembers(p), healingPotion, () => 0.5);
    expect(r.ok).toBe(true);
    expect(r.success).toBe(true);
    expect(r.roll).toBe(11);
    expect(r.intMod).toBe(2);
    expect(r.message).toContain("Healing Potion");
    expect(r.message).toContain("DC 10");
    // Reagents gone, potion in stash.
    expect(countReagent(p, "Moonpetal")).toBe(0);
    expect(countReagent(p, "Spring Water")).toBe(0);
    expect(p.inventory.some((e) => e.item === "Healing Potion")).toBe(true);
  });

  it("on failure: still consumes reagents, leaves no potion", () => {
    const p = makeParty();
    p.inventory.push({ item: "Moonpetal" });
    p.inventory.push({ item: "Spring Water" });
    // rng = 0 → roll = 1 → total = 1 + 2 = 3 < DC 10 → failure.
    const r = attemptBrew(p, activeMembers(p), healingPotion, () => 0);
    expect(r.ok).toBe(true);
    expect(r.success).toBe(false);
    expect(r.roll).toBe(1);
    expect(r.message.toLowerCase()).toContain("fumble");
    expect(countReagent(p, "Moonpetal")).toBe(0);
    expect(countReagent(p, "Spring Water")).toBe(0);
    expect(p.inventory.some((e) => e.item === "Healing Potion")).toBe(false);
  });

  it("multi-reagent recipe debits each row correctly", () => {
    const p = makeParty();
    p.inventory.push({ item: "Moonpetal", charges: 2 });
    p.inventory.push({ item: "Serpent Root" });
    p.inventory.push({ item: "Brimite Ore" });
    const elixir: Recipe = {
      id: "Elixir of Strength",
      name: "Elixir of Strength",
      description: "",
      reagents: { Moonpetal: 1, "Serpent Root": 1, "Brimite Ore": 1 },
      dc: 14,
      resultItem: "Elixir of Strength",
      resultCount: 1,
      category: "enhancement",
    };
    // rng = 0.95 → roll = floor(0.95*20)+1 = 20 → 20+2 = 22 ≥ 14 → success.
    const r = attemptBrew(p, activeMembers(p), elixir, () => 0.95);
    expect(r.success).toBe(true);
    expect(countReagent(p, "Moonpetal")).toBe(1); // 2 → 1
    expect(countReagent(p, "Serpent Root")).toBe(0);
    expect(countReagent(p, "Brimite Ore")).toBe(0);
    expect(p.inventory.some((e) => e.item === "Elixir of Strength")).toBe(true);
  });

  it("honours resultCount when > 1", () => {
    const p = makeParty();
    p.inventory.push({ item: "Moonpetal" });
    p.inventory.push({ item: "Spring Water" });
    const bulkRecipe: Recipe = { ...healingPotion, resultCount: 3 };
    attemptBrew(p, activeMembers(p), bulkRecipe, () => 0.95);
    const count = p.inventory.filter((e) => e.item === "Healing Potion").length;
    expect(count).toBe(3);
  });
});
