import { describe, expect, it } from "vitest";
import {
  applyService,
  buildSellRows,
  buildShopRows,
  buyFromShop,
  sellToShop,
} from "./CounterActions";
import type { Counter, ShopService } from "./Counters";
import type { Item } from "./Items";
import type { Party, PartyMember } from "./Party";

function makeMember(overrides: Partial<PartyMember> = {}): PartyMember {
  return {
    name: "Test",
    class: "Fighter",
    race: "Human",
    gender: "M",
    hp: 20, maxHp: 20,
    mp: undefined, maxMp: undefined,
    strength: 10, dexterity: 10, intelligence: 10, wisdom: 10,
    level: 1,
    equipped: { rightHand: null, leftHand: null, body: null, head: null },
    equippedDurability: { right_hand: null, left_hand: null, body: null, head: null },
    inventory: [],
    sprite: "/assets/characters/fighter.png",
    ...overrides,
  };
}

function makeParty(overrides: Partial<Party> = {}): Party {
  return {
    startPosition: { col: 0, row: 0 },
    gold: 100,
    roster: [makeMember()],
    activeParty: [0],
    partyEffects: { effect_1: null, effect_2: null, effect_3: null, effect_4: null },
    inventory: [],
    ...overrides,
  };
}

function makeItems(): Map<string, Item> {
  const items = new Map<string, Item>();
  items.set("Sword", {
    name: "Sword", category: "weapons", description: "A blade.",
    slots: ["right_hand"], characterCanEquip: true, partyCanEquip: false,
    usable: false, effect: null, power: 6,
    buy: 50, sell: 25,
  });
  items.set("Dagger", {
    name: "Dagger", category: "weapons", description: "A short blade.",
    slots: ["right_hand", "left_hand"], characterCanEquip: true, partyCanEquip: false,
    usable: false, effect: null, power: 3,
    buy: 20, sell: 10,
  });
  items.set("Mystery Trinket", {
    name: "Mystery Trinket", category: "general", description: "Quest item.",
    slots: [], characterCanEquip: false, partyCanEquip: false,
    usable: false, effect: null,
  });
  items.set("Healing Herb", {
    name: "Healing Herb", category: "general", description: "Restores HP.",
    slots: [], characterCanEquip: false, partyCanEquip: false,
    usable: true, effect: "heal_hp",
    buy: 5, sell: 2,
  });
  return items;
}

function makeShopCounter(items: string[]): Counter {
  return {
    key: "weapon", name: "Weapons", description: "",
    kind: "shop", items, services: [],
  };
}

const heal: ShopService = {
  id: "heal_all_hp", name: "Heal All HP",
  description: "", cost: 100,
};
const raise: ShopService = {
  id: "raise_dead", name: "Raise Dead",
  description: "", cost: 1000,
};
const restoreMp: ShopService = {
  id: "restore_all_mp", name: "Restore All MP",
  description: "", cost: 75,
};

describe("buildShopRows", () => {
  it("filters out items the catalog doesn't have a price for", () => {
    const rows = buildShopRows(
      makeShopCounter(["Sword", "Mystery Trinket", "Dagger"]),
      makeItems(),
    );
    expect(rows.map((r) => r.itemName)).toEqual(["Sword", "Dagger"]);
    expect(rows[0].price).toBe(50);
    expect(rows[1].price).toBe(20);
  });

  it("returns an empty list when the counter has no resolvable items", () => {
    const rows = buildShopRows(
      makeShopCounter(["Mystery Trinket"]),
      makeItems(),
    );
    expect(rows).toEqual([]);
  });
});

