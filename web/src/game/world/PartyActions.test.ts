import { describe, it, expect } from "vitest";
import {
  assignEffectToParty,
  removeEffectFromParty,
  giveStashItemTo,
  returnItemToStash,
  castHealOnTarget,
  castMassHeal,
  classifyMenuCast,
  rollDice,
  statMod,
  equipItemFromInventory,
  equipItemIntoSlot,
  unequipSlot,
} from "./PartyActions";
import { partyFromRaw, type Party, activeMembers } from "./Party";
import type { Effect } from "./Effects";
import { spellFromRaw, type Spell } from "./Spells";
import type { Item } from "./Items";

function makeParty(): Party {
  return partyFromRaw({
    start_position: { col: 0, row: 0 },
    gold: 25,
    roster: [
      { name: "Gimli",   class: "Fighter", race: "Dwarf",   level: 1, hp: 20 },
      { name: "Merry",   class: "Thief",   race: "Halfling",level: 1, hp: 18 },
      { name: "Gandolf", class: "Wizard",  race: "Elf",     level: 1, hp: 16, mp: 10 },
      { name: "Selina",  class: "Cleric",  race: "Human",   level: 1, hp: 18, mp: 12, wisdom: 18 },
    ],
    active_party: [0, 1, 2, 3],
    party_effects: { effect_1: null, effect_2: null, effect_3: null, effect_4: null },
    inventory: [{ item: "Torch" }, { item: "Healing Herb" }, { item: "Lockpick", charges: 5 }],
  });
}

const detectTraps: Effect = {
  id: "detect_traps", name: "Detect Traps", description: "", duration: "permanent",
  requirements: { any_of: [{ class: "Thief", min_level: 1 }] },
};
const racialOnly: Effect = {
  id: "infrav", name: "Infravision", description: "", duration: "permanent",
  requirements: { race: "Orc" },
};

describe("assignEffectToParty", () => {
  it("places an effect into the first empty slot when requirements are met", () => {
    const p = makeParty();
    const r = assignEffectToParty(p, detectTraps, activeMembers(p));
    expect(r.ok).toBe(true);
    expect(p.partyEffects.effect_1).toBe("detect_traps");
  });

  it("refuses when requirements aren't met", () => {
    const p = makeParty();
    const r = assignEffectToParty(p, racialOnly, activeMembers(p));
    expect(r.ok).toBe(false);
    expect(p.partyEffects.effect_1).toBeNull();
  });

  it("treats already-assigned as success no-op", () => {
    const p = makeParty();
    p.partyEffects.effect_2 = "detect_traps";
    const r = assignEffectToParty(p, detectTraps, activeMembers(p));
    expect(r.ok).toBe(true);
    // Slot wasn't moved.
    expect(p.partyEffects.effect_1).toBeNull();
    expect(p.partyEffects.effect_2).toBe("detect_traps");
  });

  it("returns failure when all four slots are full", () => {
    const p = makeParty();
    p.partyEffects = {
      effect_1: "a", effect_2: "b", effect_3: "c", effect_4: "d",
    };
    const r = assignEffectToParty(p, detectTraps, activeMembers(p));
    expect(r.ok).toBe(false);
  });
});

describe("removeEffectFromParty", () => {
  it("clears the slot holding the effect", () => {
    const p = makeParty();
    p.partyEffects.effect_3 = "detect_traps";
    const r = removeEffectFromParty(p, detectTraps);
    expect(r.ok).toBe(true);
    expect(p.partyEffects.effect_3).toBeNull();
  });

  it("returns success no-op when the effect wasn't equipped", () => {
    const p = makeParty();
    const r = removeEffectFromParty(p, detectTraps);
    expect(r.ok).toBe(true);
  });
});

describe("giveStashItemTo / returnItemToStash", () => {
  it("moves a stash item into a member's personal inventory", () => {
    const p = makeParty();
    const r = giveStashItemTo(p, 1, 3); // Healing Herb → Selina (idx 3)
    expect(r.ok).toBe(true);
    expect(p.inventory).toHaveLength(2);
    const selina = p.roster[3];
    expect(selina.inventory.map((i) => i.item)).toEqual(["Healing Herb"]);
  });

  it("rejects an out-of-range stash index", () => {
    const p = makeParty();
    const r = giveStashItemTo(p, 99, 0);
    expect(r.ok).toBe(false);
  });

  it("rejects a recipient slot that has no active member", () => {
    const p = makeParty();
    p.activeParty = [0, 1, 2];
    const r = giveStashItemTo(p, 0, 3);
    expect(r.ok).toBe(false);
  });

  it("returnItemToStash moves an item back from a member to the stash", () => {
    const p = makeParty();
    p.roster[2].inventory.push({ item: "Wand" });
    const r = returnItemToStash(p, 2, 0);
    expect(r.ok).toBe(true);
    expect(p.inventory.find((i) => i.item === "Wand")).toBeTruthy();
  });
});

