import { afterEach, describe, expect, it, vi } from "vitest";
import {
  loadCounters,
  isServiceCounter,
  isShopCounter,
  _clearCountersCache,
  type Counter,
} from "./Counters";

afterEach(() => {
  _clearCountersCache();
  vi.unstubAllGlobals();
});

function stubFetch(payload: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      ({ ok: true, json: async () => payload }) as unknown as Response,
    ),
  );
}

describe("loadCounters", () => {
  it("parses shop and service counters from counters.json", async () => {
    stubFetch({
      weapon: {
        name: "Weapons Shop",
        description: "Sells weapons.",
        items: ["Sword", "Dagger"],
      },
      healing: {
        name: "Healing Counter",
        description: "Mends flesh.",
        kind: "service",
        items: [],
        services: [
          { id: "heal_all_hp", name: "Heal All HP", cost: 100 },
          { id: "raise_dead", name: "Raise Dead", cost: 1000 },
        ],
      },
    });

    const counters = await loadCounters("/data/counters.json");
    const weapon = counters.get("weapon")!;
    const healing = counters.get("healing")!;

    expect(weapon.kind).toBe("shop");
    expect(weapon.items).toEqual(["Sword", "Dagger"]);
    expect(weapon.services).toEqual([]);

    expect(healing.kind).toBe("service");
    expect(healing.services.map((s) => s.id)).toEqual([
      "heal_all_hp", "raise_dead",
    ]);
    expect(healing.services[0].cost).toBe(100);
  });

  it("defaults missing kind to 'shop' and missing fields to safe values", async () => {
    stubFetch({ general: { items: ["Torch"] } });
    const counters = await loadCounters("/data/counters.json");
    const c = counters.get("general")!;
    expect(c.key).toBe("general");
    expect(c.name).toBe("general");
    expect(c.kind).toBe("shop");
    expect(c.description).toBe("");
    expect(c.services).toEqual([]);
  });

  it("coerces string costs into numbers", async () => {
    stubFetch({
      healing: {
        kind: "service",
        services: [{ id: "heal", cost: "75" }],
      },
    });
    const counters = await loadCounters("/data/counters.json");
    expect(counters.get("healing")!.services[0].cost).toBe(75);
  });
});

describe("kind predicates", () => {
  const shop: Counter = {
    key: "weapon", name: "", description: "", kind: "shop",
    items: [], services: [],
  };
  const svc: Counter = {
    key: "healing", name: "", description: "", kind: "service",
    items: [], services: [],
  };
  it("classifies counters by kind", () => {
    expect(isShopCounter(shop)).toBe(true);
    expect(isShopCounter(svc)).toBe(false);
    expect(isServiceCounter(svc)).toBe(true);
    expect(isServiceCounter(shop)).toBe(false);
    expect(isShopCounter(null)).toBe(false);
    expect(isServiceCounter(null)).toBe(false);
  });
});