describe("buyFromShop", () => {
  it("debits gold and adds the item to the stash on success", () => {
    const party = makeParty({ gold: 100 });
    const items = makeItems();
    const rows = buildShopRows(makeShopCounter(["Sword"]), items);
    const r = buyFromShop(party, rows[0]);
    expect(r.ok).toBe(true);
    expect(party.gold).toBe(50);
    expect(party.inventory).toEqual([{ item: "Sword" }]);
  });

  it("refuses when the party can't afford it", () => {
    const party = makeParty({ gold: 5 });
    const items = makeItems();
    const rows = buildShopRows(makeShopCounter(["Sword"]), items);
    const r = buyFromShop(party, rows[0]);
    expect(r.ok).toBe(false);
    expect(party.gold).toBe(5);
    expect(party.inventory).toEqual([]);
  });
});

describe("buildSellRows / sellToShop", () => {
  it("builds rows from the live stash and sells back at the listed price", () => {
    const party = makeParty({
      gold: 0,
      inventory: [{ item: "Sword" }, { item: "Healing Herb" }],
    });
    const items = makeItems();
    const rows = buildSellRows(party, items);
    expect(rows.map((r) => r.itemName)).toEqual(["Sword", "Healing Herb"]);
    expect(rows[0].price).toBe(25);
    expect(rows[1].price).toBe(2);

    const r = sellToShop(party, rows[0]);
    expect(r.ok).toBe(true);
    expect(party.gold).toBe(25);
    expect(party.inventory.map((e) => e.item)).toEqual(["Healing Herb"]);
  });

  it("refuses to sell items with no resolvable price (quest tokens, etc.)", () => {
    const party = makeParty({
      inventory: [{ item: "Mystery Trinket" }],
    });
    const rows = buildSellRows(party, makeItems());
    const r = sellToShop(party, rows[0]);
    expect(r.ok).toBe(false);
    expect(party.inventory.length).toBe(1);
  });
});

describe("applyService", () => {
  it("heals every wounded member to full and charges gold", () => {
    const m1 = makeMember({ name: "A", hp: 10, maxHp: 20 });
    const m2 = makeMember({ name: "B", hp: 1, maxHp: 12 });
    const party = makeParty({ gold: 200, roster: [m1, m2], activeParty: [0, 1] });

    const r = applyService(party, heal);

    expect(r.ok).toBe(true);
    expect(party.gold).toBe(100);
    expect(m1.hp).toBe(20);
    expect(m2.hp).toBe(12);
  });

  it("refuses to heal when no one is wounded — no gold spent", () => {
    const m = makeMember({ hp: 20, maxHp: 20 });
    const party = makeParty({ gold: 200, roster: [m], activeParty: [0] });
    const r = applyService(party, heal);
    expect(r.ok).toBe(false);
    expect(party.gold).toBe(200);
  });

  it("refuses to heal when the party can't afford it", () => {
    const m = makeMember({ hp: 5, maxHp: 20 });
    const party = makeParty({ gold: 10, roster: [m], activeParty: [0] });
    const r = applyService(party, heal);
    expect(r.ok).toBe(false);
    expect(party.gold).toBe(10);
    expect(m.hp).toBe(5);
  });

  it("raises the first fallen ally to full", () => {
    const m1 = makeMember({ name: "Alive", hp: 20, maxHp: 20 });
    const m2 = makeMember({ name: "Down", hp: 0, maxHp: 18, mp: 0, maxMp: 6 });
    const party = makeParty({
      gold: 1500, roster: [m1, m2], activeParty: [0, 1],
    });
    const r = applyService(party, raise);
    expect(r.ok).toBe(true);
    expect(party.gold).toBe(500);
    expect(m2.hp).toBe(18);
    expect(m2.mp).toBe(6);
  });

  it("restores every drained caster's MP", () => {
    const caster = makeMember({ name: "Caster", hp: 10, maxHp: 10, mp: 1, maxMp: 8 });
    const fighter = makeMember({ name: "Fighter" });
    const party = makeParty({
      gold: 200, roster: [caster, fighter], activeParty: [0, 1],
    });
    const r = applyService(party, restoreMp);
    expect(r.ok).toBe(true);
    expect(party.gold).toBe(125);
    expect(caster.mp).toBe(8);
  });
});
