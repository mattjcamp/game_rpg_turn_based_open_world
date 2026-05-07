import { describe, it, expect } from "vitest";
import {
  sumBuff,
  tickBuffs,
  describeExpire,
  type Buff,
} from "./Buffs";

describe("Buffs.sumBuff", () => {
  it("returns 0 for an empty list or undefined", () => {
    expect(sumBuff(undefined, "attack_bonus")).toBe(0);
    expect(sumBuff([], "attack_bonus")).toBe(0);
  });

  it("sums every buff matching the kind and ignores other kinds", () => {
    const buffs: Buff[] = [
      { kind: "attack_bonus",   value: 2, turnsLeft: 3, source: "Bless" },
      { kind: "attack_bonus",   value: 1, turnsLeft: 2, source: "Other" },
      { kind: "ac_bonus",       value: 1, turnsLeft: 3, source: "Shield" },
      { kind: "attack_penalty", value: 2, turnsLeft: 3, source: "Curse" },
    ];
    expect(sumBuff(buffs, "attack_bonus")).toBe(3);
    expect(sumBuff(buffs, "ac_bonus")).toBe(1);
    expect(sumBuff(buffs, "attack_penalty")).toBe(2);
    expect(sumBuff(buffs, "ac_penalty")).toBe(0);
  });
});

describe("Buffs.tickBuffs", () => {
  it("decrements every buff and removes those that expire", () => {
    const buffs: Buff[] = [
      { kind: "attack_bonus", value: 2, turnsLeft: 1, source: "Bless" },
      { kind: "ac_bonus",     value: 1, turnsLeft: 3, source: "Shield" },
    ];
    const expired = tickBuffs(buffs);
    // The 1-turn Bless expired; Shield ticks down to 2.
    expect(expired).toHaveLength(1);
    expect(expired[0].source).toBe("Bless");
    expect(buffs).toHaveLength(1);
    expect(buffs[0].source).toBe("Shield");
    expect(buffs[0].turnsLeft).toBe(2);
  });

  it("expires every buff in one tick when they all hit zero", () => {
    const buffs: Buff[] = [
      { kind: "attack_bonus", value: 2, turnsLeft: 1, source: "Bless" },
      { kind: "ac_bonus",     value: 1, turnsLeft: 1, source: "Shield" },
    ];
    const expired = tickBuffs(buffs);
    expect(expired).toHaveLength(2);
    expect(buffs).toHaveLength(0);
  });
});

describe("Buffs.describeExpire", () => {
  it("uses the spell-specific phrasing where available", () => {
    expect(describeExpire("Selina",  "Bless")).toContain("blessing fades");
    expect(describeExpire("Goblin",  "Curse")).toContain("curse lifts");
    expect(describeExpire("Gandolf", "Shield")).toContain("magical shield fades");
    expect(describeExpire("Merry",   "Long Shanks")).toContain("hastened legs slow");
    expect(describeExpire("Gandolf", "Invisibility")).toContain("reappears");
  });

  it("falls back to a generic message for unknown sources", () => {
    expect(describeExpire("Gimli", "MysteryGift")).toBe("Gimli's MysteryGift ends.");
  });
});
