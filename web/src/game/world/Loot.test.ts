import { describe, it, expect } from "vitest";
import {
  buildLootPool,
  rollLootDrop,
  LOOT_DROP_CHANCE,
  LOOT_SHOP_TYPES,
} from "./Loot";
import type { Item } from "./Items";
import type { Counter } from "./Counters";

/** Build a small items catalog covering the stock referenced below. */
function items(): Map<string, Item> {
  const make = (name: string, category: Item["category"]): Item => ({
    name,
    category,
    description: "",
    slots: [],
    characterCanEquip: false,
    partyCanEquip: false,
    usable: false,
    effect: null,
  });
  const m = new Map<string, Item>();
  for (const n of ["Sword", "Dagger", "Bow"]) m.set(n, make(n, "weapons"));
  for (const n of ["Cloth", "Leather", "Plate"]) m.set(n, make(n, "armors"));
  for (const n of ["Torch", "Healing Herb", "Lockpick"]) m.set(n, make(n, "general"));
  // Magic-shop gear that should NOT appear in the pool.
  m.set("Healing Potion", make("Healing Potion", "general"));
  return m;
}

function counters(): Map<string, Counter> {
  const m = new Map<string, Counter>();
  m.set("general", {
    shopType: "general",
    name: "General Store",
    description: "",
    // Duplicates are fine — pool de-dupes and sorts.
    items: ["Torch", "Torch", "Healing Herb", "Lockpick"],
  });
  m.set("weapon", {
    shopType: "weapon",
    name: "Weapons Shop",
    description: "",
    items: ["Sword", "Dagger", "Bow"],
  });
  m.set("armor", {
    shopType: "armor",
    name: "Armor Shop",
    description: "",
    items: ["Cloth", "Leather", "Plate"],
  });
  // Magic shop should be ignored entirely.
  m.set("magic", {
    shopType: "magic",
    name: "Magic Shop",
    description: "",
    items: ["Healing Potion"],
  });
  return m;
}

/** Tiny scripted RNG that yields each value once then defaults to 0. */
function scriptedRng(values: number[]): () => number {
  let i = 0;
  return () => (i < values.length ? values[i++] : 0);
}

describe("LOOT_SHOP_TYPES", () => {
  it("only includes general, weapon, and armor counters", () => {
    expect([...LOOT_SHOP_TYPES]).toEqual(["general", "weapon", "armor"]);
  });
});

describe("buildLootPool", () => {
  it("unions general/weapon/armor shop items, de-duped and sorted", () => {
    const pool = buildLootPool(items(), counters());
    expect(pool).toEqual([
      "Bow",
      "Cloth",
      "Dagger",
      "Healing Herb",
      "Leather",
      "Lockpick",
      "Plate",
      "Sword",
      "Torch",
    ]);
  });

  it("excludes items from non-loot counters (e.g. magic shop)", () => {
    const pool = buildLootPool(items(), counters());
    expect(pool).not.toContain("Healing Potion");
  });

  it("skips counter entries the items catalog doesn't know", () => {
    const cs = counters();
    cs.get("weapon")!.items.push("Phantom Glaive");
    const pool = buildLootPool(items(), cs);
    expect(pool).not.toContain("Phantom Glaive");
  });

  it("returns an empty list when the relevant counters are missing", () => {
    expect(buildLootPool(items(), new Map())).toEqual([]);
  });
});

describe("rollLootDrop", () => {
  it("returns null when the first roll is at or above the drop chance", () => {
    // First call governs whether anything drops at all.
    const rng = scriptedRng([LOOT_DROP_CHANCE]); // exactly the threshold
    expect(rollLootDrop(items(), counters(), rng)).toBeNull();
  });

  it("returns null when the first roll is well above the drop chance", () => {
    const rng = scriptedRng([0.9, 0]);
    expect(rollLootDrop(items(), counters(), rng)).toBeNull();
  });

  it("picks an item from the pool when the first roll is under the drop chance", () => {
    // First roll < 0.25 → drop fires; second roll selects an index.
    // Pool is sorted alphabetically, so index 0 is "Bow".
    const rng = scriptedRng([0.1, 0]);
    expect(rollLootDrop(items(), counters(), rng)).toBe("Bow");
  });

  it("indexes the last entry when the second roll is just under 1", () => {
    const rng = scriptedRng([0.0, 0.999999]);
    const pool = buildLootPool(items(), counters());
    expect(rollLootDrop(items(), counters(), rng)).toBe(pool[pool.length - 1]);
  });

  it("only ever returns items from the loot pool", () => {
    const pool = new Set(buildLootPool(items(), counters()));
    // Sample a bunch of (low, frac) RNG sequences and confirm every
    // non-null result is in the pool.
    for (let trial = 0; trial < 50; trial++) {
      const rng = scriptedRng([0.05, trial / 50]);
      const drop = rollLootDrop(items(), counters(), rng);
      if (drop !== null) expect(pool.has(drop)).toBe(true);
    }
  });

  it("returns null when no loot counters are loaded", () => {
    const rng = scriptedRng([0.0, 0.5]);
    expect(rollLootDrop(items(), new Map(), rng)).toBeNull();
  });
});