const heal: Spell = spellFromRaw({
  id: "heal", name: "Heal", description: "",
  allowable_classes: ["Cleric"], casting_type: "priest",
  min_level: 1, mp_cost: 4, duration: "instant",
  effect_type: "heal",
  effect_value: { dice_count: 1, dice_sides: 8, stat_bonus: "wisdom" },
  usable_in: ["battle", "town", "overworld", "dungeon"],
});

const massHeal: Spell = spellFromRaw({
  id: "mass_heal", name: "Mass Heal", description: "",
  allowable_classes: ["Cleric"], casting_type: "priest",
  min_level: 3, mp_cost: 8, duration: "instant",
  effect_type: "mass_heal",
  effect_value: { dice_count: 1, dice_sides: 6 },
  usable_in: ["battle", "town", "overworld", "dungeon"],
});

describe("classifyMenuCast", () => {
  it("classifies single-target heal as single-ally", () => {
    expect(classifyMenuCast(heal)).toBe("single-ally");
  });
  it("classifies mass_heal as mass", () => {
    expect(classifyMenuCast(massHeal)).toBe("mass");
  });
  it("classifies unknown effect_type as unsupported", () => {
    const k = spellFromRaw({
      id: "k", name: "Knock", description: "", allowable_classes: ["Wizard"],
      casting_type: "sorcerer", min_level: 1, mp_cost: 4, duration: "instant",
      effect_type: "knock", usable_in: ["dungeon"],
    });
    expect(classifyMenuCast(k)).toBe("unsupported");
  });
});

describe("castHealOnTarget", () => {
  it("heals a wounded ally and spends MP from the chosen caster", () => {
    const p = makeParty();
    const members = activeMembers(p);
    // Wound Gimli
    members[0].hp = 10;
    const beforeMp = members[3].mp ?? 0;
    // Stable RNG → dice rolls 1 -> 1d8 = 1, +WIS mod (18 → +4) = 5 hp.
    const r = castHealOnTarget(p, members, heal, 0, () => 0);
    expect(r.ok).toBe(true);
    expect(members[0].hp).toBeGreaterThan(10);
    expect(members[3].mp).toBe(beforeMp - heal.mp_cost);
  });

  it("refuses to heal a dead member", () => {
    const p = makeParty();
    const members = activeMembers(p);
    members[1].hp = 0;
    const r = castHealOnTarget(p, members, heal, 1, () => 0);
    expect(r.ok).toBe(false);
  });

  it("caps healed HP at maxHp", () => {
    const p = makeParty();
    const members = activeMembers(p);
    members[0].hp = members[0].maxHp - 1;
    castHealOnTarget(p, members, heal, 0, () => 0.99);
    expect(members[0].hp).toBe(members[0].maxHp);
  });

  it("fails gracefully when no qualified caster exists", () => {
    const p = makeParty();
    const members = activeMembers(p);
    members[3].mp = 0; // drain Selina
    const r = castHealOnTarget(p, members, heal, 0);
    expect(r.ok).toBe(false);
  });
});

describe("castMassHeal", () => {
  it("heals every alive member and spends MP once", () => {
    const p = makeParty();
    const members = activeMembers(p);
    members[3].level = 3; // mass_heal min_level is 3
    members[0].hp = 5; members[1].hp = 8; members[2].hp = 3; members[3].hp = 4;
    const beforeMp = members[3].mp ?? 0;
    const r = castMassHeal(p, members, massHeal, () => 0);
    expect(r.ok).toBe(true);
    expect(members[3].mp).toBe(beforeMp - massHeal.mp_cost);
    expect(members[0].hp).toBeGreaterThan(5);
    expect(members[3].hp).toBeGreaterThan(4);
  });

  it("skips dead members", () => {
    const p = makeParty();
    const members = activeMembers(p);
    members[3].level = 3;
    members[0].hp = 0;
    members[1].hp = 5; members[2].hp = 5; members[3].hp = 5;
    castMassHeal(p, members, massHeal, () => 0);
    expect(members[0].hp).toBe(0);
  });

  it("fails when no caster meets the spell's min_level", () => {
    const p = makeParty();
    const r = castMassHeal(p, activeMembers(p), massHeal, () => 0);
    expect(r.ok).toBe(false);
  });
});

