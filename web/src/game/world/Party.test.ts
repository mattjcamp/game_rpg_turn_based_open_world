/**
 * Tests for the Party loader + sprite fallback logic.
 */

import { describe, it, expect } from "vitest";
import {
  partyFromRaw,
  memberFromRaw,
  spriteForMember,
  activeMembers,
  mergeStackableInventory,
  mergePartyStackables,
  findAmmoInStash,
  consumeAmmoFromStash,
  consumeOneFromStackAt,
  partyHasAmmo,
  swapToMeleeIfOutOfAmmo,
} from "./Party";
import type { InventoryItem } from "./Party";
import type { Item } from "./Items";

describe("spriteForMember", () => {
  it("keeps a normalised /assets/characters/<known>.png path as-is", () => {
    expect(
      spriteForMember("src/assets/game/characters/cleric.png", "Cleric")
    ).toBe("/assets/characters/cleric.png");
    expect(
      spriteForMember("/assets/characters/wizard.png", "Wizard")
    ).toBe("/assets/characters/wizard.png");
  });

  it("accepts any humanoid sprite — npcs and monsters too", () => {
    // The character creator lets the player pick an avatar from any
    // shipped humanoid folder. Picks should round-trip through
    // localStorage / party.json without being squashed back to a
    // class default.
    expect(
      spriteForMember("src/assets/game/npcs/shopkeep.png", "Fighter")
    ).toBe("/assets/npcs/shopkeep.png");
    expect(
      spriteForMember("/assets/monsters/dark_mage.png", "Wizard")
    ).toBe("/assets/monsters/dark_mage.png");
  });

  it("falls back to the class sprite when the path is in a non-humanoid folder", () => {
    // Anything outside characters/npcs/monsters drops to the class
    // default — bogus paths in old saves don't render as broken
    // images on screen.
    expect(spriteForMember("nope.png", "Wizard")).toBe(
      "/assets/characters/wizard.png"
    );
    expect(spriteForMember("/assets/terrain/grass.png", "Cleric")).toBe(
      "/assets/characters/cleric.png"
    );
    expect(spriteForMember(undefined, "Cleric")).toBe(
      "/assets/characters/cleric.png"
    );
  });
});

describe("memberFromRaw", () => {
  it("populates maxHp from hp at load time", () => {
    const m = memberFromRaw({
      name: "Gimli", class: "Fighter", race: "Dwarf", gender: "Male",
      hp: 24, strength: 18, dexterity: 14, intelligence: 9, wisdom: 9,
      level: 2,
      equipped: { right_hand: "Sword", left_hand: null, body: "Cloth", head: null },
      inventory: [{ item: "Healing Herb" }],
    });
    expect(m.hp).toBe(24);
    expect(m.maxHp).toBe(24);
    expect(m.equipped.rightHand).toBe("Sword");
    expect(m.equipped.body).toBe("Cloth");
    expect(m.inventory).toEqual([{ item: "Healing Herb" }]);
  });

  it("defaults missing fields sensibly", () => {
    const m = memberFromRaw({});
    expect(m.name).toBe("?");
    expect(m.class).toBe("Fighter");
    expect(m.maxHp).toBe(0);
    expect(m.equipped).toEqual({
      rightHand: null, leftHand: null, body: null, head: null,
    });
    expect(m.sprite).toBe("/assets/characters/fighter.png");
  });
});

