import { describe, it, expect } from "vitest";
import {
  isLockedAt,
  unlockAt,
  findLockpicker,
  findKnockCaster,
  getLockpickCharges,
  consumeLockpick,
  attemptLockpick,
  attemptKnock,
  buildLockOptions,
  PICK_LOCK_DC,
} from "./Lock";
import { TileMap } from "./TileMap";
import { TILE_DDOOR, TILE_LOCKED_DOOR, TILE_GRASS } from "./Tiles";
import { partyFromRaw, activeMembers } from "./Party";
import type { Spell } from "./Spells";

function makeMap(grid: number[][], props: Record<string, unknown> = {}): TileMap {
  return new TileMap(
    grid[0].length, grid.length, grid,
    { tileProperties: props as Record<string, never> },
  );
}

function makeParty(extra: Partial<Parameters<typeof partyFromRaw>[0]> = {}) {
  return partyFromRaw({
    gold: 0,
    roster: [
      { name: "Gimli",   class: "Fighter", race: "Dwarf",    level: 1, hp: 20, dexterity: 12 },
      { name: "Merry",   class: "Thief",   race: "Halfling", level: 1, hp: 18, dexterity: 18 },
      { name: "Gandolf", class: "Wizard",  race: "Elf",      level: 2, hp: 14, mp: 10, intelligence: 16 },
      { name: "Robin",   class: "Ranger",  race: "Human",    level: 4, hp: 16, dexterity: 14 },
    ],
    active_party: [0, 1, 2, 3],
    inventory: [{ item: "Lockpick", charges: 5 }],
    ...extra,
  });
}

const KNOCK: Spell = {
  id: "knock", name: "Knock", description: "",
  allowable_classes: ["Wizard", "Alchemist", "Druid"],
  casting_type: "sorcerer",
  min_level: 2,
  mp_cost: 6,
  duration: "instant",
  effect_type: "knock",
  effect_value: { save_dc_base: 12, save_stat: "intelligence" },
  usable_in: ["dungeon"],
};

describe("isLockedAt", () => {
  it("returns true for legacy TILE_LOCKED_DOOR cells", () => {
    const m = makeMap([[TILE_GRASS, TILE_LOCKED_DOOR]]);
    expect(isLockedAt(m, 1, 0)).toBe(true);
    expect(isLockedAt(m, 0, 0)).toBe(false);
  });

  it("returns true for cells with tile_properties.locked = true", () => {
    const m = makeMap([[TILE_GRASS, TILE_DDOOR]], { "1,0": { locked: true } });
    expect(isLockedAt(m, 1, 0)).toBe(true);
  });

  it("returns false for unknown cells / out of bounds", () => {
    const m = makeMap([[TILE_GRASS]]);
    expect(isLockedAt(m, 5, 5)).toBe(false);
    expect(isLockedAt(m, -1, 0)).toBe(false);
  });
});

describe("unlockAt", () => {
  it("converts TILE_LOCKED_DOOR → TILE_DDOOR and returns the new id", () => {
    const m = makeMap([[TILE_LOCKED_DOOR]]);
    const newId = unlockAt(m, 0, 0);
    expect(newId).toBe(TILE_DDOOR);
    expect(m.getTile(0, 0)).toBe(TILE_DDOOR);
  });

  it("clears tile_properties.locked", () => {
    const m = makeMap([[TILE_DDOOR]], { "0,0": { locked: true, walkable: true } });
    unlockAt(m, 0, 0);
    const entry = m.tileProperties["0,0"] as Record<string, unknown>;
    expect("locked" in entry).toBe(false);
    // Other props on the same key survive.
    expect(entry.walkable).toBe(true);
  });

  it("clears both signals when a tile carries the legacy id AND the property", () => {
    // The Python game saw building doors stored with both — Python's
    // bug was that the property survived after a sprite swap. We
    // make sure both go.
    const m = makeMap(
      [[TILE_LOCKED_DOOR]],
      { "0,0": { locked: true } },
    );
    unlockAt(m, 0, 0);
    expect(m.getTile(0, 0)).toBe(TILE_DDOOR);
    expect(m.tileProperties["0,0"]).toBeUndefined();
  });
});

describe("findLockpicker", () => {
  it("prefers an alive Thief over a high-level Ranger", () => {
    const p = makeParty();
    const m = findLockpicker(activeMembers(p));
    expect(m?.name).toBe("Merry");
  });

  it("falls back to a level-3+ Ranger when no Thief is present", () => {
    const p = makeParty({
      roster: [
        { name: "Gimli",  class: "Fighter", race: "Dwarf",  level: 1, hp: 20 },
        { name: "Robin",  class: "Ranger",  race: "Human",  level: 4, hp: 16, dexterity: 14 },
      ],
      active_party: [0, 1],
    });
    expect(findLockpicker(activeMembers(p))?.name).toBe("Robin");
  });

  it("rejects rangers below level 3", () => {
    const p = makeParty({
      roster: [
        { name: "Robin",  class: "Ranger",  race: "Human",  level: 2, hp: 16 },
      ],
      active_party: [0],
    });
    expect(findLockpicker(activeMembers(p))).toBeNull();
  });

  it("skips downed picks", () => {
    const p = makeParty();
    p.roster[1].hp = 0;  // Merry the Thief unconscious
    p.roster[3].hp = 0;  // Robin the Ranger unconscious
    expect(findLockpicker(activeMembers(p))).toBeNull();
  });
});