describe("equipItemFromInventory / unequipSlot", () => {
  function items(): Map<string, Item> {
    const m = new Map<string, Item>();
    m.set("Dagger", {
      name: "Dagger", category: "weapons", description: "",
      slots: ["right_hand", "left_hand"],
      characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null,
    });
    m.set("Sword", {
      name: "Sword", category: "weapons", description: "",
      slots: ["right_hand"],
      characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null,
    });
    m.set("Round Shield", {
      name: "Round Shield", category: "armors", description: "",
      slots: ["left_hand"],
      characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null,
    });
    m.set("Cloth", {
      name: "Cloth", category: "armors", description: "",
      slots: ["body"], characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null,
    });
    m.set("Healing Herb", {
      name: "Healing Herb", category: "general", description: "",
      slots: [], characterCanEquip: false, partyCanEquip: false,
      usable: true, effect: "heal_hp",
    });
    return m;
  }

  it("equips a weapon into the first empty matching slot", () => {
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.inventory.push({ item: "Dagger" });
    fighter.equipped.rightHand = "Fists";
    // right_hand has Fists, left_hand is null → Dagger lands in left.
    const r = equipItemFromInventory(fighter, 0, items());
    expect(r.ok).toBe(true);
    expect(fighter.equipped.leftHand).toBe("Dagger");
    expect(fighter.equipped.rightHand).toBe("Fists");
    expect(fighter.inventory).toEqual([]);
  });

  it("auto-swaps when every accepting slot is already full", () => {
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.equipped.rightHand = "Fists"; // only slot for Sword
    fighter.inventory.push({ item: "Sword" });
    const r = equipItemFromInventory(fighter, 0, items());
    expect(r.ok).toBe(true);
    expect(fighter.equipped.rightHand).toBe("Sword");
    expect(fighter.inventory.map((i) => i.item)).toEqual(["Fists"]);
  });

  it("equips body armor into the body slot", () => {
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.equipped.body = null;
    fighter.inventory.push({ item: "Cloth" });
    const r = equipItemFromInventory(fighter, 0, items());
    expect(r.ok).toBe(true);
    expect(fighter.equipped.body).toBe("Cloth");
  });

  it("refuses non-equippable items politely", () => {
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.inventory.push({ item: "Healing Herb" });
    const r = equipItemFromInventory(fighter, 0, items());
    expect(r.ok).toBe(false);
    expect(fighter.inventory).toHaveLength(1); // unchanged
  });

  it("refuses items not in the catalog", () => {
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.inventory.push({ item: "Mythril Plate" });
    const r = equipItemFromInventory(fighter, 0, items());
    expect(r.ok).toBe(false);
  });

  it("refuses an out-of-range itemIndex", () => {
    const p = makeParty();
    expect(equipItemFromInventory(p.roster[0], 99, items()).ok).toBe(false);
  });

  it("unequipSlot moves the slot's item back to inventory", () => {
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.equipped.body = "Cloth";
    const r = unequipSlot(fighter, "body");
    expect(r.ok).toBe(true);
    expect(fighter.equipped.body).toBeNull();
    expect(fighter.inventory.map((i) => i.item)).toEqual(["Cloth"]);
  });

  it("unequipSlot is a success no-op when the slot is empty", () => {
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.equipped.head = null;
    const r = unequipSlot(fighter, "head");
    expect(r.ok).toBe(true);
    expect(fighter.inventory).toEqual([]);
  });

  it("equipItemIntoSlot honours an explicit slot choice", () => {
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.equipped.rightHand = null;
    fighter.equipped.leftHand = null;
    fighter.inventory.push({ item: "Dagger" });
    // Dagger can go in either hand — pick left explicitly.
    const r = equipItemIntoSlot(fighter, 0, "left_hand", items());
    expect(r.ok).toBe(true);
    expect(fighter.equipped.leftHand).toBe("Dagger");
    expect(fighter.equipped.rightHand).toBeNull();
    expect(fighter.inventory).toEqual([]);
  });

  it("equipItemIntoSlot rejects a slot the item doesn't accept", () => {
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.inventory.push({ item: "Dagger" });
    // Dagger's slots are right/left hand only — body should refuse.
    const r = equipItemIntoSlot(fighter, 0, "body", items());
    expect(r.ok).toBe(false);
    expect(fighter.equipped.body).toBeNull();
    expect(fighter.inventory).toHaveLength(1);
  });

  it("equipItemIntoSlot swaps the existing occupant of the chosen slot", () => {
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.equipped.rightHand = "Sword";
    fighter.inventory.push({ item: "Dagger" });
    const r = equipItemIntoSlot(fighter, 0, "right_hand", items());
    expect(r.ok).toBe(true);
    expect(fighter.equipped.rightHand).toBe("Dagger");
    expect(fighter.inventory.map((i) => i.item)).toEqual(["Sword"]);
  });

  it("equipItemIntoSlot refuses a non-equippable consumable", () => {
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.inventory.push({ item: "Healing Herb" });
    const r = equipItemIntoSlot(fighter, 0, "right_hand", items());
    expect(r.ok).toBe(false);
  });
});

describe("rollDice / statMod", () => {
  it("rollDice with rng=0 always rolls 1 per die", () => {
    expect(rollDice(3, 8, () => 0)).toBe(3);
  });
  it("rollDice with rng=0.99 rolls max per die", () => {
    expect(rollDice(2, 6, () => 0.99)).toBe(12);
  });
  it("statMod follows D&D conventions", () => {
    expect(statMod(10)).toBe(0);
    expect(statMod(18)).toBe(4);
    expect(statMod(9)).toBe(-1);
    expect(statMod(8)).toBe(-1);
    expect(statMod(7)).toBe(-2);
  });
});
