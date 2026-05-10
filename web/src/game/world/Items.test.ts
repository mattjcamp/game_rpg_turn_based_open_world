import { describe, it, expect } from "vitest";
import { slotsForItem, getItem, isCombatUsable, type Item } from "./Items";

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

describe("isCombatUsable", () => {
  // The "default true" rule mirrors the Python game so authors don't
  // have to set the flag on every potion / herb. Only items that
  // explicitly opt out (`combat_usable: false`) get filtered from the
  // combat Use-item picker.
  function mk(over: Partial<Item>): Item {
    return {
      name: "Test", category: "general", description: "", slots: [],
      characterCanEquip: false, partyCanEquip: false,
      usable: false, effect: null, ...over,
    };
  }

  it("returns false for non-usable items even with combatUsable:true set", () => {
    expect(isCombatUsable(mk({ usable: false, combatUsable: true }))).toBe(false);
  });

  it("returns true for a usable item with no combatUsable flag (default)", () => {
    expect(isCombatUsable(mk({ usable: true }))).toBe(true);
  });

  it("returns true when combatUsable is explicitly true", () => {
    expect(isCombatUsable(mk({ usable: true, combatUsable: true }))).toBe(true);
  });

  it("returns false when combatUsable is explicitly false (Camping Supplies)", () => {
    expect(isCombatUsable(mk({ usable: true, combatUsable: false }))).toBe(false);
  });
});
