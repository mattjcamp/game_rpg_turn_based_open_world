import { describe, it, expect } from "vitest";
import { slotsForItem, getItem, type Item } from "./Items";

function table(): Map<string, Item> {
  const m = new Map<string, Item>();
  m.set("Dagger", {
    name: "Dagger", category: "weapons",
    description: "", slots: ["right_hand", "left_hand"],
    characterCanEquip: true, partyCanEquip: false,
    usable: false, effect: null, power: 3,
  });
  m.set("Round Shield", {
    name: "Round Shield", category: "armors",
    description: "", slots: ["left_hand"],
    characterCanEquip: true, partyCanEquip: false,
    usable: false, effect: null, evasion: 8,
  });
  m.set("Cloth", {
    name: "Cloth", category: "armors",
    description: "", slots: ["body"],
    characterCanEquip: true, partyCanEquip: false,
    usable: false, effect: null, evasion: 1,
  });
  m.set("Healing Herb", {
    name: "Healing Herb", category: "general",
    description: "", slots: [],
    characterCanEquip: false, partyCanEquip: false,
    usable: true, effect: "heal_hp",
  });
  return m;
}

describe("getItem", () => {
  it("returns the item by exact name across all categories", () => {
    const t = table();
    expect(getItem(t, "Dagger")?.category).toBe("weapons");
    expect(getItem(t, "Cloth")?.category).toBe("armors");
    expect(getItem(t, "Healing Herb")?.category).toBe("general");
  });

  it("returns null for unknown items", () => {
    expect(getItem(table(), "Mithril Plate")).toBeNull();
  });
});

describe("slotsForItem", () => {
  it("returns the slots for an equippable weapon", () => {
    expect(slotsForItem(table(), "Dagger")).toEqual(["right_hand", "left_hand"]);
  });

  it("returns the offhand slot for a shield", () => {
    expect(slotsForItem(table(), "Round Shield")).toEqual(["left_hand"]);
  });

  it("returns [] for non-equippable consumables", () => {
    expect(slotsForItem(table(), "Healing Herb")).toEqual([]);
  });

  it("returns [] for unknown items", () => {
    expect(slotsForItem(table(), "Mythril Plate")).toEqual([]);
  });
});