describe("findKnockCaster", () => {
  it("finds an alive caster meeting class + level requirements", () => {
    const p = makeParty();
    expect(findKnockCaster(activeMembers(p), KNOCK)?.name).toBe("Gandolf");
  });

  it("rejects casters below the spell's min_level", () => {
    const p = makeParty();
    p.roster[2].level = 1;
    expect(findKnockCaster(activeMembers(p), KNOCK)).toBeNull();
  });

  it("rejects classes that aren't allowable", () => {
    const p = makeParty({
      roster: [
        { name: "Cleric", class: "Cleric", race: "Human", level: 5, hp: 18, mp: 10 },
      ],
      active_party: [0],
    });
    expect(findKnockCaster(activeMembers(p), KNOCK)).toBeNull();
  });
});

describe("getLockpickCharges + consumeLockpick", () => {
  it("totals charges across stash entries", () => {
    const p = makeParty({
      inventory: [{ item: "Lockpick", charges: 3 }, { item: "Lockpick", charges: 2 }],
    });
    expect(getLockpickCharges(p)).toBe(5);
  });

  it("decrements one charge per call, removing entries that hit zero", () => {
    const p = makeParty({ inventory: [{ item: "Lockpick", charges: 2 }] });
    expect(consumeLockpick(p)).toBe(true);
    expect(getLockpickCharges(p)).toBe(1);
    expect(consumeLockpick(p)).toBe(true);
    expect(getLockpickCharges(p)).toBe(0);
    expect(p.inventory.length).toBe(0);
  });

  it("returns false when there are no lockpicks", () => {
    const p = makeParty({ inventory: [] });
    expect(consumeLockpick(p)).toBe(false);
  });
});

describe("attemptLockpick", () => {
  it("succeeds when the d20 + DEX mod meets the DC", () => {
    const p = makeParty();
    const merry = p.roster[1]; // DEX 18 → +4
    // rng=0.95 → roll = 1 + floor(0.95*20) = 20. Total = 24 >= 12.
    const r = attemptLockpick(merry, () => 0.95);
    expect(r.success).toBe(true);
    expect(r.dc).toBe(PICK_LOCK_DC);
  });

  it("fails when the total falls below the DC", () => {
    const p = makeParty();
    const fighter = p.roster[0]; // DEX 12 → +1
    // roll = 1, total = 2 < 12.
    expect(attemptLockpick(fighter, () => 0.0).success).toBe(false);
  });
});

describe("attemptKnock", () => {
  it("succeeds when the d20 + INT mod meets the spell's save DC", () => {
    const p = makeParty();
    const gandolf = p.roster[2]; // INT 16 → +3
    // roll 18, total 21 >= 12.
    const r = attemptKnock(gandolf, KNOCK, () => 0.85);
    expect(r.success).toBe(true);
    expect(r.dc).toBe(12);
    expect(r.mpCost).toBe(6);
  });

  it("returns the configured DC and stat from the spell payload", () => {
    const p = makeParty();
    const custom: Spell = {
      ...KNOCK,
      effect_value: { save_dc_base: 18, save_stat: "wisdom" },
    };
    const r = attemptKnock(p.roster[2], custom, () => 0.0);
    expect(r.dc).toBe(18);
    // INT mod no longer applies — wisdom is 10, so mod is 0.
    expect(r.mod).toBe(0);
  });
});

describe("buildLockOptions", () => {
  it("offers Pick Lock + Cast Knock + Leave when both helpers are available", () => {
    const p = makeParty();
    const opts = buildLockOptions({
      party: p, members: activeMembers(p), knockSpell: KNOCK,
    });
    const ids = opts.map((o) => o.id);
    expect(ids).toEqual(["pick", "knock", "leave"]);
    expect(opts[0].label).toContain("Merry");
    expect(opts[0].label).toContain("5 picks");
    expect(opts[1].label).toContain("Gandolf");
    expect(opts[1].label).toContain("6 MP");
  });

  it("warns when the only Thief has no lockpicks", () => {
    const p = makeParty({ inventory: [] });
    const opts = buildLockOptions({
      party: p, members: activeMembers(p), knockSpell: null,
    });
    expect(opts[0].id).toBe("no_picks");
  });

  it("warns when the party has no Thief or qualifying Ranger", () => {
    const p = makeParty({
      roster: [{ name: "Gimli", class: "Fighter", race: "Dwarf", level: 1, hp: 20 }],
      active_party: [0],
      inventory: [],
    });
    const opts = buildLockOptions({
      party: p, members: activeMembers(p), knockSpell: null,
    });
    expect(opts[0].id).toBe("no_thief");
  });

  it("warns when the caster's MP is short", () => {
    const p = makeParty();
    p.roster[2].mp = 3;
    const opts = buildLockOptions({
      party: p, members: activeMembers(p), knockSpell: KNOCK,
    });
    expect(opts.find((o) => o.id === "no_knock_mp")).toBeTruthy();
  });
});