describe("partyFromRaw", () => {
  const raw = {
    start_position: { col: 14, row: 16 },
    gold: 25,
    roster: [
      { name: "Gimli", class: "Fighter", race: "Dwarf", hp: 20 },
      { name: "Merry", class: "Thief",   race: "Halfling", hp: 18 },
      { name: "Gandolf", class: "Wizard", race: "Elf", hp: 16 },
      { name: "Selina", class: "Cleric", race: "Human", hp: 18 },
    ],
    active_party: [0, 1, 2, 3],
    party_effects: { effect_1: null, effect_2: null, effect_3: null, effect_4: null },
    inventory: [{ item: "Torch" }, { item: "Rock" }],
  };

  it("parses every top-level field", () => {
    const p = partyFromRaw(raw);
    expect(p.startPosition).toEqual({ col: 14, row: 16 });
    expect(p.gold).toBe(25);
    expect(p.roster).toHaveLength(4);
    expect(p.activeParty).toEqual([0, 1, 2, 3]);
    expect(p.inventory).toHaveLength(2);
  });

  it("activeMembers returns the four active roster entries in order", () => {
    const p = partyFromRaw({
      ...raw,
      active_party: [3, 1, 0, 2], // out of natural order
    });
    const members = activeMembers(p);
    expect(members.map((m) => m.name)).toEqual([
      "Selina", "Merry", "Gimli", "Gandolf",
    ]);
  });

  it("activeMembers skips out-of-bounds indices", () => {
    const p = partyFromRaw({ ...raw, active_party: [0, 99, 1] });
    expect(activeMembers(p).map((m) => m.name)).toEqual(["Gimli", "Merry"]);
  });

  it("defaults active_party / party_effects / inventory when missing", () => {
    const p = partyFromRaw({ roster: [{ name: "Solo", class: "Fighter" }] });
    expect(p.activeParty).toEqual([0, 1, 2, 3]);
    expect(p.partyEffects.effect_1).toBeNull();
    expect(p.inventory).toEqual([]);
  });

  it("auto-promotes bare-string inventory entries to InventoryItem objects", () => {
    // A hand-edit (or linter) sometimes flattens `{ "item": "Arrows" }`
    // to a bare `"Arrows"`. Without normalization the runtime sees a
    // string where it expects an object and `partyHasAmmo` /
    // stackable-merge silently fail. The loader should heal the data
    // on the way in.
    const p = partyFromRaw({
      // Cast through unknown — the JSON is valid but the typed shape
      // would otherwise refuse the bare-string entry.
      inventory: ["Arrows" as unknown as { item: string }],
    });
    expect(p.inventory).toEqual([{ item: "Arrows" }]);
  });

  it("auto-promotes bare-string entries on per-member inventories too", () => {
    const p = partyFromRaw({
      roster: [{
        name: "Pippin", class: "Thief", race: "Halfling", hp: 9,
        inventory: ["Lockpick" as unknown as { item: string }],
      }],
    });
    expect(p.roster[0].inventory).toEqual([{ item: "Lockpick" }]);
  });

  it("preserves well-formed inventory entries unchanged", () => {
    const p = partyFromRaw({
      inventory: [
        { item: "Arrows", charges: 20 },
        { item: "Healing Herb" },
      ],
    });
    expect(p.inventory).toEqual([
      { item: "Arrows", charges: 20 },
      { item: "Healing Herb" },
    ]);
  });

  it("drops malformed entries (number, null, missing item field) silently", () => {
    const p = partyFromRaw({
      inventory: [
        "Arrows" as unknown as { item: string },
        42 as unknown as { item: string },
        null as unknown as { item: string },
        { /* no `item` field */ } as unknown as { item: string },
        { item: "Torch" },
      ],
    });
    // Strings get promoted; objects with an `item` string survive;
    // numbers / nulls / missing-item objects are dropped — better
    // than poisoning the whole load.
    expect(p.inventory).toEqual([
      { item: "Arrows" },
      { item: "Torch" },
    ]);
  });
});

/** Items map for the stacking helpers' tests. */
function stackingItems(): Map<string, Item> {
  const items = new Map<string, Item>();
  items.set("Arrows", { name: "Arrows", category: "general", stackable: true, charges: 20 } as Item);
  items.set("Bolts",  { name: "Bolts",  category: "general", stackable: true, charges: 20 } as Item);
  items.set("Healing Herb", { name: "Healing Herb", category: "general", stackable: true, charges: 1 } as Item);
  items.set("Sword",        { name: "Sword",        category: "weapons" } as Item);
  items.set("Long Bow", {
    name: "Long Bow", category: "weapons", ranged: true, ammo: "Arrows", power: 7,
  } as Item);
  items.set("Crossbow", {
    name: "Crossbow", category: "weapons", ranged: true, ammo: "Bolts", power: 9,
  } as Item);
  items.set("Round Shield", {
    name: "Round Shield", category: "armors",
  } as Item);
  return items;
}

