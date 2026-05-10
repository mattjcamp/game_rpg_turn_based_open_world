import { describe, it, expect } from "vitest";
import {
  assignEffectToParty,
  removeEffectFromParty,
  giveStashItemTo,
  returnItemToStash,
  castHealOnTarget,
  castMassHeal,
  castMagicLight,
  classifyMenuCast,
  summariseActiveEffects,
  rollDice,
  statMod,
  equipItemFromInventory,
  equipItemIntoSlot,
  equippableSlots,
  SUPPORTED_EQUIP_SLOTS,
  unequipSlot,
  hasClass,
  hasRace,
  findClass,
  findRace,
  pickpocket,
  tinker,
  partyHasEffect,
  partyLightRadius,
  partyLightTint,
  tickGaladrielsLight,
  getItemMaxDurability,
  getSlotDurability,
  isIndestructible,
  useEquippedDurability,
  consumeCampingSupplies,
  consumeTorch,
} from "./PartyActions";
import { memberFromRaw } from "./Party";
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

const lightSpell: Spell = spellFromRaw({
  id: "light", name: "Light", description: "",
  allowable_classes: ["Cleric", "Paladin", "Druid"],
  casting_type: "priest",
  min_level: 1, mp_cost: 3, duration: 100,
  effect_type: "magic_light",
  effect_value: { steps: 100 },
  range: 0, targeting: "self",
  usable_in: ["dungeon"],
});

