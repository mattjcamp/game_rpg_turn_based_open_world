import { describe, it, expect } from "vitest";
import {
  buyItem,
  sellItem,
  shopStockKey,
  getOrSeedShopStock,
} from "./TownActions";
import type { Party } from "./Party";
import type { Item } from "./Items";

function makeParty(overrides: Partial<Party> = {}): Party {
  return {
    roster: [],
    activeParty: [],
    gold: 100,
    inventory: [],
    effects: [],
    ...overrides,
  } as Party;
}

function makeItems(): Map<string, Item> {
  const items = new Map<string, Item>();
  items.set("Healing Potion", { name: "Healing Potion", category: "general", buy: 20, sell: 10 } as Item);
  items.set("Junk Stone",     { name: "Junk Stone",     category: "general", buy: 0,  sell: 0  } as Item);
  return items;
}

describe("shopStockKey", () => {
  it("composes a unique key per (town, shopType) pair", () => {
    expect(shopStockKey("Plainstown", "general")).toBe("Plainstown|general");
    expect(shopStockKey("building:Inside House 2", "weapon"))
      .toBe("building:Inside House 2|weapon");
  });
});

describe("getOrSeedShopStock", () => {
  it("seeds the stock from defaults the first time and returns the live ref", () => {
    const inv = new Map<string, string[]>();
    const stock = getOrSeedShopStock(inv, "Plainstown", "general", ["A", "B"]);
    expect(stock).toEqual(["A", "B"]);
    expect(inv.get("Plainstown|general")).toBe(stock);
    // Mutating the returned array updates the map entry.
    stock.push("C");
    expect(inv.get("Plainstown|general")).toEqual(["A", "B", "C"]);
  });

  it("returns the same reference on subsequent calls (no re-seed)", () => {
    const inv = new Map<string, string[]>();
    const a = getOrSeedShopStock(inv, "X", "y", ["one"]);
    a.length = 0;
    const b = getOrSeedShopStock(inv, "X", "y", ["WRONG_DEFAULTS"]);
    expect(b).toBe(a);
    expect(b).toEqual([]);
  });

  it("does not share state across (town, shopType) pairs", () => {
    const inv = new Map<string, string[]>();
    const a = getOrSeedShopStock(inv, "Plainstown", "general", ["A"]);
    const b = getOrSeedShopStock(inv, "Otherville", "general", ["B"]);
    expect(a).not.toBe(b);
    expect(a).toEqual(["A"]);
    expect(b).toEqual(["B"]);
  });
});

describe("buyItem (finite stock)", () => {
  it("removes the bought item from stock and adds it to the party stash", () => {
    const party = makeParty({ gold: 100 });
    const stock = ["Healing Potion", "Healing Potion"];
    const r = buyItem(party, stock, 0, makeItems());
    expect(r.ok).toBe(true);
    expect(party.gold).toBe(80);
    expect(party.inventory).toEqual([{ item: "Healing Potion" }]);
    expect(stock).toEqual(["Healing Potion"]);
  });

  it("refuses when the index is out of range and leaves stock untouched", () => {
    const party = makeParty();
    const stock = ["Healing Potion"];
    const r = buyItem(party, stock, 5, makeItems());
    expect(r.ok).toBe(false);
    expect(stock).toEqual(["Healing Potion"]);
    expect(party.inventory).toEqual([]);
  });

  it("refuses when the party can't afford it (no stock change)", () => {
    const party = makeParty({ gold: 5 });
    const stock = ["Healing Potion"];
    const r = buyItem(party, stock, 0, makeItems());
    expect(r.ok).toBe(false);
    expect(stock).toEqual(["Healing Potion"]);
    expect(party.gold).toBe(5);
  });

  it("refuses unpriced items without removing them from stock", () => {
    const party = makeParty({ gold: 999 });
    const stock = ["Junk Stone"];
    const r = buyItem(party, stock, 0, makeItems());
    expect(r.ok).toBe(false);
    expect(stock).toEqual(["Junk Stone"]);
  });
});

describe("sellItem (finite stock)", () => {
  it("appends the sold item to shop stock and removes it from party stash", () => {
    const party = makeParty({
      gold: 0,
      inventory: [{ item: "Healing Potion" }],
    });
    const stock: string[] = [];
    const r = sellItem(party, 0, stock, makeItems());
    expect(r.ok).toBe(true);
    expect(party.gold).toBe(10);
    expect(party.inventory).toEqual([]);
    expect(stock).toEqual(["Healing Potion"]);
  });

  it("refuses unsellable items and leaves stock untouched", () => {
    const party = makeParty({
      inventory: [{ item: "Junk Stone" }],
    });
    const stock: string[] = [];
    const r = sellItem(party, 0, stock, makeItems());
    expect(r.ok).toBe(false);
    expect(stock).toEqual([]);
    expect(party.inventory).toEqual([{ item: "Junk Stone" }]);
  });

  it("re-buying a sold item works (the same array round-trips)", () => {
    const party = makeParty({
      gold: 30,
      inventory: [{ item: "Healing Potion" }],
    });
    const stock: string[] = [];
    sellItem(party, 0, stock, makeItems());
    expect(stock).toEqual(["Healing Potion"]);
    expect(party.gold).toBe(40);
    const r = buyItem(party, stock, 0, makeItems());
    expect(r.ok).toBe(true);
    expect(stock).toEqual([]);
    expect(party.gold).toBe(20);
    expect(party.inventory).toEqual([{ item: "Healing Potion" }]);
  });
});