describe("mergeStackableInventory", () => {
  it("collapses duplicate stackable entries summing charges", () => {
    const merged = mergeStackableInventory(
      [
        { item: "Arrows", charges: 20 },
        { item: "Arrows", charges: 20 },
        { item: "Sword" },
      ],
      stackingItems(),
    );
    expect(merged).toEqual([
      { item: "Arrows", charges: 40 },
      { item: "Sword" },
    ]);
  });

  it("treats a missing charges field as 1", () => {
    const merged = mergeStackableInventory(
      [{ item: "Healing Herb" }, { item: "Healing Herb" }, { item: "Healing Herb" }],
      stackingItems(),
    );
    expect(merged).toEqual([{ item: "Healing Herb", charges: 3 }]);
  });

  it("leaves non-stackable items alone (one row per copy)", () => {
    const merged = mergeStackableInventory(
      [{ item: "Sword" }, { item: "Sword" }],
      stackingItems(),
    );
    expect(merged).toEqual([{ item: "Sword" }, { item: "Sword" }]);
  });

  it("is idempotent — running on already-merged inventory is a no-op", () => {
    const items = stackingItems();
    const once = mergeStackableInventory(
      [{ item: "Arrows", charges: 20 }, { item: "Arrows", charges: 40 }],
      items,
    );
    const twice = mergeStackableInventory(once, items);
    expect(twice).toEqual([{ item: "Arrows", charges: 60 }]);
  });

  it("ignores items the catalog doesn't know", () => {
    const merged = mergeStackableInventory(
      [{ item: "Phantom Glaive" }, { item: "Phantom Glaive" }],
      stackingItems(),
    );
    expect(merged).toEqual([{ item: "Phantom Glaive" }, { item: "Phantom Glaive" }]);
  });
});

describe("mergePartyStackables", () => {
  it("merges shared stash AND every roster member's bag", () => {
    const p = partyFromRaw({
      roster: [
        {
          name: "Gimli", class: "Fighter", hp: 20,
          inventory: [{ item: "Healing Herb" }, { item: "Healing Herb" }],
        },
      ],
      inventory: [
        { item: "Arrows", charges: 20 },
        { item: "Arrows", charges: 20 },
        { item: "Sword" },
      ],
    });
    mergePartyStackables(p, stackingItems());
    expect(p.inventory).toEqual([
      { item: "Arrows", charges: 40 },
      { item: "Sword" },
    ]);
    expect(p.roster[0].inventory).toEqual([{ item: "Healing Herb", charges: 2 }]);
  });
});

describe("findAmmoInStash / partyHasAmmo / consumeAmmoFromStash", () => {
  it("findAmmoInStash returns the index + entry, null when absent", () => {
    const p = partyFromRaw({ inventory: [{ item: "Arrows", charges: 5 }] });
    expect(findAmmoInStash(p, "Arrows")).toEqual({
      index: 0, entry: { item: "Arrows", charges: 5 },
    });
    expect(findAmmoInStash(p, "Bolts")).toBeNull();
  });

  it("partyHasAmmo flips false when the only stack hits zero", () => {
    const p = partyFromRaw({ inventory: [{ item: "Arrows", charges: 1 }] });
    expect(partyHasAmmo(p, "Arrows")).toBe(true);
    expect(consumeAmmoFromStash(p, "Arrows")).toBe(true);
    expect(partyHasAmmo(p, "Arrows")).toBe(false);
    // Spent stacks are removed entirely so the inventory doesn't
    // grow zero-charge tombstones.
    expect(p.inventory).toEqual([]);
  });

  it("consumeAmmoFromStash decrements without removing while charges remain", () => {
    const p = partyFromRaw({ inventory: [{ item: "Arrows", charges: 3 }] });
    expect(consumeAmmoFromStash(p, "Arrows")).toBe(true);
    expect(p.inventory).toEqual([{ item: "Arrows", charges: 2 }]);
  });

  it("consumeAmmoFromStash returns false when no matching stack exists", () => {
    const p = partyFromRaw({ inventory: [] });
    expect(consumeAmmoFromStash(p, "Arrows")).toBe(false);
  });
});