describe("classifyMenuCast", () => {
  it("classifies single-target heal as single-ally", () => {
    expect(classifyMenuCast(heal)).toBe("single-ally");
  });
  it("classifies mass_heal as mass", () => {
    expect(classifyMenuCast(massHeal)).toBe("mass");
  });
  it("classifies magic_light (Light) as self", () => {
    expect(classifyMenuCast(lightSpell)).toBe("self");
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

describe("castMagicLight (Light)", () => {
  it("adds the spell's steps to magicLightSteps and spends MP", () => {
    const p = makeParty();
    const members = activeMembers(p);
    expect(p.magicLightSteps).toBe(0);
    const beforeMp = members[3].mp ?? 0;
    const r = castMagicLight(p, members, lightSpell);
    expect(r.ok).toBe(true);
    expect(p.magicLightSteps).toBe(100);
    expect(members[3].mp).toBe(beforeMp - lightSpell.mp_cost);
    expect(r.message).toContain("Light");
    expect(r.message).toContain("Selina"); // Cleric is the eligible caster
  });

  it("does NOT stack on top of an active physical torch", () => {
    // Casting Light should leave torchSteps alone — the two counters
    // are tracked separately so the HUD readout can show them as
    // distinct entries.
    const p = makeParty();
    p.torchSteps = 40; // simulate a half-burnt torch
    castMagicLight(p, activeMembers(p), lightSpell);
    expect(p.torchSteps).toBe(40);
    expect(p.magicLightSteps).toBe(100);
  });

  it("stacks with prior Light casts on the magic counter only", () => {
    const p = makeParty();
    p.magicLightSteps = 50; // a prior Light still burning
    castMagicLight(p, activeMembers(p), lightSpell);
    expect(p.magicLightSteps).toBe(150);
    expect(p.torchSteps).toBe(0);
  });

  it("falls back to 100 steps when effect_value.steps is missing", () => {
    const p = makeParty();
    const noSteps = spellFromRaw({
      id: "light", name: "Light", description: "",
      allowable_classes: ["Cleric"], casting_type: "priest",
      min_level: 1, mp_cost: 3, duration: "instant",
      effect_type: "magic_light",
      // intentionally omit effect_value
      usable_in: ["dungeon"],
    });
    castMagicLight(p, activeMembers(p), noSteps);
    expect(p.magicLightSteps).toBe(100);
  });

  it("prefers the highest-level caster (then most MP)", () => {
    const p = makeParty();
    const members = activeMembers(p);
    // Add a second cleric at higher level so the priority rule has work to do.
    members[3].level = 3;
    // Pretend Selina has less MP than the (synthetic) lower-level cleric
    members[3].mp = 5;
    // Replace Gandolf with another Cleric at level 1 to act as a worse pick.
    members[2].class = "Cleric";
    members[2].mp = 12;
    members[2].maxMp = 12;
    castMagicLight(p, members, lightSpell);
    // High level Selina spent the MP, not the level-1 Cleric
    expect(members[3].mp).toBe(5 - lightSpell.mp_cost);
    expect(members[2].mp).toBe(12);
  });

  it("fails when no caster has the class + MP to cast", () => {
    const p = makeParty();
    const members = activeMembers(p);
    members[3].mp = 0;  // drain Selina, the only Cleric
    const before = p.magicLightSteps;
    const r = castMagicLight(p, members, lightSpell);
    expect(r.ok).toBe(false);
    expect(p.magicLightSteps).toBe(before);
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

  it("equips a weapon into the hands slot when it's empty", () => {
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.inventory.push({ item: "Dagger" });
    fighter.equipped.rightHand = null;
    // The collapsed-UI model treats right_hand as "Hands" — a Dagger
    // (whose data lists both hands) only targets right_hand, so an
    // empty Hands slot is filled directly without a swap.
    const r = equipItemFromInventory(fighter, 0, items());
    expect(r.ok).toBe(true);
    expect(fighter.equipped.rightHand).toBe("Dagger");
    // Offhand stays untouched and isn't auto-filled — it's no longer
    // surfaced in the UI and `equippableSlots(Dagger)` returns just
    // the right hand.
    expect(fighter.equipped.leftHand).toBeNull();
    expect(fighter.inventory).toEqual([]);
  });

  it("a Dagger equipped while a Sword is in Hands swaps the Sword back to inventory", () => {
    // The user's reported flow: Gimli starts combat with Sword
    // in Hands, equips a Dagger from his belt. Result: Dagger in
    // Hands, Sword on the belt — NOT Sword in Hands and Dagger in
    // Offhand (the pre-collapse UI showed that confusing layout).
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.equipped.rightHand = "Sword";
    fighter.inventory.push({ item: "Dagger" });
    const r = equipItemFromInventory(fighter, 0, items());
    expect(r.ok).toBe(true);
    expect(fighter.equipped.rightHand).toBe("Dagger");
    expect(fighter.equipped.leftHand).toBeNull();
    expect(fighter.inventory.map((i) => i.item)).toEqual(["Sword"]);
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
    fighter.inventory.push({ item: "Dagger" });
    // The Hands slot is right_hand — pick it explicitly.
    const r = equipItemIntoSlot(fighter, 0, "right_hand", items());
    expect(r.ok).toBe(true);
    expect(fighter.equipped.rightHand).toBe("Dagger");
    expect(fighter.inventory).toEqual([]);
  });

  it("equipItemIntoSlot refuses an explicit left_hand pick (offhand isn't surfaced)", () => {
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.inventory.push({ item: "Dagger" });
    // The Dagger's catalog data still lists left_hand, but the UI
    // doesn't surface it — direct picks for offhand should refuse so
    // a stale caller can't re-introduce the confusing offhand layout.
    const r = equipItemIntoSlot(fighter, 0, "left_hand", items());
    expect(r.ok).toBe(false);
    expect(fighter.equipped.leftHand).toBeNull();
    expect(fighter.inventory).toHaveLength(1);
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

  it("combat-context equip swap returns the previous slot occupant to personal inventory", () => {
    // The user's spec for combat-time Equip Item: whatever was in the
    // slot before the swap should land back on the fighter's belt
    // rather than being dropped or destroyed. equipItemFromInventory
    // is the helper the combat scene calls, so this is the canonical
    // place to pin the contract.
    const p = makeParty();
    const fighter = p.roster[0];
    // Sword's only slot is right_hand. Filling that slot forces the
    // swap branch when we equip a fresh Sword from inventory.
    fighter.equipped.rightHand = "Fists";
    fighter.inventory.push({ item: "Sword" });
    const r = equipItemFromInventory(fighter, 0, items());
    expect(r.ok).toBe(true);
    // New item is equipped …
    expect(fighter.equipped.rightHand).toBe("Sword");
    // … and the previous occupant is back on the belt at the same
    // index the new item came from (the "stable view" rule).
    expect(fighter.inventory.map((i) => i.item)).toEqual(["Fists"]);
  });

  it("equip preserves durability on the swapped-out item", () => {
    // If the previous Sword had 7/20 durability remaining, that wear
    // should ride along on the inventory entry it lands on so picking
    // it back up doesn't reset to full.
    const cat = items();
    cat.set("Sword", {
      name: "Sword", category: "weapons", description: "",
      slots: ["right_hand"],
      characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null, durability: 20,
    });
    cat.set("Battle Axe", {
      name: "Battle Axe", category: "weapons", description: "",
      slots: ["right_hand"],
      characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null, durability: 20,
    });
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.equipped.rightHand = "Sword";
    fighter.equippedDurability.right_hand = 7;
    fighter.inventory.push({ item: "Battle Axe" });
    const r = equipItemFromInventory(fighter, 0, cat);
    expect(r.ok).toBe(true);
    // Battle Axe is now in right_hand with full durability seeded …
    expect(fighter.equipped.rightHand).toBe("Battle Axe");
    expect(fighter.equippedDurability.right_hand).toBe(20);
    // … and the swapped-out Sword carries its wear back into the slot
    // the Battle Axe came from.
    expect(fighter.inventory).toEqual([{ item: "Sword", durability: 7 }]);
  });

  it("refuses a head-only item (head slot isn't surfaced in the UI yet)", () => {
    const cat = items();
    cat.set("Helm", {
      name: "Helm", category: "armors", description: "",
      slots: ["head"], characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null, evasion: 50,
    });
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.inventory.push({ item: "Helm" });
    const r = equipItemFromInventory(fighter, 0, cat);
    expect(r.ok).toBe(false);
    // Head-only items refuse cleanly and stay in inventory until the
    // helmet UI lands.
    expect(fighter.equipped.head).toBeNull();
    expect(fighter.inventory).toEqual([{ item: "Helm" }]);
  });

  it("multi-slot items keep their non-head slots", () => {
    // A hypothetical mixed item that lists both `right_hand` and
    // `head` should still equip into the hand, ignoring the
    // currently-unsupported head option.
    const cat = items();
    cat.set("Crowned Spear", {
      name: "Crowned Spear", category: "weapons", description: "",
      slots: ["right_hand", "head"],
      characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null, power: 5,
    });
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.equipped.rightHand = null;
    fighter.inventory.push({ item: "Crowned Spear" });
    const r = equipItemFromInventory(fighter, 0, cat);
    expect(r.ok).toBe(true);
    expect(fighter.equipped.rightHand).toBe("Crowned Spear");
  });

  it("equipItemIntoSlot refuses an explicit head pick (slot not yet surfaced)", () => {
    const cat = items();
    cat.set("Helm", {
      name: "Helm", category: "armors", description: "",
      slots: ["head"], characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null, evasion: 50,
    });
    const p = makeParty();
    const fighter = p.roster[0];
    fighter.inventory.push({ item: "Helm" });
    const r = equipItemIntoSlot(fighter, 0, "head", cat);
    expect(r.ok).toBe(false);
    expect(fighter.equipped.head).toBeNull();
  });
});

describe("equippableSlots / SUPPORTED_EQUIP_SLOTS", () => {
  function mk(slots: ("right_hand" | "left_hand" | "body" | "head")[], over: Partial<Item> = {}): Item {
    return {
      name: "X", category: "general", description: "", slots,
      characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null, ...over,
    };
  }

  it("supports the two currently-shipped slots (Hands + Body)", () => {
    expect([...SUPPORTED_EQUIP_SLOTS].sort())
      .toEqual(["body", "right_hand"].sort());
  });

  it("filters head and left_hand out of an item's slot list", () => {
    // Both head and offhand stay in the EquipSlot type for forward
    // compat but neither is surfaced to the player; equippableSlots
    // hides them so daggers (`right_hand` + `left_hand`) end up in
    // the Hands slot only.
    expect(equippableSlots(mk(["head"]))).toEqual([]);
    expect(equippableSlots(mk(["left_hand"]))).toEqual([]);
    expect(equippableSlots(mk(["right_hand", "left_hand"]))).toEqual(["right_hand"]);
    expect(equippableSlots(mk(["right_hand", "head"]))).toEqual(["right_hand"]);
    expect(equippableSlots(mk(["body", "head"]))).toEqual(["body"]);
  });

  it("preserves order for fully-supported items", () => {
    // With only right_hand + body in the supported set the practical
    // case is a single-slot item, but the filter keeps order if a
    // future item lists both.
    expect(equippableSlots(mk(["right_hand", "body"])))
      .toEqual(["right_hand", "body"]);
  });

  it("returns [] for items the catalog says aren't character-equippable", () => {
    expect(equippableSlots(mk(["right_hand"], { characterCanEquip: false })))
      .toEqual([]);
  });
});

describe("durability — read helpers", () => {
  function items(): Map<string, Item> {
    const m = new Map<string, Item>();
    m.set("Dagger", {
      name: "Dagger", category: "weapons", description: "",
      slots: ["right_hand", "left_hand"],
      characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null,
      durability: 20,
    });
    m.set("Fists", {
      name: "Fists", category: "weapons", description: "",
      slots: ["right_hand"],
      characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null,
      durability: 0,                    // 0 → indestructible
    });
    m.set("Cloth", {
      name: "Cloth", category: "armors", description: "",
      slots: ["body"], characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null,      // missing durability → indestructible
    });
    return m;
  }

  it("getItemMaxDurability reads the catalog max", () => {
    expect(getItemMaxDurability("Dagger", items())).toBe(20);
  });

  it("getItemMaxDurability returns null for indestructible items", () => {
    expect(getItemMaxDurability("Fists", items())).toBeNull();
    expect(getItemMaxDurability("Cloth", items())).toBeNull();
  });

  it("getItemMaxDurability returns null for unknown items", () => {
    expect(getItemMaxDurability("Mythril Plate", items())).toBeNull();
  });

  it("isIndestructible matches the catalog", () => {
    expect(isIndestructible("Dagger", items())).toBe(false);
    expect(isIndestructible("Fists", items())).toBe(true);
    expect(isIndestructible("Cloth", items())).toBe(true);
  });
});

describe("durability — useEquippedDurability + break", () => {
  function items(): Map<string, Item> {
    const m = new Map<string, Item>();
    m.set("Dagger", {
      name: "Dagger", category: "weapons", description: "",
      slots: ["right_hand"], characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null,
      durability: 3,
    });
    m.set("Fists", {
      name: "Fists", category: "weapons", description: "",
      slots: ["right_hand"], characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null,
      durability: 0,
    });
    return m;
  }

  it("decrements once per call, reporting current/max", () => {
    const p = makeParty();
    const m = p.roster[0];
    m.equipped.rightHand = "Dagger";
    m.equippedDurability.right_hand = 3;
    const r1 = useEquippedDurability(m, "right_hand", items());
    expect(r1.kind).toBe("ok");
    if (r1.kind === "ok") {
      expect(r1.current).toBe(2);
      expect(r1.max).toBe(3);
    }
    expect(m.equippedDurability.right_hand).toBe(2);
  });

  it("returns indestructible for items with durability 0", () => {
    const p = makeParty();
    const m = p.roster[0];
    m.equipped.rightHand = "Fists";
    const r = useEquippedDurability(m, "right_hand", items());
    expect(r.kind).toBe("indestructible");
  });

  it("breaks the item when durability reaches 0 and clears the slot", () => {
    const p = makeParty();
    const m = p.roster[0];
    m.equipped.rightHand = "Dagger";
    m.equippedDurability.right_hand = 1;
    const r = useEquippedDurability(m, "right_hand", items());
    expect(r.kind).toBe("broke");
    if (r.kind === "broke") expect(r.itemName).toBe("Dagger");
    expect(m.equipped.rightHand).toBeNull();
    expect(m.equippedDurability.right_hand).toBeNull();
    // Broken item is destroyed — does NOT return to inventory.
    expect(m.inventory.find((it) => it.item === "Dagger")).toBeUndefined();
  });

  it("seeds durability lazily on first use", () => {
    const p = makeParty();
    const m = p.roster[0];
    m.equipped.rightHand = "Dagger";
    // No tracker entry yet — first use should seed to max-1 (it
    // initialises and then ticks the same call).
    expect(m.equippedDurability.right_hand).toBeNull();
    const r = useEquippedDurability(m, "right_hand", items());
    expect(r.kind).toBe("ok");
    expect(m.equippedDurability.right_hand).toBe(2); // 3 - 1
  });
});

describe("durability — equip / unequip preserves wear", () => {
  function items(): Map<string, Item> {
    const m = new Map<string, Item>();
    m.set("Dagger", {
      name: "Dagger", category: "weapons", description: "",
      slots: ["right_hand", "left_hand"],
      characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null,
      durability: 20,
    });
    m.set("Sword", {
      name: "Sword", category: "weapons", description: "",
      slots: ["right_hand"],
      characterCanEquip: true, partyCanEquip: false,
      usable: false, effect: null,
      durability: 30,
    });
    return m;
  }

  it("equip seeds the slot durability from the inventory entry's value", () => {
    const p = makeParty();
    const m = p.roster[0];
    m.equipped.rightHand = null;
    m.inventory.push({ item: "Dagger", durability: 7 });
    const r = equipItemFromInventory(m, 0, items());
    expect(r.ok).toBe(true);
    expect(m.equippedDurability.right_hand).toBe(7);
  });

  it("equip seeds to max when the inventory entry has no durability set", () => {
    const p = makeParty();
    const m = p.roster[0];
    m.equipped.rightHand = null;
    m.inventory.push({ item: "Dagger" });
    equipItemFromInventory(m, 0, items());
    expect(m.equippedDurability.right_hand).toBe(20);
  });

  it("unequip carries the current durability onto the new inventory entry", () => {
    const p = makeParty();
    const m = p.roster[0];
    m.equipped.rightHand = "Dagger";
    m.equippedDurability.right_hand = 5;
    const r = unequipSlot(m, "right_hand", items());
    expect(r.ok).toBe(true);
    const moved = m.inventory.find((it) => it.item === "Dagger");
    expect(moved?.durability).toBe(5);
    // Slot tracker is cleared after unequip.
    expect(m.equippedDurability.right_hand).toBeNull();
  });

  it("swap preserves the displaced item's durability into inventory", () => {
    const p = makeParty();
    const m = p.roster[0];
    m.equipped.rightHand = "Sword";
    m.equippedDurability.right_hand = 12;
    m.inventory.push({ item: "Dagger", durability: 8 });
    const r = equipItemIntoSlot(m, 0, "right_hand", items());
    expect(r.ok).toBe(true);
    expect(m.equipped.rightHand).toBe("Dagger");
    expect(m.equippedDurability.right_hand).toBe(8);
    // Displaced sword now in the inventory at the same index, with
    // its 12-uses-remaining wear preserved.
    const sword = m.inventory.find((it) => it.item === "Sword");
    expect(sword?.durability).toBe(12);
  });

  it("durability survives a full equip → use → unequip round-trip", () => {
    const p = makeParty();
    const m = p.roster[0];
    m.equipped.rightHand = null;
    m.inventory.push({ item: "Dagger", durability: 10 });
    equipItemFromInventory(m, 0, items());
    expect(m.equippedDurability.right_hand).toBe(10);
    // Use it three times.
    useEquippedDurability(m, "right_hand", items());
    useEquippedDurability(m, "right_hand", items());
    useEquippedDurability(m, "right_hand", items());
    expect(m.equippedDurability.right_hand).toBe(7);
    unequipSlot(m, "right_hand", items());
    const back = m.inventory.find((it) => it.item === "Dagger");
    expect(back?.durability).toBe(7);
    // And re-equipping respects that tracked wear.
    const idx = m.inventory.findIndex((it) => it.item === "Dagger");
    equipItemFromInventory(m, idx, items());
    expect(m.equippedDurability.right_hand).toBe(7);
  });

  it("getSlotDurability reflects current/max for an equipped slot", () => {
    const p = makeParty();
    const m = p.roster[0];
    m.equipped.rightHand = "Dagger";
    m.equippedDurability.right_hand = 11;
    expect(getSlotDurability(m, "right_hand", items())).toEqual({ current: 11, max: 20 });
  });

  it("getSlotDurability returns null for indestructible / empty slots", () => {
    const p = makeParty();
    const m = p.roster[0];
    m.equipped.body = null;
    expect(getSlotDurability(m, "body", items())).toBeNull();
  });
});

describe("party-comp helpers", () => {
  const members = [
    memberFromRaw({ name: "Gimli",  class: "Fighter",   race: "Dwarf",   level: 1, hp: 20 }),
    memberFromRaw({ name: "Merry",  class: "Thief",     race: "Halfling",level: 1, hp: 18 }),
    memberFromRaw({ name: "Glim",   class: "Alchemist", race: "Gnome",   level: 1, hp: 16 }),
    memberFromRaw({ name: "Selina", class: "Cleric",    race: "Human",   level: 1, hp: 18 }),
  ];

  it("hasClass / hasRace are case-insensitive", () => {
    expect(hasClass(members, "alchemist")).toBe(true);
    expect(hasClass(members, "ALCHEMIST")).toBe(true);
    expect(hasRace(members,  "Halfling")).toBe(true);
    expect(hasClass(members, "Druid")).toBe(false);
    expect(hasRace(members,  "Orc")).toBe(false);
  });

  it("ignores dead members", () => {
    members[2].hp = 0; // Glim the Gnome Alchemist is down
    expect(hasClass(members, "Alchemist")).toBe(false);
    expect(hasRace(members,  "Gnome")).toBe(false);
    members[2].hp = 16; // restore
  });

  it("findClass / findRace return the first matching live member", () => {
    expect(findClass(members, "Cleric")?.name).toBe("Selina");
    expect(findRace(members,  "Halfling")?.name).toBe("Merry");
    expect(findClass(members, "Druid")).toBeNull();
  });
});

describe("pickpocket / tinker", () => {
  // The standalone `brewPotion` helper retired here — Alchemy is now
  // a recipe-based system in `Potions.ts` with its own test file.

  it("pickpocket either drops gold or pushes an item, depending on the roll", () => {
    const p = makeParty(); // Merry the Halfling is already in the active party
    const members = activeMembers(p);
    const nearby = ["Plainstown|Innkeeper|3,3", "Plainstown|Villager|7,5"];
    const spent = new Set<string>();

    // rng=0 → first row of the loot table (Gold)
    const beforeGold = p.gold;
    const r1 = pickpocket(p, members, nearby, spent, () => 0);
    expect(r1.ok).toBe(true);
    expect(r1.message.toLowerCase()).toContain("gold");
    expect(r1.pickedKey).toBe(nearby[0]);
    expect(p.gold).toBeGreaterThan(beforeGold);

    // Stamp the first NPC as spent and roll again — should pick
    // the second one. rng=0.99 lands on the last loot row (Holy Water).
    spent.add(r1.pickedKey!);
    const beforeInv = p.inventory.length;
    const r2 = pickpocket(p, members, nearby, spent, () => 0.99);
    expect(r2.ok).toBe(true);
    expect(r2.pickedKey).toBe(nearby[1]);
    expect(p.inventory.length).toBeGreaterThan(beforeInv);
  });

  it("pickpocket refuses when no Halfling is present", () => {
    const p = makeParty();
    p.activeParty = [0, 2, 3]; // drop Merry from the active four
    const r = pickpocket(p, activeMembers(p), ["Town|X|0,0"], new Set());
    expect(r.ok).toBe(false);
  });

  it("pickpocket refuses when no NPCs are nearby", () => {
    const p = makeParty();
    const r = pickpocket(p, activeMembers(p), [], new Set());
    expect(r.ok).toBe(false);
    expect(r.message.toLowerCase()).toContain("nearby");
  });

  it("pickpocket refuses when every nearby NPC is already pickpocketed", () => {
    const p = makeParty();
    const members = activeMembers(p);
    const nearby = ["Plainstown|Innkeeper|3,3", "Plainstown|Villager|7,5"];
    const spent = new Set(nearby);
    const beforeGold = p.gold;
    const beforeInv = p.inventory.length;
    const r = pickpocket(p, members, nearby, spent);
    expect(r.ok).toBe(false);
    expect(r.message.toLowerCase()).toContain("already");
    // Loot must NOT have been awarded on a refusal.
    expect(p.gold).toBe(beforeGold);
    expect(p.inventory.length).toBe(beforeInv);
  });

  it("pickpocket picks the first un-spent NPC, skipping spent ones", () => {
    const p = makeParty();
    const members = activeMembers(p);
    const nearby = [
      "Plainstown|Innkeeper|3,3",  // already spent
      "Plainstown|Bard|5,5",        // already spent
      "Plainstown|Villager|7,5",   // fresh — should be picked
    ];
    const spent = new Set([nearby[0], nearby[1]]);
    const r = pickpocket(p, members, nearby, spent, () => 0);
    expect(r.ok).toBe(true);
    expect(r.pickedKey).toBe(nearby[2]);
  });

  it("tinker adds the chosen item to the stash when a Gnome is present", () => {
    const p = makeParty();
    const members = activeMembers(p);
    members[0].race = "Gnome";
    const stock = new Set(["Torch", "Lockpick", "Arrows"]);
    const items = new Map<string, Item>([
      ["Torch", { name: "Torch", category: "general" } as Item],
    ]);
    const before = p.inventory.length;
    const r = tinker(p, members, "Torch", 0, stock, items);
    expect(r.ok).toBe(true);
    expect(r.message).toContain("Torch");
    expect(p.inventory.length).toBe(before + 1);
    expect(p.lastTinkerDay).toBe(0);
  });

  it("tinker refuses when no Gnome is present", () => {
    const p = makeParty();
    const stock = new Set(["Torch"]);
    const items = new Map<string, Item>([
      ["Torch", { name: "Torch", category: "general" } as Item],
    ]);
    const r = tinker(p, activeMembers(p), "Torch", 0, stock, items);
    expect(r.ok).toBe(false);
  });

  it("tinker refuses a second call on the same day, then allows it the next day", () => {
    const p = makeParty();
    const members = activeMembers(p);
    members[0].race = "Gnome";
    const stock = new Set(["Torch", "Lockpick"]);
    const items = new Map<string, Item>([
      ["Torch", { name: "Torch", category: "general" } as Item],
      ["Lockpick", { name: "Lockpick", category: "general" } as Item],
    ]);
    expect(tinker(p, members, "Torch", 5, stock, items).ok).toBe(true);
    // Same day — refused. Stash count must stay put.
    const inventoryAfterFirst = p.inventory.length;
    const second = tinker(p, members, "Lockpick", 5, stock, items);
    expect(second.ok).toBe(false);
    expect(second.message.toLowerCase()).toContain("already tinkered");
    expect(p.inventory.length).toBe(inventoryAfterFirst);
    // Next day — allowed again.
    const third = tinker(p, members, "Lockpick", 6, stock, items);
    expect(third.ok).toBe(true);
    expect(p.lastTinkerDay).toBe(6);
  });

  it("tinker refuses items that aren't in the general-store catalog", () => {
    const p = makeParty();
    const members = activeMembers(p);
    members[0].race = "Gnome";
    const stock = new Set(["Torch"]);
    const items = new Map<string, Item>([
      ["Torch", { name: "Torch", category: "general" } as Item],
      ["Mystic Sword", { name: "Mystic Sword", category: "weapons" } as Item],
    ]);
    const r = tinker(p, members, "Mystic Sword", 0, stock, items);
    expect(r.ok).toBe(false);
    expect(r.message.toLowerCase()).toContain("can tinker");
    // Day stamp must NOT advance on a refusal — the player should
    // still get their daily attempt.
    expect(p.lastTinkerDay).toBeUndefined();
  });

  it("tinker stacks ammo into the existing stash row instead of duplicating", () => {
    const p = makeParty();
    p.inventory.push({ item: "Arrows", charges: 20 });
    const members = activeMembers(p);
    members[0].race = "Gnome";
    const stock = new Set(["Arrows"]);
    const items = new Map<string, Item>([
      ["Arrows", {
        name: "Arrows", category: "general",
        stackable: true, charges: 20,
      } as Item],
    ]);
    const arrowsBefore = p.inventory.filter((it) => it.item === "Arrows").length;
    const r = tinker(p, members, "Arrows", 1, stock, items);
    expect(r.ok).toBe(true);
    // Must NOT spawn a second "Arrows" row — addToStash should
    // merge into the existing one, summing per-stack charges.
    const arrowEntries = p.inventory.filter((it) => it.item === "Arrows");
    expect(arrowEntries.length).toBe(arrowsBefore);
    expect(arrowEntries[0].charges).toBe(40);
  });
});

describe("partyHasEffect / partyLightRadius", () => {
  it("partyHasEffect inspects the effect_N slots", () => {
    const p = makeParty();
    expect(partyHasEffect(p, "infravision")).toBe(false);
    p.partyEffects.effect_2 = "infravision";
    expect(partyHasEffect(p, "infravision")).toBe(true);
  });

  it("partyLightRadius bumps for Infravision", () => {
    const p = makeParty();
    expect(partyLightRadius(p, 2)).toBe(2);
    p.partyEffects.effect_1 = "infravision";
    expect(partyLightRadius(p, 2)).toBe(8);
  });

  it("partyLightRadius bumps less for Galadriel's Light", () => {
    const p = makeParty();
    p.partyEffects.effect_1 = "galadriels_light";
    expect(partyLightRadius(p, 2)).toBe(5);
  });

  it("Infravision wins over Galadriel's Light when both are equipped", () => {
    const p = makeParty();
    p.partyEffects.effect_1 = "galadriels_light";
    p.partyEffects.effect_2 = "infravision";
    expect(partyLightRadius(p, 2)).toBe(8);
  });

  it("never shrinks below the supplied default radius", () => {
    const p = makeParty();
    p.partyEffects.effect_1 = "galadriels_light"; // boost = 5
    expect(partyLightRadius(p, 9)).toBe(9);       // already brighter, keep it
  });

  it("partyLightTint returns null when no tint effect is active", () => {
    const p = makeParty();
    expect(partyLightTint(p)).toBeNull();
    p.partyEffects.effect_1 = "detect_traps"; // not a tint effect
    expect(partyLightTint(p)).toBeNull();
  });

  it("partyLightTint returns the infrared red for Infravision", () => {
    const p = makeParty();
    p.partyEffects.effect_1 = "infravision";
    const t = partyLightTint(p);
    expect(t?.color).toBe(0xc02020);
    expect(t?.alphaScale).toBeGreaterThan(0);
  });

  it("partyLightTint returns the moonlight blue for Galadriel's Light", () => {
    const p = makeParty();
    p.partyEffects.effect_2 = "galadriels_light";
    const t = partyLightTint(p);
    expect(t?.color).toBe(0x9bb6e0);
  });

  it("Infravision wins over Galadriel's Light when both are equipped", () => {
    const p = makeParty();
    p.partyEffects.effect_1 = "galadriels_light";
    p.partyEffects.effect_2 = "infravision";
    expect(partyLightTint(p)?.color).toBe(0xc02020);
  });
});

describe("Galadriel's Light step burnout", () => {
  const galadriels: Effect = {
    id: "galadriels_light", name: "Galadriel's Light", description: "",
    duration: 500, requirements: { race: "Elf" },
  };

  it("seeds the step counter from the effect's duration on equip", () => {
    const p = makeParty();
    expect(p.galadrielsLightSteps).toBe(0);
    const r = assignEffectToParty(p, galadriels, activeMembers(p));
    expect(r.ok).toBe(true);
    expect(p.galadrielsLightSteps).toBe(500);
  });

  it("clears the counter when the effect is manually removed", () => {
    const p = makeParty();
    assignEffectToParty(p, galadriels, activeMembers(p));
    expect(p.galadrielsLightSteps).toBe(500);
    removeEffectFromParty(p, galadriels);
    expect(p.galadrielsLightSteps).toBe(0);
    expect(partyHasEffect(p, "galadriels_light")).toBe(false);
  });

  it("ticks one step per call and clears the slot when it hits zero", () => {
    const p = makeParty();
    assignEffectToParty(p, galadriels, activeMembers(p));
    // Burn 499 steps — still active.
    for (let i = 0; i < 499; i++) {
      expect(tickGaladrielsLight(p)).toBe(false);
    }
    expect(p.galadrielsLightSteps).toBe(1);
    expect(partyHasEffect(p, "galadriels_light")).toBe(true);
    // Final tick — fades.
    expect(tickGaladrielsLight(p)).toBe(true);
    expect(p.galadrielsLightSteps).toBe(0);
    expect(partyHasEffect(p, "galadriels_light")).toBe(false);
    // Subsequent ticks are a no-op.
    expect(tickGaladrielsLight(p)).toBe(false);
  });

  it("does nothing when the effect isn't equipped", () => {
    const p = makeParty();
    expect(tickGaladrielsLight(p)).toBe(false);
    expect(p.galadrielsLightSteps).toBe(0);
  });
});

describe("pickpocket gating (helper enforces both adjacency + once-per-NPC)", () => {
  it("the helper refuses outright when the nearby list is empty", () => {
    // Used to live in the scene; moved into the helper so save-game
    // restores can't bypass it on a stale localStorage payload.
    const p = makeParty();
    const r = pickpocket(p, activeMembers(p), [], new Set(), () => 0.5);
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

describe("consumeCampingSupplies", () => {
  function woundedParty(): Party {
    const p = makeParty();
    // Wound everyone, drain the casters' MP.
    for (const m of p.roster) {
      m.hp = 1;
      if (m.maxMp != null) m.mp = 0;
    }
    p.inventory = [{ item: "Camping Supplies", charges: 2 }];
    return p;
  }

  it("fails cleanly when there are no camping supplies in the stash", () => {
    const p = makeParty();
    p.inventory = [{ item: "Healing Herb" }];
    const r = consumeCampingSupplies(p);
    expect(r.ok).toBe(false);
    expect(r.message).toMatch(/no camping/i);
  });

  it("heals every alive member to full HP and refills MP", () => {
    const p = woundedParty();
    const r = consumeCampingSupplies(p);
    expect(r.ok).toBe(true);
    for (const m of p.roster) {
      expect(m.hp).toBe(m.maxHp);
      if (m.maxMp != null) expect(m.mp).toBe(m.maxMp);
    }
  });

  it("decrements the entry's charges and removes it on the last charge", () => {
    const p = woundedParty(); // charges: 2
    consumeCampingSupplies(p);
    expect(p.inventory[0].charges).toBe(1);
    consumeCampingSupplies(p);
    expect(p.inventory).toHaveLength(0);
  });

  it("seeds charges from the catalog default when the entry has none", () => {
    const p = woundedParty();
    p.inventory = [{ item: "Camping Supplies" }]; // no charges
    consumeCampingSupplies(p);
    // Default is 3 → after one use, 2 remain.
    expect(p.inventory[0].charges).toBe(2);
  });

  it("skips downed members", () => {
    const p = woundedParty();
    p.roster[0].hp = 0; // Gimli is down
    consumeCampingSupplies(p);
    expect(p.roster[0].hp).toBe(0);
    expect(p.roster[1].hp).toBe(p.roster[1].maxHp);
  });

  it("reports a no-op when the party is already at full health", () => {
    const p = makeParty();
    p.inventory = [{ item: "Camping Supplies", charges: 1 }];
    const r = consumeCampingSupplies(p);
    expect(r.ok).toBe(true);
    expect(r.message).toMatch(/already whole/i);
  });
});

describe("consumeTorch", () => {
  it("fails cleanly when there are no torches in the stash", () => {
    const p = makeParty();
    p.inventory = [{ item: "Healing Herb" }];
    const r = consumeTorch(p);
    expect(r.ok).toBe(false);
  });

  it("removes one torch and adds 150 light-steps to the counter", () => {
    const p = makeParty();
    p.inventory = [{ item: "Torch" }];
    p.torchSteps = 0;
    const r = consumeTorch(p);
    expect(r.ok).toBe(true);
    expect(p.torchSteps).toBe(150);
    expect(p.inventory.find((it) => it.item === "Torch")).toBeUndefined();
  });

  it("stacks with an already-burning torch (tops the counter back up)", () => {
    const p = makeParty();
    p.inventory = [{ item: "Torch" }];
    p.torchSteps = 25;
    consumeTorch(p);
    expect(p.torchSteps).toBe(175);
  });

  it("honours an entry's partial `charges` count when present", () => {
    const p = makeParty();
    p.inventory = [{ item: "Torch", charges: 40 }];
    p.torchSteps = 0;
    consumeTorch(p);
    expect(p.torchSteps).toBe(40);
  });
});

describe("summariseActiveEffects", () => {
  it("returns an empty list when no party", () => {
    expect(summariseActiveEffects(null)).toEqual([]);
    expect(summariseActiveEffects(undefined)).toEqual([]);
  });

  it("reports the torch counter as a synthetic 'Torch' lighting entry", () => {
    const p = makeParty();
    p.torchSteps = 87;
    const items = summariseActiveEffects(p);
    expect(items).toHaveLength(1);
    expect(items[0]).toEqual({
      id: "",
      name: "Torch",
      isLight: true,
      charges: 87,
    });
  });

  it("omits the torch entry when steps are 0", () => {
    const p = makeParty();
    p.torchSteps = 0;
    expect(summariseActiveEffects(p)).toEqual([]);
  });

  it("reports the Light spell as its own 'Magic Light' lighting entry", () => {
    const p = makeParty();
    p.magicLightSteps = 73;
    const items = summariseActiveEffects(p);
    expect(items).toHaveLength(1);
    expect(items[0]).toEqual({
      id: "",
      name: "Magic Light",
      isLight: true,
      charges: 73,
    });
  });

  it("surfaces Torch and Magic Light side-by-side when both are active", () => {
    const p = makeParty();
    p.torchSteps = 40;
    p.magicLightSteps = 100;
    const items = summariseActiveEffects(p);
    // Both are light entries; sort is alpha within the lights group,
    // so "Magic Light" comes before "Torch".
    expect(items.map((i) => i.name)).toEqual(["Magic Light", "Torch"]);
    expect(items.every((i) => i.isLight)).toBe(true);
    expect(items[0].charges).toBe(100);
    expect(items[1].charges).toBe(40);
  });

  it("includes slotted partyEffects with the fallback display names", () => {
    const p = makeParty();
    p.partyEffects.effect_1 = "detect_traps";
    p.partyEffects.effect_2 = "infravision";
    const items = summariseActiveEffects(p);
    // Infravision is a light; Detect Traps is permanent non-light.
    // Lights sort first.
    expect(items.map((i) => i.name)).toEqual(["Infravision", "Detect Traps"]);
    expect(items[0].isLight).toBe(true);
    expect(items[1].isLight).toBe(false);
    // Permanent effects carry no charges.
    expect(items[0].charges).toBeUndefined();
    expect(items[1].charges).toBeUndefined();
  });

  it("attaches the step counter to Galadriel's Light when active", () => {
    const p = makeParty();
    p.partyEffects.effect_1 = "galadriels_light";
    p.galadrielsLightSteps = 153;
    const items = summariseActiveEffects(p);
    expect(items[0]).toMatchObject({
      id: "galadriels_light",
      name: "Galadriel's Light",
      isLight: true,
      charges: 153,
    });
  });

  it("omits Galadriel's Light charge when its counter is 0", () => {
    const p = makeParty();
    p.partyEffects.effect_1 = "galadriels_light";
    p.galadrielsLightSteps = 0;
    const items = summariseActiveEffects(p);
    expect(items[0].charges).toBeUndefined();
  });

  it("orders lights first, then alphabetical, in mixed cases", () => {
    const p = makeParty();
    p.torchSteps = 50;
    p.partyEffects.effect_1 = "detect_traps";
    p.partyEffects.effect_2 = "galadriels_light";
    p.galadrielsLightSteps = 120;
    const items = summariseActiveEffects(p);
    expect(items.map((i) => i.name)).toEqual([
      "Galadriel's Light",  // light, G < T
      "Torch",              // light
      "Detect Traps",       // non-light
    ]);
    expect(items.filter((i) => i.isLight)).toHaveLength(2);
  });

  it("prefers the loaded effects.json names over the built-in fallback", () => {
    const p = makeParty();
    p.partyEffects.effect_1 = "detect_traps";
    const customEffect: Effect = {
      id: "detect_traps",
      name: "Trap Sense",  // custom override (e.g. a localised module)
      description: "",
      duration: "permanent",
    };
    const items = summariseActiveEffects(p, [customEffect]);
    expect(items[0].name).toBe("Trap Sense");
  });

  it("uses the raw id when neither effects.json nor fallback knows the effect", () => {
    const p = makeParty();
    p.partyEffects.effect_1 = "future_effect_xyz";
    const items = summariseActiveEffects(p);
    expect(items[0].name).toBe("future_effect_xyz");
    expect(items[0].isLight).toBe(false);
  });
});
