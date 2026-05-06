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
  hasClass,
  hasRace,
  findClass,
  findRace,
  brewPotion,
  pickpocket,
  tinker,
  partyHasEffect,
  partyLightRadius,
  partyLightTint,
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

describe("brewPotion / pickpocket / tinker", () => {
  it("brewPotion adds a potion to the stash when an Alchemist is present", () => {
    const p = makeParty();
    const members = activeMembers(p);
    members[0].class = "Alchemist"; // make Gimli an Alchemist for the test
    const before = p.inventory.length;
    // rng = 0 always picks the first weighted entry → Healing Potion
    const r = brewPotion(p, members, () => 0);
    expect(r.ok).toBe(true);
    expect(r.message).toContain("Healing Potion");
    expect(p.inventory.length).toBe(before + 1);
  });

  it("brewPotion refuses when no Alchemist is present", () => {
    const p = makeParty();
    const r = brewPotion(p, activeMembers(p), () => 0);
    expect(r.ok).toBe(false);
  });

  it("pickpocket either drops gold or pushes an item, depending on the roll", () => {
    const p = makeParty(); // Merry the Halfling is already in the active party
    const members = activeMembers(p);

    // rng=0 → first row of the loot table (Gold)
    const beforeGold = p.gold;
    const r1 = pickpocket(p, members, () => 0);
    expect(r1.ok).toBe(true);
    expect(r1.message.toLowerCase()).toContain("gold");
    expect(p.gold).toBeGreaterThan(beforeGold);

    // rng nudged so the weighted-pick lands on a non-Gold row.
    // Calls: pickWeighted uses one rng() call. Easiest: feed 0.99
    // which should land on the last row (Holy Water).
    const beforeInv = p.inventory.length;
    const r2 = pickpocket(p, members, () => 0.99);
    expect(r2.ok).toBe(true);
    expect(p.inventory.length).toBeGreaterThan(beforeInv);
  });

  it("pickpocket refuses when no Halfling is present", () => {
    const p = makeParty();
    p.activeParty = [0, 2, 3]; // drop Merry from the active four
    const r = pickpocket(p, activeMembers(p));
    expect(r.ok).toBe(false);
  });

  it("tinker adds an item to the stash when a Gnome is present", () => {
    const p = makeParty();
    const members = activeMembers(p);
    members[0].race = "Gnome";
    const before = p.inventory.length;
    const r = tinker(p, members, () => 0); // Lockpick (first entry)
    expect(r.ok).toBe(true);
    expect(r.message).toContain("Lockpick");
    expect(p.inventory.length).toBe(before + 1);
  });

  it("tinker refuses when no Gnome is present", () => {
    const p = makeParty();
    const r = tinker(p, activeMembers(p), () => 0);
    expect(r.ok).toBe(false);
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

describe("pickpocket gating (NPC adjacency lives in the scene)", () => {
  it("pickpocket helper itself does NOT check adjacency", () => {
    // The adjacency rule is enforced by the scene before the helper
    // is even called — when it IS called we expect it to do its
    // weighted roll regardless. The scene's own test covers the
    // refusal path.
    const p = makeParty();
    const r = pickpocket(p, activeMembers(p), () => 0.5);
    expect(r.ok).toBe(true);
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