describe("consumeOneFromStackAt", () => {
  // Regression: the Throw action used to splice the whole entry out,
  // so a single thrown rock destroyed all 20 in the stack. This helper
  // is the fix — it must decrement charges and leave the stack in
  // place until the last unit is consumed.
  it("decrements charges on a stack without removing the entry", () => {
    const list: InventoryItem[] = [{ item: "Rock", charges: 20 }];
    expect(consumeOneFromStackAt(list, 0)).toBe(true);
    expect(list).toEqual([{ item: "Rock", charges: 19 }]);
  });

  it("removes the entry when the last charge is consumed", () => {
    const list: InventoryItem[] = [{ item: "Rock", charges: 1 }];
    expect(consumeOneFromStackAt(list, 0)).toBe(true);
    expect(list).toEqual([]);
  });

  it("removes a non-stacked single (no charges field) outright", () => {
    const list: InventoryItem[] = [{ item: "Dagger" }];
    expect(consumeOneFromStackAt(list, 0)).toBe(true);
    expect(list).toEqual([]);
  });

  it("operates on the entry at the given index, not the first matching item", () => {
    const list: InventoryItem[] = [
      { item: "Rock", charges: 5 },
      { item: "Rock", charges: 20 },
    ];
    expect(consumeOneFromStackAt(list, 1)).toBe(true);
    expect(list).toEqual([
      { item: "Rock", charges: 5 },
      { item: "Rock", charges: 19 },
    ]);
  });

  it("returns false on an out-of-bounds index", () => {
    const list: InventoryItem[] = [{ item: "Rock", charges: 5 }];
    expect(consumeOneFromStackAt(list, 1)).toBe(false);
    expect(consumeOneFromStackAt(list, -1)).toBe(false);
    expect(list).toEqual([{ item: "Rock", charges: 5 }]);
  });
});

describe("swapToMeleeIfOutOfAmmo", () => {
  // The Hands/Body collapse migrated stale `left_hand` gear into
  // personal inventory at load time, so to pin down the algorithm
  // these tests stamp the offhand AFTER `partyFromRaw` runs — the
  // function still has to work when offhand state appears via
  // future content paths (or test fixtures), even if save loading
  // can't introduce one anymore.
  it("swaps the offhand into the main hand when out of ammo", () => {
    const p = partyFromRaw({
      roster: [{
        name: "Legolas", class: "Thief", hp: 18,
        equipped: { right_hand: "Long Bow", left_hand: null, body: null, head: null },
      }],
      inventory: [], // no Arrows
    });
    const m = p.roster[0];
    m.equipped.leftHand = "Sword";
    const r = swapToMeleeIfOutOfAmmo(m, p, stackingItems());
    expect(r).toEqual({ from: "Long Bow", to: "Sword" });
    expect(m.equipped.rightHand).toBe("Sword");
    expect(m.equipped.leftHand).toBeNull();
  });

  it("no-op when the party still has matching ammo", () => {
    const p = partyFromRaw({
      roster: [{
        name: "Legolas", class: "Thief", hp: 18,
        equipped: { right_hand: "Long Bow", left_hand: null, body: null, head: null },
      }],
      inventory: [{ item: "Arrows", charges: 20 }],
    });
    const m = p.roster[0];
    m.equipped.leftHand = "Sword";
    expect(swapToMeleeIfOutOfAmmo(m, p, stackingItems())).toBeNull();
    expect(m.equipped.rightHand).toBe("Long Bow");
  });

  it("no-op when the offhand isn't a weapon (e.g. shield)", () => {
    const p = partyFromRaw({
      roster: [{
        name: "Legolas", class: "Thief", hp: 18,
        equipped: { right_hand: "Long Bow", left_hand: null, body: null, head: null },
      }],
      inventory: [],
    });
    const m = p.roster[0];
    m.equipped.leftHand = "Round Shield";
    expect(swapToMeleeIfOutOfAmmo(m, p, stackingItems())).toBeNull();
    expect(m.equipped.rightHand).toBe("Long Bow");
  });

  it("no-op when there's nothing in the offhand at all", () => {
    const p = partyFromRaw({
      roster: [{
        name: "Legolas", class: "Thief", hp: 18,
        equipped: { right_hand: "Long Bow", left_hand: null, body: null, head: null },
      }],
      inventory: [],
    });
    const m = p.roster[0];
    expect(swapToMeleeIfOutOfAmmo(m, p, stackingItems())).toBeNull();
    expect(m.equipped.rightHand).toBe("Long Bow");
  });

  it("no-op for a melee right-hand weapon", () => {
    const p = partyFromRaw({
      roster: [{
        name: "Gimli", class: "Fighter", hp: 20,
        equipped: { right_hand: "Sword", left_hand: null, body: null, head: null },
      }],
      inventory: [],
    });
    expect(swapToMeleeIfOutOfAmmo(p.roster[0], p, stackingItems())).toBeNull();
  });
});

describe("migrateUnsupportedSlots (via partyFromRaw / memberFromRaw)", () => {
  // Saves written before the Hands/Body collapse may still hold gear
  // in left_hand / head — slots the player UI no longer surfaces.
  // The load-time migration moves that gear back onto the personal
  // belt so the equipment panel and the data agree on what exists.
  it("moves a left_hand item into personal inventory on load", () => {
    const m = memberFromRaw({
      name: "Legolas", class: "Thief", race: "Elf", hp: 18,
      equipped: { right_hand: "Long Bow", left_hand: "Sword", body: null, head: null },
      inventory: [],
    });
    expect(m.equipped.leftHand).toBeNull();
    expect(m.equipped.rightHand).toBe("Long Bow"); // primary weapon untouched
    expect(m.inventory.map((i) => i.item)).toEqual(["Sword"]);
  });

  it("moves a head item into personal inventory on load", () => {
    const m = memberFromRaw({
      name: "Gimli", class: "Fighter", race: "Dwarf", hp: 20,
      equipped: { right_hand: null, left_hand: null, body: null, head: "Helm" },
      inventory: [],
    });
    expect(m.equipped.head).toBeNull();
    expect(m.inventory.map((i) => i.item)).toEqual(["Helm"]);
  });

  it("migrates both stale slots in one load", () => {
    const m = memberFromRaw({
      name: "X", class: "Fighter", race: "Human", hp: 10,
      equipped: { right_hand: null, left_hand: "Dagger", body: null, head: "Helm" },
      inventory: [{ item: "Healing Herb" }],
    });
    expect(m.equipped.leftHand).toBeNull();
    expect(m.equipped.head).toBeNull();
    // Original belt entry preserved; migrated items appended.
    expect(m.inventory.map((i) => i.item)).toEqual(["Healing Herb", "Dagger", "Helm"]);
  });

  it("is a no-op for a clean save (no double-migration)", () => {
    const m = memberFromRaw({
      name: "X", class: "Fighter", race: "Human", hp: 10,
      equipped: { right_hand: "Sword", left_hand: null, body: "Chain", head: null },
      inventory: [{ item: "Healing Herb" }],
    });
    expect(m.equipped.rightHand).toBe("Sword");
    expect(m.equipped.body).toBe("Chain");
    expect(m.inventory.map((i) => i.item)).toEqual(["Healing Herb"]);
  });
});
